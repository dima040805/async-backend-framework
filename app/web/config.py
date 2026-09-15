import os
import typing
from dataclasses import dataclass

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


ENV_OVERRIDES = {
    ("telegram", "token"): "TELEGRAM_TOKEN",
    ("session", "key"): "SESSION_KEY",
    ("admin", "email"): "ADMIN_EMAIL",
    ("admin", "password"): "ADMIN_PASSWORD",
    ("database", "host"): "DATABASE_HOST",
    ("database", "user"): "DATABASE_USER",
    ("database", "password"): "DATABASE_PASSWORD",
    ("database", "database"): "DATABASE_NAME",
}


def apply_env_overrides(raw_config: dict) -> dict:
    for (section, key), env_name in ENV_OVERRIDES.items():
        value = os.environ.get(env_name)
        if value:
            raw_config.setdefault(section, {})[key] = value
    return raw_config


def setup_config(app: "Application", config_path: str):
    with open(config_path, "r") as f:
        raw_config = apply_env_overrides(yaml.safe_load(f))

    app.config = Config(
        session=SessionConfig(**raw_config["session"]),
        admin=AdminConfig(**raw_config["admin"]),
        telegram=TelegramConfig(**raw_config["telegram"]),
        database=DatabaseConfig(**raw_config["database"]),
        debug=raw_config.get("debug", False),
    )
