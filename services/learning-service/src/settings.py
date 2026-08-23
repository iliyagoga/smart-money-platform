from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql://smart_money:smart_money@postgres:5432/smart_money"
    redis_url: str = "redis://redis:6379"
    minio_endpoint: str = "http://minio:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    model_bucket: str = "models"
    minimum_training_samples: int = 20
    model_type: str = "LOGREG"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

