import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class Poller:
    def __init__(self, app, manager):
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
                updates = await self.app.telegram_api.get_updates(
                    offset=self.offset,
                    timeout=30
                )
                
                if updates.get('ok') and updates.get('result'):
                    for update in updates['result']:
                        await self.manager.handle_update(update)
                        self.offset = update['update_id'] + 1
                
                await asyncio.sleep(self.app.config['telegram']['polling_interval'])
                
            except Exception as e:
                logger.error(f"Polling error: {e}")
                await asyncio.sleep(5)  # Wait before retry