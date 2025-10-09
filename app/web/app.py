import typing

from aiohttp.web import (
    Application as AiohttpApplication,
    Request as AiohttpRequest,
    View as AiohttpView,
)

if typing.TYPE_CHECKING:
    from app.web.config import Config

__all__ = ("Application", "Request", "View")


class Application(AiohttpApplication):
    config: "Config" = None
    store: object = None
    database: object = None


class Request(AiohttpRequest):
    @property
    def app(self) -> "Application":
        return super().app()


class View(AiohttpView):
    @property
    def request(self) -> Request:
        return super().request

    @property
    def store(self):
        return self.request.app.store

    @property
    def data(self) -> dict:
        return self.request.get("data", {})


def setup_app(config_path: str) -> Application:
    # ruff: noqa: PLC0415
    from aiohttp_apispec import setup_aiohttp_apispec
    from aiohttp_session import setup as session_setup
    from aiohttp_session.cookie_storage import EncryptedCookieStorage

    from app.store.store import setup_store
    from app.web.config import setup_config
    from app.web.mw import setup_middlewares
    from app.web.routes import setup_routes

    app = Application()
    setup_config(app, config_path)

    session_setup(app, EncryptedCookieStorage(app.config.session.key))

    setup_routes(app)
    setup_aiohttp_apispec(
        app, title="100к1 Bot", url="/docs/json", swagger_path="/docs"
    )
    setup_middlewares(app)
    setup_store(app)

    async def start_bot(app):
        await app.store.bot.connect()

    app.on_startup.append(start_bot)

    async def stop_bot(app):
        await app.store.bot.disconnect()

    app.on_cleanup.append(stop_bot)

    return app
