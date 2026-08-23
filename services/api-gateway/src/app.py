from contextlib import asynccontextmanager
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response

from .security import TokenVerifier, authorize
from .settings import settings


SERVICE_URLS = {
    "data": settings.data_service_url,
    "smc": settings.smc_service_url,
    "decision": settings.decision_service_url,
    "execution": settings.execution_service_url,
    "analytics": settings.analytics_service_url,
}
verifier = TokenVerifier(settings.keycloak_issuer, settings.keycloak_jwks_url, settings.keycloak_client_id)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.client = httpx.AsyncClient(timeout=settings.request_timeout)
    yield
    await app.state.client.aclose()


app = FastAPI(title="Smart Money API Gateway", version="1.0.0", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "UP"}


@app.get("/api/v1/me")
async def me(request: Request):
    principal = await verifier.authenticate(request)
    return {"id": principal.subject, "username": principal.username, "roles": sorted(principal.roles)}


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
        upstream = await request.app.state.client.request(
            request.method,
            f"{base_url}/{path}",
            params=request.query_params,
            content=await request.body(),
            headers=headers,
        )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Upstream {service} is unavailable") from exc
    excluded = {"content-length", "connection", "transfer-encoding", "content-encoding"}
    response_headers = {k: v for k, v in upstream.headers.items() if k.lower() not in excluded}
    response_headers["x-correlation-id"] = correlation_id
    return Response(upstream.content, status_code=upstream.status_code, headers=response_headers)


@app.api_route("/api/v1/{service}/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def service_proxy(service: str, path: str, request: Request):
    return await proxy(service, path, request)

