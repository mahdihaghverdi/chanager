from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DEBUG: bool
    CHANAGER_TITLE: str
    CHANAGER_VERSION: str
    API_VERSION: str

    @property
    def PREFIX(self):
        return f"/api/{self.API_VERSION}"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
