from urllib.parse import urlsplit

from pydantic import Field,model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    okx_rest_url:str="https://www.okx.com"
    okx_public_ws_url:str="wss://ws.okx.com:8443/ws/v5/public"
    okx_business_ws_url:str="wss://ws.okx.com:8443/ws/v5/business"
    okx_private_ws_url:str="wss://wspap.okx.com:8443/ws/v5/private"
    okx_api_key:str=""; okx_secret_key:str=""; okx_passphrase:str=""
    okx_demo:bool=True; market_data_enabled:bool=False
    trading_enabled:bool=False; margin_mode:str="cross"
    symbols:str="BTC-USDT-SWAP"; timeframes:str="M1,M5,M15,M30,H1,H4,D1"
    data_service_url:str="http://data-service:8000"
    elliott_service_url:str="http://elliott-service:8010"
    database_url:str="postgresql://smart_money:smart_money_local_password@postgres:5432/smart_money"
    redis_url:str="redis://redis:6379"
    history_concurrency:int=Field(default=2,ge=1,le=20)
    model_config=SettingsConfigDict(env_file=".env",extra="ignore")
    @model_validator(mode="after")
    def secure_exchange_transport(self):
        rest=urlsplit(self.okx_rest_url)
        if (rest.scheme!="https" or not rest.hostname or rest.username or rest.password
                or rest.query or rest.fragment or rest.path not in {"","/"}):
            raise ValueError("OKX_REST_URL must be an HTTPS origin")
        for name,value in {
            "OKX_PUBLIC_WS_URL":self.okx_public_ws_url,
            "OKX_BUSINESS_WS_URL":self.okx_business_ws_url,
            "OKX_PRIVATE_WS_URL":self.okx_private_ws_url,
        }.items():
            endpoint=urlsplit(value)
            if endpoint.scheme!="wss" or not endpoint.hostname or endpoint.username or endpoint.password:
                raise ValueError(f"{name} must use WSS")
        credentials=(self.okx_api_key,self.okx_secret_key,self.okx_passphrase)
        if any(credentials) and not all(credentials):raise ValueError("OKX credentials must be configured together")
        if self.trading_enabled and not all(credentials):raise ValueError("OKX trading requires API credentials")
        if self.margin_mode not in {"cross","isolated"}:raise ValueError("MARGIN_MODE must be cross or isolated")
        return self
settings=Settings()
