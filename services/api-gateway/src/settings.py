from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    keycloak_issuer: str = "http://localhost:8080/realms/smart-money"
    keycloak_jwks_url: str = "http://keycloak:8080/realms/smart-money/protocol/openid-connect/certs"
    keycloak_client_id: str = "smart-money-api"
    data_service_url: str = "http://data-service:8000"
    smc_service_url: str = "http://smc-service:8010"
    decision_service_url: str = "http://decision-service:8020"
    execution_service_url: str = "http://execution-service:8030"
    analytics_service_url: str = "http://analytics-service:8040"
    backtest_service_url: str = "http://backtest-service:8080"
    exchange_service_url: str = "http://exchange-gateway:8070"
    request_timeout: float = 30.0
    redis_url: str = "redis://redis:6379"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
