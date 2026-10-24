import asyncio
from time import monotonic, time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from unittest.mock import AsyncMock

from src.security import Principal, TokenVerifier, authorize


def principal(*roles):
    return Principal("id", "user", frozenset(roles), {})


def test_viewer_can_read():
    authorize(principal("viewer"), "GET", "execution", "/positions")


def test_viewer_cannot_trade():
    with pytest.raises(HTTPException) as error:
        authorize(principal("viewer"), "POST", "execution", "/positions/id/close")
    assert error.value.status_code == 403


def test_trader_can_trade_but_not_ingest():
    authorize(principal("trader"), "POST", "execution", "/orders")
    with pytest.raises(HTTPException):
        authorize(principal("trader"), "POST", "data", "/internal/ingest/candles")


def test_only_admin_changes_risk_config():
    with pytest.raises(HTTPException):
        authorize(principal("trader"), "PATCH", "decision", "/risk/config")
    authorize(principal("admin"), "PATCH", "decision", "/risk/config")


def test_only_admin_can_emulate_elliott_signal():
    with pytest.raises(HTTPException):
        authorize(principal("trader"), "POST", "decision", "/signals/simulate-elliott")
    authorize(principal("admin"), "POST", "decision", "/signals/simulate-elliott")


def test_viewer_can_run_backtest_but_only_admin_manages_assets():
    authorize(principal("viewer"), "POST", "backtest", "/backtests")
    with pytest.raises(HTTPException):
        authorize(principal("trader"), "POST", "backtest", "/assets")
    authorize(principal("admin"), "POST", "backtest", "/assets")


def test_only_admin_can_start_exchange_ingestion_or_reload_symbols():
    for path in ("/exchange/sync","/exchange/reload-symbols"):
        with pytest.raises(HTTPException):
            authorize(principal("trader"),"POST","exchange",path)
        authorize(principal("admin"),"POST","exchange",path)


@pytest.mark.parametrize(("method","service","path"),[
    ("POST","data","/market/../internal/ingest/candles"),
    ("PATCH","decision","/risk/../risk/config"),
    ("GET","exchange","/exchange/orders/../account/balance"),
    ("POST","backtest","/backtests/../datasets"),
])
def test_dot_segments_cannot_bypass_endpoint_authorization(method,service,path):
    for role in ("viewer","trader","admin"):
        with pytest.raises(HTTPException) as error:
            authorize(principal(role),method,service,path)
        assert error.value.status_code==404


@pytest.mark.parametrize(("service","path"),[
    ("data","/actuator/prometheus"),
    ("data","/swagger-ui/index.html"),
    ("exchange","/health"),
    ("execution","/docs"),
])
def test_operational_and_documentation_endpoints_are_not_exposed(service,path):
    for role in ("viewer","admin"):
        with pytest.raises(HTTPException) as error:
            authorize(principal(role),"GET",service,path)
        assert error.value.status_code==404


def test_token_requires_expiry_and_well_formed_security_claims():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier = TokenVerifier("https://auth.example.com/realms/smart-money", "unused", "smart-money-api")
    verifier._keys["test-key"] = private_key.public_key()
    verifier._loaded_at = monotonic()
    claims = {
        "iss": verifier.issuer,
        "sub": "user-id",
        "iat": int(time()),
        "exp": int(time()) + 60,
        "azp": verifier.client_id,
        "typ": "Bearer",
        "realm_access": {"roles": ["viewer"]},
    }

    token = jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test-key"})
    assert asyncio.run(verifier.verify(token)).subject == "user-id"

    for broken_claims in (
        {key: value for key, value in claims.items() if key != "exp"},
        {**claims, "realm_access": "viewer"},
        {**claims, "sub": ""},
    ):
        broken = jwt.encode(broken_claims, private_key, algorithm="RS256", headers={"kid": "test-key"})
        with pytest.raises(HTTPException) as error:
            asyncio.run(verifier.verify(broken))
        assert error.value.status_code == 401


def test_unknown_signing_key_does_not_trigger_unbounded_jwks_refreshes():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier = TokenVerifier("https://auth.example.com/realms/smart-money", "unused", "smart-money-api")
    verifier._refresh = AsyncMock()
    token = jwt.encode({"sub":"id"}, private_key, algorithm="RS256", headers={"kid":"unknown"})
    for _ in range(2):
        with pytest.raises(HTTPException) as error:
            asyncio.run(verifier.verify(token))
        assert error.value.status_code == 401
    verifier._refresh.assert_awaited_once()


def test_expired_jwks_cache_stops_trusting_removed_keys():
    async def check():
        verifier=TokenVerifier("issuer","unused","client")
        verifier._keys={"old":object()}
        verifier._loaded_at=monotonic()-verifier.JWKS_TTL_SECONDS-1
        async def refresh():
            verifier._keys={"new":object()}
            verifier._loaded_at=monotonic()
        verifier._refresh=AsyncMock(side_effect=refresh)
        with pytest.raises(jwt.InvalidTokenError):await verifier._key("old")
        assert await verifier._key("new") is verifier._keys["new"]
        verifier._refresh.assert_awaited_once()
    asyncio.run(check())


def test_jwks_refresh_replaces_same_key_id_once_for_concurrent_requests():
    async def check():
        verifier=TokenVerifier("issuer","unused","client")
        old_key=object();new_key=object()
        verifier._keys={"key":old_key}
        verifier._loaded_at=monotonic()-verifier.JWKS_TTL_SECONDS-1
        async def refresh():
            await asyncio.sleep(0)
            verifier._keys={"key":new_key}
            verifier._loaded_at=monotonic()
        verifier._refresh=AsyncMock(side_effect=refresh)
        assert await asyncio.gather(verifier._key("key"),verifier._key("key"))==[new_key,new_key]
        verifier._refresh.assert_awaited_once()
    asyncio.run(check())


def test_expired_jwks_cache_fails_closed_and_limits_failed_refreshes():
    async def check():
        verifier=TokenVerifier("issuer","unused","client")
        verifier._keys={"key":object()}
        verifier._loaded_at=monotonic()-verifier.JWKS_TTL_SECONDS-1
        verifier._refresh=AsyncMock(side_effect=jwt.InvalidTokenError("JWKS unavailable"))
        for _ in range(2):
            with pytest.raises(jwt.InvalidTokenError):await verifier._key("key")
        verifier._refresh.assert_awaited_once()
    asyncio.run(check())
