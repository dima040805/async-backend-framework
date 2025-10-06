import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text
from app.store.database.database import Database
from app.web.app import setup_app


async def add_new_fields():
    # Создаем приложение для доступа к конфигурации
    app = setup_app("etc/config.yaml")
    await app.store.database.connect()
    
    try:
        async with app.store.database.engine.begin() as conn:
            # Добавляем новые поля в таблицу game_sessions
            await conn.execute(text("""
                ALTER TABLE game_sessions 
                ADD COLUMN IF NOT EXISTS max_rounds_per_question INTEGER DEFAULT 3,
                ADD COLUMN IF NOT EXISTS revealed_variants JSONB DEFAULT '[]'::JSONB
            """))
            print("✅ Новые поля успешно добавлены в таблицу game_sessions!")
            
            # Добавляем поле total_points в таблицу players
            await conn.execute(text("""
                ALTER TABLE players 
                ADD COLUMN IF NOT EXISTS total_points INTEGER DEFAULT 0
            """))
            print("✅ Поле total_points успешно добавлено в таблицу players!")
            
    except Exception as e:
        print(f"❌ Ошибка при добавлении полей: {e}")
    finally:
        await app.store.database.disconnect()


if __name__ == "__main__":
    asyncio.run(add_new_fields())