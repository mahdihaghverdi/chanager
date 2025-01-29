from enum import StrEnum, auto

from pydantic_settings import BaseSettings, SettingsConfigDict


class LogLevels(StrEnum):
    INFO = auto()
    DEBUG = auto()


class Settings(BaseSettings):
    CHANAGER_IP: str
    CHANAGER_WAIT_TO_CONNECT: int
    CHANAGER_CLIENT_HEALTH_CHECK_INTERVAL: int
    LOGLEVEL: LogLevels

    # ports
    RLS_PORT: int
    ALS_PORT: int | None = None
    CMD_PORT: int

    # client
    CLIENT_NAME: str | None = None
    CLIENT_CLS_PORT: int | None = None
    CLIENT_IP: str | None = None
    CLIENT_ALERT_INTERVAL: int | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
