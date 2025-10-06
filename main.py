import os
import logging
from aiohttp.web import run_app
from app.web.app import setup_app

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

if __name__ == "__main__":
    run_app(
        setup_app(
            config_path=os.path.join(
                os.path.dirname(os.path.realpath(__file__)), "etc", "config.yaml"
            )
        )
    )