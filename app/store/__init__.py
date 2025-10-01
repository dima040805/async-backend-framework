class Store:
    def __init__(self, app):
        from app.users.accessor import UserAccessor
        from app.store.database.db import Database
        from app.store.bot.accessor import BotAccessor

        self.app = app
        self.database = Database(app)
        self.bot = BotAccessor(app)
        self.user = UserAccessor(app)