import typing

if typing.TYPE_CHECKING:
    from app.web.app import Application


class Store:
    def __init__(self, app: "Application"):
        from app.store.bot.accessor import BotAccessor
        from app.store.database.database import Database
        from app.store.accessors.admin_accessor import AdminAccessor
        from app.store.accessors.session_accessor import SessionAccessor
        from app.store.accessors.user_accessor import UserAccessor
        from app.store.accessors.game_accessor import GameAccessor

        self.app = app
        self.database = Database(app)
        self.bot = BotAccessor(app)
        self.admin_accessor = AdminAccessor(app)
        self.session_accessor = SessionAccessor(app)
        self.user_accessor = UserAccessor(app)
        self.game_accessor = GameAccessor(app)


def setup_store(app: "Application"):
    app.store = Store(app)