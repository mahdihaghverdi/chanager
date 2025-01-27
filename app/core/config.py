from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    CHANAGER_IP: str

    # ports
    RLS_PORT: int
    ALS_PORT: int | None = None

    # client
    CLIENT_NAME: str | None = None
    CLIENT_CLS_PORT: int | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
