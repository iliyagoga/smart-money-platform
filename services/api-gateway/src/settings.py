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
    request_timeout: float = 30.0
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

