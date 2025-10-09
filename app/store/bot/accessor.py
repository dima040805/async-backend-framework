import logging
import typing

from app.store.bot.manager import BotManager
from app.store.bot.poller import Poller
from app.store.telegram.api import TelegramAPI

if typing.TYPE_CHECKING:
    from app.web.app import Application

logger = logging.getLogger(__name__)


class BotAccessor:
    def __init__(self, app: "Application"):
        self.app = app
        self.manager = None
        self.poller = None

    async def connect(self):

        self.app.store.telegram_api = TelegramAPI(
            self.app.config.telegram.token
        )

        await self.app.store.database.connect()

        self.manager = BotManager(self.app)
        self.poller = Poller(self.app, self.manager)

        await self.poller.start()
        logger.info("Bot started successfully")

    async def disconnect(self):
        if self.poller:
            await self.poller.stop()
        if hasattr(self.app.store, "database") and self.app.store.database:
            await self.app.store.database.disconnect()
        logger.info("Bot stopped")
