import logging
import os

from aiohttp.web import run_app

from app.web.app import setup_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.dialects").setLevel(logging.WARNING)

logging.getLogger("app").setLevel(logging.INFO)
logging.getLogger("app.store.bot").setLevel(logging.INFO)
logging.getLogger("app.store.accessors").setLevel(logging.INFO)

if __name__ == "__main__":
    logging.info("🚀 Starting 100к1 Telegram Bot...")
    run_app(
        setup_app(
            config_path=os.path.join(
                os.path.dirname(os.path.realpath(__file__)),
                "etc",
                "config.yaml",
            )
        )
    )
