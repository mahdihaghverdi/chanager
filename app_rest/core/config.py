from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # both
    DEBUG: bool
    API_VERSION: str

    # changer
    CHANAGER_IP: str | None = None
    CHANAGER_PORT: int | None = None
    CHANAGER_TITLE: str | None = None
    CHANAGER_VERSION: str | None = None

    # client
    CLIENT_TITLE: str | None = None
    CLIENT_VERSION: str | None = None
    CLIENT_IP: str | None = None
    CLIENT_PORT: int | None = None

    @property
    def PREFIX(self):
        return f"/api/{self.API_VERSION}"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
