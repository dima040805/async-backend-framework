class Store:
    def __init__(self, app):
        from app.store.bot.accessor import BotAccessor
        from app.store.database.database import Database
        from app.users.accessor import UserAccessor

        self.app = app
        self.database = Database(app)
        self.bot = BotAccessor(app)
        self.user = UserAccessor(app)
