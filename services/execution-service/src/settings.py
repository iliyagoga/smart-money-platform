from pydantic_settings import BaseSettings,SettingsConfigDict
class Settings(BaseSettings):
    model_config=SettingsConfigDict(env_file=".env",extra="ignore")
    database_url:str="postgresql://smart_money:smart_money@localhost:5432/smart_money";redis_url:str="redis://localhost:6379"
    exchange_service_url:str="http://exchange-gateway:8070"
    execution_mode:str="paper";stream_group:str="execution-service";consumer_name:str="execution-1"
settings=Settings()
