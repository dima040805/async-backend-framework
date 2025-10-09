import logging
import typing

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

if typing.TYPE_CHECKING:
    from app.web.app import Application

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, app: "Application"):
        self.app = app
        self.engine = None
        self.session = None

    async def connect(self):
        db_config = self.app.config.database
        database_url = f"postgresql+asyncpg://{db_config.user}:{db_config.password}@{db_config.host}:{db_config.port}/{db_config.database}"

        self.engine = create_async_engine(
            database_url,
            echo=False,  # Убрали echo=self.app.config.debug
            future=True,
        )
        self.session = async_sessionmaker(
            self.engine,
            expire_on_commit=False,
        )
        logger.info("Database connected successfully")

    async def disconnect(self):
        if self.engine:
            await self.engine.dispose()
            logger.info("Database disconnected")
