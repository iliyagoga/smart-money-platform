import asyncio
from dataclasses import dataclass
from time import monotonic

import httpx
import jwt
from fastapi import HTTPException, Request, status


@dataclass(frozen=True)
class Principal:
    subject: str
    username: str
    roles: frozenset[str]
    claims: dict


class TokenVerifier:
    JWKS_TTL_SECONDS = 300

    def __init__(self, issuer: str, jwks_url: str, client_id: str):
        self.issuer = issuer.rstrip("/")
        self.jwks_url = jwks_url
        self.client_id = client_id
        self._keys: dict[str, object] = {}
        self._loaded_at = 0.0
        self._refresh_attempted_at = float("-inf")
        self._refresh_lock = asyncio.Lock()

    async def _refresh(self) -> None:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(self.jwks_url)
            response.raise_for_status()
        if len(response.content)>1_000_000:
            raise jwt.InvalidTokenError("JWKS response is too large")
        payload=response.json()
        raw_keys=payload.get("keys") if isinstance(payload,dict) else None
        if not isinstance(raw_keys,list) or len(raw_keys)>100:
            raise jwt.InvalidTokenError("JWKS response is invalid")
        keys={}
        for item in raw_keys:
            if not isinstance(item,dict) or item.get("use")!="sig" or item.get("alg")!="RS256":continue
            key_id=item.get("kid")
            if not isinstance(key_id,str) or not key_id or len(key_id)>255:continue
            keys[key_id]=jwt.PyJWK.from_dict(item).key
        if not keys:raise jwt.InvalidTokenError("JWKS contains no supported signing keys")
        self._keys=keys
        self._loaded_at = monotonic()

    async def _key(self, kid: str) -> object:
        key = self._keys.get(kid)
        if key is not None and monotonic() - self._loaded_at < self.JWKS_TTL_SECONDS:
            return key
        async with self._refresh_lock:
            key = self._keys.get(kid)
            if key is not None and monotonic() - self._loaded_at < self.JWKS_TTL_SECONDS:
                return key
            now = monotonic()
            if now - self._refresh_attempted_at < 10:
                raise jwt.InvalidTokenError("token references an unknown signing key")
            self._refresh_attempted_at = now
            await self._refresh()
            key = self._keys.get(kid)
            if key is None:
                raise jwt.InvalidTokenError("token references an unknown signing key")
            return key

    async def verify(self, token: str) -> Principal:
        try:
            kid = jwt.get_unverified_header(token).get("kid")
            if not isinstance(kid, str) or not kid or len(kid) > 255:
                raise jwt.InvalidTokenError("token has an invalid key identifier")
            key = await self._key(kid)
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                issuer=self.issuer,
                options={"verify_aud": False, "require": ["exp", "iat", "sub"]},
            )
            authorized_party = claims.get("azp")
            audience = claims.get("aud", [])
            if isinstance(audience, str):
                audience = [audience]
            elif not isinstance(audience, (list, tuple)):
                raise jwt.InvalidAudienceError("token has an invalid audience")
            if self.client_id not in audience and authorized_party != self.client_id:
                raise jwt.InvalidAudienceError("token is not intended for this platform")
            if claims.get("typ") not in (None,"Bearer"):
                raise jwt.InvalidTokenError("an access token is required")
            realm_access = claims.get("realm_access", {})
            if not isinstance(realm_access, dict) or not isinstance(realm_access.get("roles", []), list):
                raise jwt.InvalidTokenError("token has invalid realm roles")
            roles = frozenset(role for role in realm_access.get("roles", []) if isinstance(role, str))
            platform_roles = roles.intersection({"admin", "trader", "viewer"})
            if not platform_roles:
                raise jwt.InvalidTokenError("platform role is missing")
            subject = claims["sub"]
            if not isinstance(subject, str) or not subject or len(subject) > 255:
                raise jwt.InvalidTokenError("token has an invalid subject")
            username = claims.get("preferred_username", subject)
            if not isinstance(username, str) or not username or len(username) > 255:
                username = subject
            return Principal(
                subject=subject,
                username=username,
                roles=platform_roles,
                claims=claims,
            )
        except (jwt.PyJWTError, KeyError, TypeError, ValueError, httpx.HTTPError) as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired access token",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

    async def authenticate(self, request: Request) -> Principal:
        authorization = request.headers.get("authorization", "")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Bearer token is required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return await self.verify(token)


EXPOSED_PATH_PREFIXES = {
    "data": ("/market", "/internal/ingest"),
    "elliott": ("/elliott", "/scenarios", "/internal"),
    "decision": ("/risk", "/signals", "/internal"),
    "execution": ("/orders", "/positions", "/trading-configs", "/portfolios", "/configuration-library", "/trades"),
    "analytics": ("/portfolio", "/analytics", "/monitoring"),
    "exchange": ("/exchange",),
    "backtest": ("/assets", "/datasets", "/backtests", "/portfolio-backtests", "/optimizations"),
}


def authorize(principal: Principal, method: str, service: str, path: str) -> None:
    if any(segment in {".", ".."} for segment in path.split("/")):
        raise HTTPException(status_code=404, detail="Endpoint is not exposed by the API gateway")
    normalized = "/" + path.strip("/")
    prefixes=EXPOSED_PATH_PREFIXES.get(service,())
    if not any(normalized==prefix or normalized.startswith(prefix+"/") for prefix in prefixes):
        raise HTTPException(status_code=404,detail="Endpoint is not exposed by the API gateway")
    if "admin" in principal.roles:
        return
    admin_only = (
        normalized.startswith("/internal")
        or service == "exchange" and normalized in {"/exchange/reload-symbols","/exchange/sync"}
        or service == "decision" and normalized == "/signals/simulate-elliott" and method == "POST"
        or service == "decision" and normalized.startswith("/risk/config") and method != "GET"
        or service == "backtest" and normalized.startswith(("/assets","/datasets")) and method != "GET"
        or service == "exchange" and normalized.startswith("/exchange/account")
        or service == "exchange" and normalized.startswith("/exchange/history") and method != "GET"
    )
    if admin_only:
        raise HTTPException(status_code=403, detail="Admin role is required")
    if service == "backtest" and normalized == "/backtests" and method == "POST":
        return
    if method in {"GET", "HEAD", "OPTIONS"}:
        return
    if "trader" not in principal.roles:
        raise HTTPException(status_code=403, detail="Trader or admin role is required")
