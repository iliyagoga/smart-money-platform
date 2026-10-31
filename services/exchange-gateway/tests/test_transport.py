import asyncio
import json
import ssl
import subprocess
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.service import ExchangeGateway, ExchangeAmbiguousError
from src.settings import Settings
from src.transport import OKXClient, okx_ssl_context


def gateway():
    return ExchangeGateway(Settings(_env_file=None, okx_api_key="test-key",
                                    okx_secret_key="test-secret", okx_passphrase="test-pass"))


def acknowledgements():
    return [json.dumps({"event": "login", "code": "0"}),
            json.dumps({"event": "subscribe", "arg": {"channel": "orders"}})]


def test_tls_context_is_local_and_keeps_certificate_and_hostname_verification():
    context = okx_ssl_context()
    assert context.minimum_version == context.maximum_version == ssl.TLSVersion.TLSv1_2
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname
    assert ssl.create_default_context().maximum_version != ssl.TLSVersion.TLSv1_2
    assert gateway().okx_ws_ssl is not context


@pytest.mark.parametrize("channel", ["public", "business"])
def test_market_websocket_uses_okx_context_and_cleans_up_on_cancel(channel):
    async def check():
        service = gateway()
        ws = AsyncMock()
        ws.__aiter__.side_effect = asyncio.CancelledError
        manager = AsyncMock()
        manager.__aenter__.return_value = ws
        with patch("src.service.websockets.connect", return_value=manager) as connect:
            with pytest.raises(asyncio.CancelledError):
                await service.loop(channel, "wss://ws.okx.com/ws/v5/" + channel)
        assert connect.call_args.kwargs["ssl"] is service.okx_ws_ssl
        assert connect.call_args.kwargs["open_timeout"] == 20
        assert not service.connected[channel]
        assert channel not in service.websockets
    asyncio.run(check())


def test_private_auth_waits_for_login_before_subscribing():
    async def check():
        service = gateway()
        ws = AsyncMock()
        ws.recv.side_effect = acknowledgements()
        await service.authenticate_private(ws)
        messages = [json.loads(call.args[0]) for call in ws.send.await_args_list]
        assert messages[0]["op"] == "login"
        assert messages[0]["args"][0]["apiKey"] == "test-key"
        assert messages[1] == {"op": "subscribe", "args": [{"channel": "orders", "instType": "ANY"}]}
        assert not service.trading_ready
    asyncio.run(check())


@pytest.mark.parametrize("messages,expected,sends", [
    ([{"event": "login", "code": "60009", "msg": "test-secret"}], "login rejected: code=60009", 1),
    ([{"event": "login", "code": "0"}, {"event": "error", "code": "60012"}],
     "subscription rejected: code=60012", 2),
])
def test_private_auth_rejections_never_enable_trading(messages, expected, sends):
    async def check():
        service = gateway()
        ws = AsyncMock()
        ws.recv.side_effect = [json.dumps(msg) for msg in messages]
        with pytest.raises(ValueError, match=expected) as error:
            await service.authenticate_private(ws)
        assert "test-secret" not in str(error.value)
        assert ws.send.await_count == sends
        assert not service.trading_ready
    asyncio.run(check())


@pytest.mark.parametrize("stage", ["login", "subscribe"])
def test_private_auth_timeout_reconnects_without_reconciliation(caplog, stage):
    async def check():
        service = gateway()
        service.reconcile_orders = AsyncMock()
        ws = AsyncMock()
        received = 0

        async def receive():
            nonlocal received
            received += 1
            if stage == "subscribe" and received == 1:
                return acknowledgements()[0]
            await asyncio.Future()

        ws.recv.side_effect = receive
        manager = AsyncMock()
        manager.__aenter__.return_value = ws
        timeout = asyncio.timeout
        with patch("src.service.websockets.connect", return_value=manager), \
             patch("src.service.asyncio.timeout", side_effect=lambda seconds: timeout(.001)), \
             patch("src.service.asyncio.sleep", side_effect=asyncio.CancelledError):
            with pytest.raises(asyncio.CancelledError):
                await service.private_loop()
        service.reconcile_orders.assert_not_awaited()
        assert not service.trading_ready and not service.private_subscribed
        assert not service.connected["private"]
        assert "private login/subscribe: TimeoutError" in service.last_error
    asyncio.run(check())
    assert "phase=login/subscribe" in caplog.text
    assert "test-secret" not in caplog.text


def test_health_requires_private_reconciliation_and_fresh_market_data():
    from fastapi import HTTPException
    from src import app
    from time import monotonic

    async def check():
        service = gateway()
        service.active_symbols = ["BTC-USDT-SWAP"]
        service.connected["business"] = True
        service.last_m1_by_symbol["BTC-USDT-SWAP"] = monotonic()
        settings = Settings(_env_file=None, market_data_enabled=True, trading_enabled=True,
                            okx_api_key="test-key", okx_secret_key="test-secret", okx_passphrase="test-pass")
        with patch.object(app, "settings", settings), patch.object(app, "service", service):
            with pytest.raises(HTTPException) as error:
                await app.health()
            assert error.value.status_code == 503
            service.private_ready.set()
            with pytest.raises(HTTPException):
                await app.health()
            service.reconciled = True
            assert (await app.health())["status"] == "UP"
            service.last_m1_by_symbol["BTC-USDT-SWAP"] -= 121
            with pytest.raises(HTTPException):
                await app.health()
    asyncio.run(check())


