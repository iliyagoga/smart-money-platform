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
    def __init__(self, issuer: str, jwks_url: str, client_id: str):
        self.issuer = issuer.rstrip("/")
        self.jwks_url = jwks_url
        self.client_id = client_id
        self._keys: dict[str, object] = {}
        self._loaded_at = 0.0

    async def _refresh(self) -> None:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(self.jwks_url)
            response.raise_for_status()
        self._keys = {
            item["kid"]: jwt.PyJWK.from_dict(item).key
            for item in response.json().get("keys", [])
            if item.get("use") == "sig" and item.get("alg") == "RS256"
        }
        self._loaded_at = monotonic()

    async def verify(self, token: str) -> Principal:
        try:
            kid = jwt.get_unverified_header(token)["kid"]
            if kid not in self._keys or monotonic() - self._loaded_at > 300:
                await self._refresh()
            claims = jwt.decode(
                token,
                self._keys[kid],
                algorithms=["RS256"],
                issuer=self.issuer,
                options={"verify_aud": False},
            )
            authorized_party = claims.get("azp")
            audience = claims.get("aud", [])
            if isinstance(audience, str):
                audience = [audience]
            if self.client_id not in audience and authorized_party != self.client_id and authorized_party != "smart-money-web":
                raise jwt.InvalidAudienceError("token is not intended for this platform")
            roles = frozenset(claims.get("realm_access", {}).get("roles", []))
            platform_roles = roles.intersection({"admin", "trader", "viewer"})
            if not platform_roles:
                raise jwt.InvalidTokenError("platform role is missing")
            return Principal(
                subject=claims["sub"],
                username=claims.get("preferred_username", claims["sub"]),
                roles=platform_roles,
                claims=claims,
            )
        except (jwt.PyJWTError, KeyError, httpx.HTTPError) as exc:
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


def authorize(principal: Principal, method: str, service: str, path: str) -> None:
    if "admin" in principal.roles:
        return
    normalized = "/" + path.strip("/")
    admin_only = (
        normalized.startswith("/internal")
        or service == "decision" and normalized.startswith("/risk/config") and method != "GET"
        or service == "learning" and normalized == "/learning/train" and method == "POST"
    )
    if admin_only:
        raise HTTPException(status_code=403, detail="Admin role is required")
    if method in {"GET", "HEAD", "OPTIONS"}:
        return
    if "trader" not in principal.roles:
        raise HTTPException(status_code=403, detail="Trader or admin role is required")
