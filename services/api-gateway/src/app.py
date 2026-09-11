from contextlib import asynccontextmanager
import re
from time import time
from uuid import uuid4

import httpx
from redis.asyncio import Redis
from fastapi import FastAPI, HTTPException, Request,WebSocket
from pydantic import BaseModel, Field
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
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
cors_origins=tuple(item.strip().rstrip("/") for item in settings.cors_origins.split(",") if item.strip())
allowed_hosts=tuple(item.strip() for item in settings.allowed_hosts.split(",") if item.strip())
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
    password: str = Field(min_length=12, max_length=255)
    temporary_password: bool = True
    roles: set[str]


class UpdateUserRequest(BaseModel):
    enabled: bool
    roles: set[str]


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.client = httpx.AsyncClient(timeout=settings.request_timeout)
    app.state.redis = Redis.from_url(settings.redis_url,decode_responses=True);await app.state.redis.ping()
    app.state.ws_bridge=WebSocketBridge(app.state.redis,verifier,cors_origins,
      settings.websocket_max_connections,settings.websocket_max_connections_per_user)
    yield
    await app.state.client.aclose()
    await app.state.redis.aclose()


app = FastAPI(title="Elliott Wave API Gateway", version="1.0.0", lifespan=lifespan,
              docs_url="/docs" if settings.expose_docs else None,
              redoc_url="/redoc" if settings.expose_docs else None,
              openapi_url="/openapi.json" if settings.expose_docs else None)
if allowed_hosts:app.add_middleware(TrustedHostMiddleware,allowed_hosts=list(allowed_hosts))
if cors_origins:app.add_middleware(CORSMiddleware,allow_origins=list(cors_origins),allow_credentials=False,
  allow_methods=["GET","POST","PUT","PATCH","DELETE","OPTIONS"],
  allow_headers=["Authorization","Content-Type","X-Correlation-ID"])

@app.middleware("http")
async def security_headers(request:Request,call_next):
    content_length=request.headers.get("content-length")
    if content_length:
        try:too_large=int(content_length)>settings.max_request_bytes
        except ValueError:too_large=True
        if too_large:return Response("Request body is too large",status_code=413,media_type="text/plain")
    response=await call_next(request)
    response.headers["X-Content-Type-Options"]="nosniff"
    response.headers["X-Frame-Options"]="DENY"
    response.headers["Referrer-Policy"]="no-referrer"
    response.headers["Permissions-Policy"]="camera=(), microphone=(), geolocation=()"
    response.headers["Cache-Control"]="no-store"
    return response

async def check_rate_limit(request:Request,subject:str,category:str="read"):
    limit={"read":settings.requests_per_minute,"mutation":settings.mutations_per_minute,
           "expensive":settings.expensive_requests_per_minute}[category]
    key=f"rate-limit:{subject}:{category}:{int(time()//60)}"
    count=await request.app.state.redis.incr(key)
    if count==1:await request.app.state.redis.expire(key,61)
    if count>limit:raise HTTPException(status_code=429,detail="Rate limit exceeded",headers={"Retry-After":"60"})


@app.get("/health")
async def health():
    return {"status": "UP","websocket_connections":app.state.ws_bridge.connections}

@app.websocket("/ws")
async def websocket_endpoint(websocket:WebSocket):await websocket.app.state.ws_bridge.serve(websocket)


@app.get("/api/v1/me")
async def me(request: Request):
    principal = await verifier.authenticate(request)
    await check_rate_limit(request,principal.subject)
    return {"id": principal.subject, "username": principal.username, "roles": sorted(principal.roles)}


def validate_platform_roles(roles: set[str]) -> None:
    if not roles:
        raise HTTPException(status_code=422, detail="Назначьте хотя бы одну роль")
    unknown = roles - PLATFORM_ROLES
    if unknown:
        raise HTTPException(status_code=422, detail=f"Неизвестные роли: {', '.join(sorted(unknown))}")


async def require_admin(request: Request):
    principal = await verifier.authenticate(request)
    await check_rate_limit(request,principal.subject,"mutation" if request.method!="GET" else "read")
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
    expensive=service=="backtest" and request.method=="POST" and path.strip("/") in {"backtests","portfolio-backtests","optimizations"}
    await check_rate_limit(request,principal.subject,"expensive" if expensive else "mutation" if request.method!="GET" else "read")
    supplied_correlation=request.headers.get("x-correlation-id","")
    correlation_id=(supplied_correlation if re.fullmatch(r"[A-Za-z0-9._:-]{1,128}",supplied_correlation)
                    else str(uuid4()))
    headers = {
        "content-type": request.headers.get("content-type", "application/json"),
        "x-correlation-id": correlation_id,
        "x-user-id": principal.subject,
        "x-user-roles": ",".join(sorted(principal.roles)),
    }
    try:
        body = await request.body()
        if len(body)>settings.max_request_bytes:raise HTTPException(status_code=413,detail="Request body is too large")
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
    allowed_response_headers={"content-type","content-disposition","cache-control","etag","last-modified"}
    response_headers = {k: v for k, v in upstream.headers.items() if k.lower() in allowed_response_headers}
    response_headers["x-correlation-id"] = correlation_id
    return Response(upstream.content, status_code=upstream.status_code, headers=response_headers)


@app.api_route("/api/v1/{service}/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def service_proxy(service: str, path: str, request: Request):
    return await proxy(service, path, request)
