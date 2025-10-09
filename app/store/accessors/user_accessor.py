import logging

from app.store.database.base_accessor import BaseAccessor

logger = logging.getLogger(__name__)


class UserAccessor(BaseAccessor):
    async def get_or_create_user(self, telegram_id: int, 
                                 username: str | None = None):
        pass
