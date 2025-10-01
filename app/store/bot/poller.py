import asyncio
import logging
import typing
from typing import Optional

if typing.TYPE_CHECKING:
    from app.web.app import Application

logger = logging.getLogger(__name__)


class Poller:
    def __init__(self, app: "Application", manager):
        self.app = app
        self.manager = manager
        self.is_running = False
        self.task: Optional[asyncio.Task] = None
        self.offset = 0

    async def start(self):
        self.is_running = True
        self.task = asyncio.create_task(self._poll())

    async def stop(self):
        self.is_running = False
        if self.task:
            await self.task
            self.task = None

    async def _poll(self):
        while self.is_running:
            try:
                if not hasattr(self.app.store, "telegram_api"):
                    await asyncio.sleep(1)
                    continue

                updates = await self.app.store.telegram_api.get_updates(
                    offset=self.offset, timeout=30
                )

                if updates.get("ok") and updates.get("result"):
                    for update in updates["result"]:
                        await self.manager.handle_update(update)
                        self.offset = update["update_id"] + 1

                polling_interval = self.app.config.telegram.polling_interval
                await asyncio.sleep(polling_interval)

            except Exception as e:
                logger.error(f"Polling error: {e}")
                await asyncio.sleep(5)
