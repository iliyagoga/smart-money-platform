from pydantic_settings import BaseSettings,SettingsConfigDict

class Settings(BaseSettings):
    model_config=SettingsConfigDict(env_file=".env",extra="ignore")
    database_url:str="postgresql://smart_money:smart_money@localhost:5432/smart_money"
    redis_url:str="redis://localhost:6379"
    swing_lookback:int=5
    scenario_min_confidence:float=.55
settings=Settings()
