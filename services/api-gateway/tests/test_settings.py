import pytest
from pydantic import ValidationError

from src.settings import Settings


def production(**changes):
    values={
      "environment":"production","keycloak_issuer":"https://auth.example.com/realms/smart-money",
      "cors_origins":"https://app.example.com","allowed_hosts":"api.example.com",
      "keycloak_admin_password":"a-long-random-admin-password",
      "redis_url":"redis://:a-long-random-redis-password@redis:6379",
      "postgres_password":"a-long-random-postgres-password",
    }
    values.update(changes);return Settings(_env_file=None,**values)


def test_secure_production_settings_are_accepted():
    assert production().environment=="production"


@pytest.mark.parametrize("changes",[
  {"keycloak_issuer":"http://auth.example.com/realms/smart-money"},
  {"keycloak_issuer":"https://user:password@auth.example.com/realms/smart-money"},
  {"cors_origins":"http://app.example.com"},
  {"cors_origins":"https://app.example.com/path"},
  {"allowed_hosts":"*"},
  {"allowed_hosts":""},
  {"keycloak_admin_password":"CHANGE_ME_USE_A_RANDOM_VALUE"},
  {"keycloak_admin_password":"too-short"},
  {"redis_url":"redis://redis:6379"},
  {"redis_url":"redis://:short@redis:6379"},
  {"redis_url":"redis://:CHANGE_ME_USE_A_RANDOM_VALUE@redis:6379"},
  {"postgres_password":"short"},
  {"postgres_password":"CHANGE_ME_USE_A_RANDOM_VALUE"},
])
def test_insecure_production_settings_fail_closed(changes):
    with pytest.raises(ValidationError):production(**changes)


@pytest.mark.parametrize("changes",[
  {"max_request_bytes":0},
  {"requests_per_minute":0},
  {"mutations_per_minute":0},
  {"expensive_requests_per_minute":0},
  {"websocket_max_connections":0},
  {"websocket_max_connections_per_user":0},
])
def test_resource_limits_cannot_be_disabled(changes):
    with pytest.raises(ValidationError):Settings(_env_file=None,**changes)
