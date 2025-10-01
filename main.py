import asyncio
import logging
import yaml
from aiohttp import web
from app.web.app import setup_app
from app.store import Store
from app.store.database.db import Database
from app.store.telegram.api import TelegramAPI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def load_config(config_path: str) -> dict:
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

async def main():
    config_path = "etc/config.yaml"
    config = load_config(config_path)
    
    app = setup_app(config_path)
    app.config = config
    
    app.telegram_api = TelegramAPI(config['telegram']['bot_token'])
    app.database = Database(app)
    app.store = Store(app)
    
    await app.database.connect()
    
    await app.store.bot.connect(app)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    site = web.TCPSite(runner, config['web']['host'], config['web']['port'])
    await site.start()
    
    logger.info(f"Server started at http://{config['web']['host']}:{config['web']['port']}")
    logger.info("Bot is running...")
    
    try:
        await asyncio.Future()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        await app.store.bot.disconnect(app)
        await app.database.disconnect()

if __name__ == "__main__":
    asyncio.run(main())