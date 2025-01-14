"""
test_api_db.py

Один файл, который:
 - Сам определяет класс User (простейший).
 - Достаёт зашифрованный токен из БД (метод load_token_db).
 - Расшифровывает токен (decrypt_token).
 - Через AsyncMobileAPI + token получает профили, детей, заполняет User.
 - Вызывает inline-функции get_marks, get_subjects_marks, get_mark,
   заимствованные из GitHub api.py.
"""

import asyncio
import logging
from datetime import date
from typing import Optional, Generic, TypeVar
from pydantic import BaseModel

# Из вашего бота:
from bot.auth import load_token_db, decrypt_token
from bot.database import get_db_connection
# Из octodiary:
from octodiary.apis import AsyncMobileAPI
from octodiary.urls import Systems
from octodiary import types

# Укажите тот telegram_user_id,
# у которого есть encrypted_token в таблице users
TEST_TELEGRAM_ID = 821884326

# Диапазон дат для get_marks
FROM_DATE = date(2024, 9, 1)
TO_DATE   = date(2024, 9, 30)

# ------------------------------------------------------------------------------
# 1) Минимальный класс User,
#    чтобы удовлетворить вызовы get_marks, get_subjects_marks, etc.
# ------------------------------------------------------------------------------
class User:
    """
    Простейший класс, подделка того, что у вас могло быть в проекте.
    """
    def __init__(
        self,
        telegram_user_id: int,
        db_profile_id: int,
        db_profile: dict,
        db_current_child: dict,
        system: str = "MES"
    ):
        self.telegram_user_id = telegram_user_id
        self.db_profile_id = db_profile_id
        self.db_profile = db_profile
        self.db_current_child = db_current_child
        self.system = system

# ------------------------------------------------------------------------------
# 2) Поддельный класс APIs (чтобы get_marks / get_subjects_marks
#    могли внутри вызывать apis.mobile.get_...)
# ------------------------------------------------------------------------------
class FakeAPIs:
    def __init__(self, mobile_api: AsyncMobileAPI):
        self.mobile = mobile_api

# ------------------------------------------------------------------------------
# 3) inline: APIResponse и методы get_marks, get_subjects_marks, get_mark
# ------------------------------------------------------------------------------
ResponseType = TypeVar("ResponseType")

class APIResponse(BaseModel, Generic[ResponseType]):
    response: ResponseType
    is_cache: bool = False
    last_cache_time: Optional[str] = None

async def get_marks(
    user: User,
    apis: FakeAPIs,
    from_date: date,
    to_date: date,
    *,
    student_id: Optional[int] = None
) -> APIResponse[types.mobile.Marks]:
    """
    Упрощённый метод: вызывает apis.mobile.get_marks(...)
    """
    try:
        sid = student_id or (
            user.db_current_child["id"] if user.db_current_child
            else user.db_profile["children"][0]["id"]
        )
        marks_data = await apis.mobile.get_marks(
            student_id=sid,
            profile_id=user.db_profile_id,
            from_date=from_date,
            to_date=to_date
        )
    except Exception as e:
        logging.error("Ошибка в get_marks", exc_info=e)
        raise e

    return APIResponse(response=marks_data, is_cache=False, last_cache_time=None)

async def get_subjects_marks(
    user: User,
    apis: FakeAPIs,
) -> APIResponse[types.mobile.SubjectsMarks]:
    """
    Упрощённый метод: вызывает apis.mobile.get_subjects_marks(...)
    """
    try:
        sid = (
            user.db_current_child["id"] if user.db_current_child
            else user.db_profile["children"][0]["id"]
        )
        subj_data = await apis.mobile.get_subjects_marks(
            student_id=sid,
            profile_id=user.db_profile_id
        )
    except Exception as e:
        logging.error("Ошибка в get_subjects_marks", exc_info=e)
        raise e

    return APIResponse(response=subj_data, is_cache=False, last_cache_time=None)