@pytest.mark.parametrize("fail_initial_reconciliation", [False, True])
def test_private_disconnect_reauthenticates_and_reconciles(fail_initial_reconciliation):
    async def check():
        service = gateway()
        ws = AsyncMock()
        ws.recv.side_effect = acknowledgements() * 2
        states = []

        async def reconcile():
            assert service.private_subscribed and service.connected["private"]
            assert not service.private_ready.is_set()
            if fail_initial_reconciliation and not states:
                raise httpx.ConnectTimeout("test timeout")
            service.reconciled = True

        service.reconcile_orders = AsyncMock(side_effect=reconcile)

        def stream():
            async def messages():
                states.append(service.trading_ready)
                if len(states) == 2:
                    raise asyncio.CancelledError
                if False:
                    yield
            return messages()

        ws.__aiter__.side_effect = stream
        manager = AsyncMock()
        manager.__aenter__.return_value = ws
        with patch("src.service.websockets.connect", return_value=manager) as connect, \
             patch("src.service.asyncio.sleep", new=AsyncMock()):
            with pytest.raises(asyncio.CancelledError):
                await service.private_loop()
        assert connect.call_count == 2
        assert all(call.kwargs["ssl"] is service.okx_ws_ssl for call in connect.call_args_list)
        assert service.reconcile_orders.await_count == 2
        assert states == [not fail_initial_reconciliation, True]
        assert [json.loads(call.args[0])["op"] for call in ws.send.await_args_list] == [
            "login", "subscribe", "login", "subscribe"]
        assert not service.trading_ready and not service.reconciled
        assert not service.private_subscribed and not service.connected["private"]
        assert "private" not in service.websockets
    asyncio.run(check())


def test_rest_errors_have_safe_diagnostics_and_no_request_replay(caplog):
    async def check():
        service = gateway()
        service.okx_client = OKXClient()
        error = httpx.ConnectTimeout("test-secret")
        error.__cause__ = TimeoutError()
        try:
            with patch.object(httpx.AsyncClient, "request", new=AsyncMock(side_effect=error)) as request:
                with pytest.raises(ExchangeAmbiguousError):
                    await service.private("GET", "/api/v5/account/positions?instType=SWAP")
                assert request.await_count == 1
        finally:
            await service.okx_client.aclose()
    asyncio.run(check())
    assert "path=/api/v5/account/positions" in caplog.text
    assert "ConnectTimeout <- TimeoutError" in caplog.text
    assert "test-secret" not in caplog.text and "instType" not in caplog.text


def test_rest_client_preserves_proxy_and_no_proxy_routing(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:8888")
    monkeypatch.setenv("NO_PROXY", "localhost")

    async def check():
        async with OKXClient() as client:
            # Verify HTTPX routing without contacting a proxy or exchange.
            direct = client._transport_for_url(httpx.URL("https://localhost"))
            proxied = client._transport_for_url(httpx.URL("https://www.okx.com"))
            assert direct is client._transport
            assert proxied is not direct
    asyncio.run(check())


@pytest.fixture
def certificate(tmp_path):
    cert, key = tmp_path / "cert.pem", tmp_path / "key.pem"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                    "-keyout", str(key), "-out", str(cert), "-days", "1", "-subj", "/CN=localhost",
                    "-addext", "subjectAltName=DNS:localhost"], check=True, capture_output=True)
    return cert, key


@pytest.mark.parametrize("trusted,hostname,works", [(True, "localhost", True),
                                                    (False, "localhost", False),
                                                    (True, "127.0.0.1", False)])
def test_real_rest_tls12_handshake_checks_trust_and_hostname(certificate, trusted, hostname, works):
    async def check():
        cert, key = certificate
        server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_context.load_cert_chain(cert, key)
        server_context.minimum_version = server_context.maximum_version = ssl.TLSVersion.TLSv1_2
        versions = []

        async def respond(reader, writer):
            versions.append(writer.get_extra_info("ssl_object").version())
            try:
                await reader.readuntil(b"\r\n\r\n")
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}")
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_server(respond, "127.0.0.1", 0, ssl=server_context)
        context = okx_ssl_context()
        if trusted:
            context.load_verify_locations(cafile=str(cert))
        try:
            with patch("src.transport.okx_ssl_context", return_value=context):
                async with OKXClient() as client:
                    url = f"https://{hostname}:{server.sockets[0].getsockname()[1]}/"
                    if works:
                        assert (await client.get(url)).status_code == 200
                        assert versions == ["TLSv1.2"]
                    else:
                        with pytest.raises(httpx.ConnectError, match="CERTIFICATE_VERIFY_FAILED"):
                            await client.get(url)
        finally:
            server.close()
            await server.wait_closed()
    asyncio.run(check())
