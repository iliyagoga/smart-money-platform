import asyncio
from urllib.parse import quote

import httpx


PLATFORM_ROLES = frozenset({"admin", "trader", "viewer"})


class KeycloakAdminError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class KeycloakAdmin:
    def __init__(self, base_url: str, realm: str, username: str, password: str):
        self.base_url = base_url.rstrip("/")
        self.realm = realm
        self.username = username
        self.password = password

    async def _token(self, client: httpx.AsyncClient) -> str:
        response = await client.post(
            f"{self.base_url}/realms/master/protocol/openid-connect/token",
            data={
                "client_id": "admin-cli",
                "username": self.username,
                "password": self.password,
                "grant_type": "password",
            },
        )
        self._ensure_success(response, "Не удалось авторизоваться в Keycloak Admin API")
        token = response.json().get("access_token")
        if not token:
            raise KeycloakAdminError(502, "Keycloak не вернул административный токен")
        return token

    async def list_users(self, client: httpx.AsyncClient) -> list[dict]:
        token = await self._token(client)
        headers = self._headers(token)
        response = await client.get(
            f"{self._admin_url}/users", params={"max": 1000}, headers=headers,
        )
        self._ensure_success(response, "Не удалось получить пользователей")
        users = response.json()
        role_lists = await asyncio.gather(*(
            self._user_roles(client, headers, user["id"]) for user in users
        ))
        return [self._serialize_user(user, roles) for user, roles in zip(users, role_lists)]

    async def create_user(self, client: httpx.AsyncClient, user: dict) -> dict:
        token = await self._token(client)
        headers = self._headers(token)
        response = await client.post(
            f"{self._admin_url}/users",
            headers=headers,
            json={
                "username": user["username"],
                "email": user.get("email") or None,
                "firstName": user.get("first_name") or "",
                "lastName": user.get("last_name") or "",
                "enabled": True,
                "emailVerified": False,
                "credentials": [{
                    "type": "password",
                    "value": user["password"],
                    "temporary": user.get("temporary_password", True),
                }],
            },
        )
        self._ensure_success(response, "Не удалось создать пользователя")
        user_id = response.headers.get("location", "").rstrip("/").rsplit("/", 1)[-1]
        if not user_id:
            lookup = await client.get(
                f"{self._admin_url}/users",
                params={"username": user["username"], "exact": "true"},
                headers=headers,
            )
            self._ensure_success(lookup, "Пользователь создан, но не найден")
            matches = lookup.json()
            if not matches:
                raise KeycloakAdminError(502, "Пользователь создан, но Keycloak не вернул его идентификатор")
            user_id = matches[0]["id"]
        try:
            await self._replace_platform_roles(client, headers, user_id, set(user["roles"]))
        except KeycloakAdminError:
            await client.delete(f"{self._admin_url}/users/{quote(user_id, safe='')}", headers=headers)
            raise
        return await self._get_user(client, headers, user_id)

    async def update_user(self, client: httpx.AsyncClient, user_id: str, enabled: bool, roles: set[str]) -> dict:
        token = await self._token(client)
        headers = self._headers(token)
        encoded_id = quote(user_id, safe="")
        response = await client.put(
            f"{self._admin_url}/users/{encoded_id}", headers=headers, json={"enabled": enabled},
        )
        self._ensure_success(response, "Не удалось обновить пользователя")
        await self._replace_platform_roles(client, headers, user_id, roles)
        return await self._get_user(client, headers, user_id)

    @property
    def _admin_url(self) -> str:
        return f"{self.base_url}/admin/realms/{quote(self.realm, safe='')}"

    async def _get_user(self, client: httpx.AsyncClient, headers: dict[str, str], user_id: str) -> dict:
        response = await client.get(
            f"{self._admin_url}/users/{quote(user_id, safe='')}", headers=headers,
        )
        self._ensure_success(response, "Не удалось получить пользователя")
        roles = await self._user_roles(client, headers, user_id)
        return self._serialize_user(response.json(), roles)

    async def _user_roles(self, client: httpx.AsyncClient, headers: dict[str, str], user_id: str) -> set[str]:
        response = await client.get(
            f"{self._admin_url}/users/{quote(user_id, safe='')}/role-mappings/realm",
            headers=headers,
        )
        self._ensure_success(response, "Не удалось получить роли пользователя")
        return {role["name"] for role in response.json() if role.get("name") in PLATFORM_ROLES}

    async def _replace_platform_roles(
        self, client: httpx.AsyncClient, headers: dict[str, str], user_id: str, roles: set[str],
    ) -> None:
        role_representations: dict[str, dict] = {}
        for role in PLATFORM_ROLES:
            response = await client.get(
                f"{self._admin_url}/roles/{quote(role, safe='')}", headers=headers,
            )
            self._ensure_success(response, f"Роль {role} не найдена в Keycloak")
            role_representations[role] = response.json()
        current = await self._user_roles(client, headers, user_id)
        remove = [role_representations[role] for role in current - roles]
        add = [role_representations[role] for role in roles - current]
        mapping_url = f"{self._admin_url}/users/{quote(user_id, safe='')}/role-mappings/realm"
        if remove:
            response = await client.request("DELETE", mapping_url, headers=headers, json=remove)
            self._ensure_success(response, "Не удалось снять роли пользователя")
        if add:
            response = await client.post(mapping_url, headers=headers, json=add)
            self._ensure_success(response, "Не удалось назначить роли пользователю")

    @staticmethod
    def _headers(token: str) -> dict[str, str]:
        return {"authorization": f"Bearer {token}", "content-type": "application/json"}

    @staticmethod
    def _serialize_user(user: dict, roles: set[str]) -> dict:
        return {
            "id": user["id"],
            "username": user.get("username", ""),
            "email": user.get("email") or "",
            "first_name": user.get("firstName") or "",
            "last_name": user.get("lastName") or "",
            "enabled": bool(user.get("enabled", False)),
            "roles": sorted(roles),
        }

    @staticmethod
    def _ensure_success(response: httpx.Response, fallback: str) -> None:
        if response.is_success:
            return
        try:
            payload = response.json()
            detail = payload.get("errorMessage") or payload.get("error_description") or payload.get("error")
        except ValueError:
            detail = response.text
        status_code = response.status_code if response.status_code in {400, 401, 403, 404, 409} else 502
        raise KeycloakAdminError(status_code, detail or fallback)