async def get_mark(
    user: User,
    apis: FakeAPIs,
    mark_id: str
) -> APIResponse[types.mobile.lesson_schedule_item.Mark]:
    """
    Упрощённый метод: вызывает apis.mobile.request(...) для конкретной оценки.
    """
    try:
        sid = (
            user.db_current_child["id"] if user.db_current_child
            else user.db_profile["children"][0]["id"]
        )
        # model=types.mobile.lesson_schedule_item.Mark
        single = await apis.mobile.request(
            method="GET",
            base_url=Systems.MES.family_mobile,  # Может отличаться, зависит от octodiary
            path=f"/family/mobile/v1/marks/{mark_id}",
            params={"student_id": sid},
            custom_headers={
                "x-mes-subsystem": "familymp",
                "client-type": "diary-mobile",
                "profile-id": str(user.db_profile_id),
            },
            model=types.mobile.lesson_schedule_item.Mark
        )
    except Exception as e:
        logging.error("Ошибка в get_mark", exc_info=e)
        raise e

    return APIResponse(response=single, is_cache=False, last_cache_time=None)


# ------------------------------------------------------------------------------
# Основная асинхронная функция
# ------------------------------------------------------------------------------
async def test_main():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    # 1) Загрузим зашифрованный токен
    encrypted_token = load_token_db(TEST_TELEGRAM_ID)
    if not encrypted_token:
        logger.error(f"В БД нет токена для пользователя {TEST_TELEGRAM_ID}")
        return

    # 2) Расшифруем
    try:
        token_data = decrypt_token(encrypted_token)
        logger.info("Токен расшифрован успешно!")
    except Exception as e:
        logger.error(f"Ошибка расшифровки: {e}")
        return

    # 3) Создаём AsyncMobileAPI
    mobile_api = AsyncMobileAPI(system=Systems.MES)
    mobile_api.token = token_data
    logger.info("mobile_api сконфигурирован.")

    # 4) fake_apis
    fake_apis = FakeAPIs(mobile_api)

    # 5) Получаем профили, чтобы собрать User
    try:
        profiles = await mobile_api.get_users_profile_info()
        if not profiles:
            logger.error("Не нашли профилей. Токен мог просрочиться.")
            return
        first_prof = profiles[0]
        fam = await mobile_api.get_family_profile(profile_id=first_prof.id)
        if not fam.children:
            logger.warning("В профиле нет children. Возможно, это учитель.")
            return
        child = fam.children[0]
        logger.info(f"Выбрали ребёнка: {child.name}")

        user = User(
            telegram_user_id=TEST_TELEGRAM_ID,
            db_profile_id=first_prof.id,
            db_profile=fam.model_dump(),
            db_current_child=child.model_dump(),
            system="MES"
        )
    except Exception as e:
        logger.error(f"Ошибка при сборе User: {e}")
        return

    # 6) Вызываем get_marks
    try:
        marks_resp = await get_marks(user, fake_apis, FROM_DATE, TO_DATE)
        print("\n=== GET_MARKS ===")
        print("response =>", marks_resp.response)
    except Exception as e:
        logger.error(f"Ошибка get_marks: {e}")

    # 7) Вызываем get_subjects_marks
    try:
        subs_resp = await get_subjects_marks(user, fake_apis)
        print("\n=== GET_SUBJECTS_MARKS ===")
        print("response =>", subs_resp.response)
    except Exception as e:
        logger.error(f"Ошибка get_subjects_marks: {e}")

    # 8) Пример get_mark, если знаете mark_id
    # mark_id = "какой-то-mark-id"
    # try:
    #     single_mark = await get_mark(user, fake_apis, mark_id)
    #     print("\n=== GET_MARK ===", single_mark.response)
    # except Exception as e:
    #     logger.error(f"Ошибка get_mark: {e}")


def main():
    asyncio.run(test_main())

if __name__ == "__main__":
    main()
