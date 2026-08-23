from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql://smart_money:smart_money_local_password@postgres:5432/smart_money"
    data_service_url: str = "http://data-service:8000"
    max_candles: int = 10000
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
