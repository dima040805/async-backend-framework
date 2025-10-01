from aiohttp.web_app import Application

from app.admin.routes import setup_admin_routes

__all__ = ("setup_routes",)


def setup_routes(application: Application):
    import app.users.routes

    setup_admin_routes(application)
    app.users.routes.register_urls(application)
