from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql://smart_money:smart_money_local_password@postgres:5432/smart_money"
    data_service_url: str = "http://data-service:8000"
    max_candles: int = 1000000
    scenario_template_dir: str = "/app/scenario-templates"
    minio_endpoint: str = "http://minio:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "CHANGE_ME_MINIO"
    job_concurrency: int = 2
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
