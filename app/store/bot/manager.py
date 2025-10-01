import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class BotManager:
    def __init__(self, app):
        self.app = app
        self.telegram_api = app.telegram_api

    async def handle_update(self, update: Dict[str, Any]):
        try:
            if 'message' in update:
                await self._handle_message(update['message'])
            elif 'edited_message' in update:
                await self._handle_edited_message(update['edited_message'])
        except Exception as e:
            logger.error(f"Error handling update: {e}")

    async def _handle_message(self, message: Dict[str, Any]):
        chat_id = message['chat']['id']
        text = message.get('text', '').strip()
        
        if text:
            await self.telegram_api.send_message(
                chat_id=chat_id,
                text=f"{text}"
            )
            logger.info(f"Echoed message to chat {chat_id}: {text}")

    async def _handle_edited_message(self, message: Dict[str, Any]):
        chat_id = message['chat']['id']
        text = message.get('text', '').strip()
        
        await self.telegram_api.send_message(
            chat_id=chat_id,
            text=f"Edited echo: {text}"
        )