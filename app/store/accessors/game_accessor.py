import logging
import typing
from app.store.database.base_accessor import BaseAccessor

if typing.TYPE_CHECKING:
    from app.web.app import Application

logger = logging.getLogger(__name__)


class GameAccessor(BaseAccessor):
    
    def __init__(self, app: "Application"):
        super().__init__(app)
        self.active_sessions = {}

    async def connect(self, app: "Application"):
        """Подключение аксессора"""
        logger.info("GameAccessor connected")

    async def disconnect(self, app: "Application"):
        """Отключение аксессора"""
        logger.info("GameAccessor disconnected")