from aiohttp.web import (
    Application as AiohttpApplication,
)

from app.store import Store
from app.store.database.db import Database  
from app.store.telegram.api import TelegramAPI

__all__ = ("Application",)


class Application(AiohttpApplication):
    config: dict = None
    store: Store = None
    database: Database = None
    telegram_api: TelegramAPI = None


def setup_app(config_path: str) -> Application:
    from .routes import setup_routes
    
    app = Application()
    setup_routes(app)
    return app