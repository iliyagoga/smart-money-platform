from contextlib import asynccontextmanager
from uuid import uuid4

import httpx
from redis.asyncio import Redis
from fastapi import FastAPI, HTTPException, Request,WebSocket
from pydantic import BaseModel, Field
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import ClientDisconnect

from .security import TokenVerifier, authorize
from .settings import settings
from .websocket import WebSocketBridge
from .keycloak_admin import KeycloakAdmin, KeycloakAdminError, PLATFORM_ROLES


SERVICE_URLS = {
    "data": settings.data_service_url,
    "elliott": settings.elliott_service_url,
    "decision": settings.decision_service_url,
    "execution": settings.execution_service_url,
    "analytics": settings.analytics_service_url,
    "exchange": settings.exchange_service_url,
    "backtest": settings.backtest_service_url,
}
verifier = TokenVerifier(settings.keycloak_issuer, settings.keycloak_jwks_url, settings.keycloak_client_id)
keycloak_admin = KeycloakAdmin(
    settings.keycloak_admin_url,
    settings.keycloak_realm,
    settings.keycloak_admin_username,
    settings.keycloak_admin_password,
)


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    email: str = Field(default="", max_length=255)
    first_name: str = Field(default="", max_length=255)
    last_name: str = Field(default="", max_length=255)
    password: str = Field(min_length=8, max_length=255)
    temporary_password: bool = True
    roles: set[str]


class UpdateUserRequest(BaseModel):
    enabled: bool
    roles: set[str]


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.client = httpx.AsyncClient(timeout=settings.request_timeout)
    app.state.redis = Redis.from_url(settings.redis_url,decode_responses=True);await app.state.redis.ping();app.state.ws_bridge=WebSocketBridge(app.state.redis,verifier)
    yield
    await app.state.client.aclose()
    await app.state.redis.aclose()


app = FastAPI(title="Elliott Wave API Gateway", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=["http://localhost:3000"],allow_credentials=True,allow_methods=["*"],allow_headers=["Authorization","Content-Type","X-Correlation-ID"])


@app.get("/health")
async def health():
    return {"status": "UP","websocket_connections":app.state.ws_bridge.connections}

@app.websocket("/ws")
async def websocket_endpoint(websocket:WebSocket):await websocket.app.state.ws_bridge.serve(websocket)


@app.get("/api/v1/me")
async def me(request: Request):
    principal = await verifier.authenticate(request)
    return {"id": principal.subject, "username": principal.username, "roles": sorted(principal.roles)}


def validate_platform_roles(roles: set[str]) -> None:
    if not roles:
        raise HTTPException(status_code=422, detail="Назначьте хотя бы одну роль")
    unknown = roles - PLATFORM_ROLES
    if unknown:
        raise HTTPException(status_code=422, detail=f"Неизвестные роли: {', '.join(sorted(unknown))}")


async def require_admin(request: Request):
    principal = await verifier.authenticate(request)
    if "admin" not in principal.roles:
        raise HTTPException(status_code=403, detail="Admin role is required")
    return principal


@app.get("/api/v1/admin/users")
async def list_users(request: Request):
    await require_admin(request)
    try:
        return {"users": await keycloak_admin.list_users(request.app.state.client)}
    except KeycloakAdminError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@app.post("/api/v1/admin/users", status_code=201)
async def create_user(payload: CreateUserRequest, request: Request):
    await require_admin(request)
    validate_platform_roles(payload.roles)
    try:
        return await keycloak_admin.create_user(request.app.state.client, payload.model_dump())
    except KeycloakAdminError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@app.patch("/api/v1/admin/users/{user_id}")
async def update_user(user_id: str, payload: UpdateUserRequest, request: Request):
    principal = await require_admin(request)
    validate_platform_roles(payload.roles)
    if principal.subject == user_id and (not payload.enabled or "admin" not in payload.roles):
        raise HTTPException(status_code=400, detail="Нельзя заблокировать себя или снять у себя роль admin")
    try:
        return await keycloak_admin.update_user(
            request.app.state.client, user_id, payload.enabled, payload.roles,
        )
    except KeycloakAdminError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


async def proxy(service: str, path: str, request: Request) -> Response:
    principal = await verifier.authenticate(request)
    authorize(principal, request.method, service, path)
    base_url = SERVICE_URLS.get(service)
    if not base_url:
        raise HTTPException(status_code=404, detail="Unknown service")
    correlation_id = request.headers.get("x-correlation-id", str(uuid4()))
    headers = {
        "content-type": request.headers.get("content-type", "application/json"),
        "x-correlation-id": correlation_id,
        "x-user-id": principal.subject,
        "x-user-roles": ",".join(sorted(principal.roles)),
    }
    try:
        body = await request.body()
        upstream = await request.app.state.client.request(
            request.method,
            f"{base_url}/{path}",
            params=request.query_params,
            content=body,
            headers=headers,
        )
    except ClientDisconnect as exc:
        raise HTTPException(status_code=499, detail="Client closed request") from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Upstream {service} is unavailable") from exc
    excluded = {"content-length", "connection", "transfer-encoding", "content-encoding"}
    response_headers = {k: v for k, v in upstream.headers.items() if k.lower() not in excluded}
    response_headers["x-correlation-id"] = correlation_id
    return Response(upstream.content, status_code=upstream.status_code, headers=response_headers)


@app.api_route("/api/v1/{service}/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def service_proxy(service: str, path: str, request: Request):
    return await proxy(service, path, request)
