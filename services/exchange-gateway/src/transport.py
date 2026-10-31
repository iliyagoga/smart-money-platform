"""TLS compatibility settings scoped to OKX, never to the process."""
import logging
import ssl

import httpx

log = logging.getLogger(__name__)


def okx_ssl_context():
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.maximum_version = ssl.TLSVersion.TLSv1_2
    return context


def error_types(exc):
    """Keep chained transport causes without logging signed requests or credentials."""
    names = []
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        names.append(type(exc).__name__)
        exc = exc.__cause__ or exc.__context__
    return " <- ".join(names)


class OKXClient(httpx.AsyncClient):
    def __init__(self):
        # Let HTTPX retain its normal proxy / NO_PROXY routing and zero retries.
        super().__init__(verify=okx_ssl_context(), timeout=20)

    async def request(self, method, url, **kwargs):
        try:
            return await super().request(method, url, **kwargs)
        except httpx.RequestError as exc:
            endpoint = httpx.URL(url)
            log.warning("OKX REST connection failed host=%s method=%s path=%s tls=TLSv1.2 error=%s",
                        endpoint.host, method, endpoint.path, error_types(exc))
            raise
