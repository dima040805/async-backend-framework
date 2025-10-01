import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.models.database import Base

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, app):
        self.app = app
        self.engine = None
        self.session = None

    async def connect(self):
        database_url = self.app.config['database']['url'].replace(
            'postgresql://', 'postgresql+asyncpg://'
        )
        
        self.engine = create_async_engine(
            database_url,
            echo=self.app.config['debug'],
            future=True
        )
        
        self.session = sessionmaker(
            self.engine, 
            class_=AsyncSession, 
            expire_on_commit=False
        )
        
        logger.info("Database connected successfully")

    async def disconnect(self):
        """Отключается от базы данных"""
        if self.engine:
            await self.engine.dispose()
            logger.info("Database disconnected")

    async def create_tables(self):
        """Создает таблицы (для разработки)"""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)