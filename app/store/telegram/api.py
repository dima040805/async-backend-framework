import aiohttp
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class TelegramAPI:
    def __init__(self, token: str):
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{token}"
    
    async def get_updates(self, offset: Optional[int] = None, timeout: int = 30) -> Dict[str, Any]:
        url = f"{self.base_url}/getUpdates"
        params = {"timeout": timeout}
        if offset:
            params["offset"] = offset
            
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    data = await response.json()
                    logger.debug(f"Got updates: {data}")
                    return data
        except Exception as e:
            logger.error(f"Error getting updates: {e}")
            return {"ok": False, "error": str(e)}
    
    async def send_message(self, chat_id: int, text: str) -> Dict[str, Any]:
        url = f"{self.base_url}/sendMessage"
        data = {
            "chat_id": chat_id, 
            "text": text,
            "parse_mode": "HTML"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data) as response:
                    result = await response.json()
                    if not result.get("ok"):
                        logger.error(f"Telegram API error: {result}")
                    return result
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return {"ok": False, "error": str(e)}