from pydantic_settings import BaseSettings,SettingsConfigDict
class Settings(BaseSettings):
    model_config=SettingsConfigDict(env_file=".env",extra="ignore")
    database_url:str="postgresql://smart_money:smart_money@localhost:5432/smart_money"
    redis_url:str="redis://localhost:6379"
    confidence_threshold:float=.60
    conflict_min_delta:float=.10
    default_capital:float=10000
    minio_endpoint:str="http://minio:9000"
    minio_access_key:str="minioadmin"
    minio_secret_key:str="minioadmin"
    model_bucket:str="models"
    adaptive_model_weight:float=.35
settings=Settings()
