import logging
from app.store.database.base_accessor import BaseAccessor

logger = logging.getLogger(__name__)


class AdminAccessor(BaseAccessor):
    
    async def is_user_admin(self, telegram_id: int) -> bool:

        return True