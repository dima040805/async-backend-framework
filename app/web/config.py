from dataclasses import dataclass
from typing import Optional
import typing
import yaml

if typing.TYPE_CHECKING:
    from app.web.app import Application


@dataclass
class SessionConfig:
    key: str


@dataclass
class AdminConfig:
    email: str
    password: str


@dataclass
class TelegramConfig:
    token: str
    polling_interval: int = 1


@dataclass
class DatabaseConfig:
    host: str = "localhost"
    port: int = 5432
    user: str = "postgres"
    password: str = "postgres"
    database: str = "project"


@dataclass
class Config:
    session: SessionConfig = None
    admin: AdminConfig = None
    telegram: TelegramConfig = None
    database: DatabaseConfig = None
    debug: bool = False


def setup_config(app: "Application", config_path: str):
    with open(config_path, "r") as f:
        raw_config = yaml.safe_load(f)

    app.config = Config(
        session=SessionConfig(**raw_config["session"]), 
        admin=AdminConfig(**raw_config["admin"]),        
        telegram=TelegramConfig(**raw_config["telegram"]),
        database=DatabaseConfig(**raw_config["database"]),
        debug=raw_config.get("debug", False)
    )