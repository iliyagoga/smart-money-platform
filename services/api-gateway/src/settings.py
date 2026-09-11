from urllib.parse import urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    environment: str = "development"
    keycloak_issuer: str = "http://localhost:8080/realms/smart-money"
    keycloak_jwks_url: str = "http://keycloak:8080/realms/smart-money/protocol/openid-connect/certs"
    keycloak_client_id: str = "smart-money-api"
    keycloak_admin_url: str = "http://keycloak:8080"
    keycloak_realm: str = "smart-money"
    keycloak_admin_username: str = "admin"
    keycloak_admin_password: str = "CHANGE_ME"
    data_service_url: str = "http://data-service:8000"
    elliott_service_url: str = "http://elliott-service:8010"
    decision_service_url: str = "http://decision-service:8020"
    execution_service_url: str = "http://execution-service:8030"
    analytics_service_url: str = "http://analytics-service:8040"
    backtest_service_url: str = "http://backtest-service:8080"
    exchange_service_url: str = "http://exchange-gateway:8070"
    request_timeout: float = Field(default=30.0, gt=0, le=300)
    max_request_bytes: int = Field(default=2_000_000, ge=1024, le=50_000_000)
    requests_per_minute: int = Field(default=120, ge=1, le=100_000)
    mutations_per_minute: int = Field(default=30, ge=1, le=10_000)
    expensive_requests_per_minute: int = Field(default=5, ge=1, le=1_000)
    cors_origins: str = "http://localhost:3000"
    allowed_hosts: str = "localhost,127.0.0.1,testserver"
    expose_docs: bool = False
    websocket_max_connections: int = Field(default=200, ge=1, le=10_000)
    websocket_max_connections_per_user: int = Field(default=5, ge=1, le=100)
    redis_url: str = "redis://redis:6379"
    postgres_password: str = ""
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def production_security(self):
        if self.environment.lower()=="production":
            issuer=urlsplit(self.keycloak_issuer)
            if (issuer.scheme!="https" or not issuer.hostname or issuer.username or issuer.password
                    or issuer.query or issuer.fragment):
                raise ValueError("production KEYCLOAK_ISSUER must use HTTPS")
            origins=[item.strip() for item in self.cors_origins.split(",") if item.strip()]
            parsed_origins=[urlsplit(item) for item in origins]
            if not origins or any(
                item.scheme!="https" or not item.hostname or item.username or item.password
                or item.path not in {"","/"} or item.query or item.fragment
                for item in parsed_origins
            ):
                raise ValueError("production CORS_ORIGINS must contain HTTPS origins")
            if (len(self.keycloak_admin_password)<16
                    or self.keycloak_admin_password.upper().startswith("CHANGE_ME")):
                raise ValueError("production Keycloak admin password is not configured")
            hosts={item.strip() for item in self.allowed_hosts.split(",") if item.strip()}
            if not hosts or "*" in hosts or any(
                any(character in item for character in "/@ \\") or "://" in item for item in hosts
            ):
                raise ValueError("production ALLOWED_HOSTS must contain explicit hostnames")
            redis=urlsplit(self.redis_url)
            if (redis.scheme not in {"redis","rediss"} or not redis.hostname
                    or len(redis.password or "")<16 or (redis.password or "").upper().startswith("CHANGE_ME")):
                raise ValueError("production REDIS_URL must contain a strong password")
            if len(self.postgres_password)<16 or self.postgres_password.upper().startswith("CHANGE_ME"):
                raise ValueError("production POSTGRES_PASSWORD must contain a strong password")
        return self


settings = Settings()
