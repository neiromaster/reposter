from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Example: API keys
    # vk_api_key: str
    # telegram_bot_token: str


settings = Settings()
