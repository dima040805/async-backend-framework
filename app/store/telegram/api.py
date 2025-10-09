import logging

import aiohttp

logger = logging.getLogger(__name__)


class TelegramAPI:
    def __init__(self, token: str):
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.session: aiohttp.ClientSession | None = None

    async def _ensure_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()

    async def _make_request(
        self, method: str, endpoint: str, **kwargs
    ) -> dict[str, object]:
        await self._ensure_session()
        url = f"{self.base_url}/{endpoint}"

        try:
            async with self.session.request(method, url, **kwargs) as response:
                return await response.json()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def get_me(self) -> dict[str, object]:
        return await self._make_request("GET", "getMe")

    async def get_updates(
        self, offset: int | None = None, timeout: int = 30
    ) -> dict[str, object]:
        params = {"timeout": timeout}
        if offset:
            params["offset"] = offset

        return await self._make_request("GET", "getUpdates", params=params)

    async def send_message(
        self, chat_id: int, text: str, reply_markup: dict | None = None
    ) -> dict[str, object]:
        data = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
        if reply_markup:
            data["reply_markup"] = reply_markup

        return await self._make_request("POST", "sendMessage", json=data)

    async def answer_callback_query(
        self, callback_query_id: str, text: str | None = None
    ) -> dict[str, object]:
        data = {"callback_query_id": callback_query_id}
        if text:
            data["text"] = text

        return await self._make_request(
            "POST", "answerCallbackQuery", json=data
        )

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
            logger.info("🔌 Telegram API session closed")
