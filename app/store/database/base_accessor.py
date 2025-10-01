class BaseAccessor:
    def __init__(self, app):
        self.app = app

    async def connect(self, app):
        pass

    async def disconnect(self, app):
        pass
