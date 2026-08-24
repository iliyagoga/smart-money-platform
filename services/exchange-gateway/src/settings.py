from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    okx_rest_url:str="https://www.okx.com"
    okx_public_ws_url:str="wss://ws.okx.com:8443/ws/v5/public"
    okx_business_ws_url:str="wss://ws.okx.com:8443/ws/v5/business"
    okx_api_key:str=""; okx_secret_key:str=""; okx_passphrase:str=""
    okx_demo:bool=True; market_data_enabled:bool=False
    symbols:str="BTC-USDT-SWAP"; timeframes:str="M1,M5,M15,M30,H1,H4,D1"
    data_service_url:str="http://data-service:8000"
    smc_service_url:str="http://smc-service:8010"
    database_url:str="postgresql://smart_money:smart_money_local_password@postgres:5432/smart_money"
    history_concurrency:int=2
    model_config=SettingsConfigDict(env_file=".env",extra="ignore")
settings=Settings()
