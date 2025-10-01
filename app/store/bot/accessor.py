from app.store.database.base_accessor import BaseAccessor
from app.store.bot.manager import BotManager
from app.store.bot.poller import Poller  

class BotAccessor(BaseAccessor):
    def __init__(self, app):
        super().__init__(app)
        self.manager = None
        self.poller = None

    async def connect(self, app):
        self.manager = BotManager(self.app)
        self.poller = Poller(self.app, self.manager)
        await self.poller.start()

    async def disconnect(self, app):
        if self.poller:
            await self.poller.stop()