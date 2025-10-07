import aiohttp
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class TelegramAPI:
    def __init__(self, token: str):
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def _ensure_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
    
    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        await self._ensure_session()
        url = f"{self.base_url}/{endpoint}"
        
        try:
            async with self.session.request(method, url, **kwargs) as response:
                return await response.json()
        except Exception as e:
            logger.error(f"Error making Telegram API request: {e}")
            return {"ok": False, "error": str(e)}
    
    async def get_me(self) -> Dict[str, Any]:
        return await self._make_request("GET", "getMe")
    
    async def get_updates(self, offset: Optional[int] = None, timeout: int = 30) -> Dict[str, Any]:
        params = {"timeout": timeout}
        if offset:
            params["offset"] = offset
            
        return await self._make_request("GET", "getUpdates", params=params)
    
    async def send_message(self, chat_id: int, text: str) -> Dict[str, Any]:
        data = {
            "chat_id": chat_id, 
            "text": text,
            "parse_mode": "Markdown"
        }
        return await self._make_request("POST", "sendMessage", json=data)
    
    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()