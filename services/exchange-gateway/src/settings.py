from urllib.parse import urlsplit

from pydantic import Field,model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    okx_rest_url:str="https://www.okx.com"
    okx_public_ws_url:str="wss://ws.okx.com/ws/v5/public"
    okx_business_ws_url:str="wss://ws.okx.com/ws/v5/business"
    okx_private_ws_url:str|None=None
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
        expected_host="wspap.okx.com" if self.okx_demo else "ws.okx.com"
        if not self.okx_private_ws_url:
            self.okx_private_ws_url=f"wss://{expected_host}/ws/v5/private"
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
            if (endpoint.scheme!="wss" or not endpoint.hostname or endpoint.username or endpoint.password
                    or endpoint.port not in (None,443)):
                raise ValueError(f"{name} must use WSS")
        private=urlsplit(self.okx_private_ws_url)
        if private.hostname!=expected_host or private.path!="/ws/v5/private":
            raise ValueError(f"OKX_PRIVATE_WS_URL must use {expected_host}/ws/v5/private for this account mode")
        credentials=(self.okx_api_key,self.okx_secret_key,self.okx_passphrase)
        if any(credentials) and not all(credentials):raise ValueError("OKX credentials must be configured together")
        if self.trading_enabled and not all(credentials):raise ValueError("OKX trading requires API credentials")
        if self.trading_enabled and not self.market_data_enabled:raise ValueError("OKX trading requires live market data")
        if self.margin_mode not in {"cross","isolated"}:raise ValueError("MARGIN_MODE must be cross or isolated")
        return self
settings=Settings()
