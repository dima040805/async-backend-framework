import logging
from typing import Any, Dict, Optional

import aiohttp

logger = logging.getLogger(__name__)


class TelegramAPI:
    def __init__(self, token: str):
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{token}"

    async def get_updates(
        self, offset: Optional[int] = None, timeout: int = 30
    ) -> Dict[str, Any]:
        """Получаем обновления от Telegram"""
        url = f"{self.base_url}/getUpdates"
        params = {"timeout": timeout}
        if offset:
            params["offset"] = offset

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    data = await response.json()
                    return data
        except Exception as e:
            logger.error(f"Error getting updates: {e}")
            return {"ok": False, "error": str(e)}

    async def send_message(self, chat_id: int, text: str) -> Dict[str, Any]:
        """Отправляем сообщение в Telegram"""
        url = f"{self.base_url}/sendMessage"
        data = {
            "chat_id": chat_id,
            "text": text,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data) as response:
                    result = await response.json()
                    return result
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return {"ok": False, "error": str(e)}
