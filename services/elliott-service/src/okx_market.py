from __future__ import annotations

import asyncio
from collections.abc import Mapping

import httpx

from .models import Candle, Timeframe


OKX_TIMEFRAMES = {
    "M1": "1m", "M5": "5m", "M15": "15m", "M30": "30m",
    "H1": "1H", "H4": "4H", "D1": "1D",
}
TIMEFRAME_MILLISECONDS = {
    "M1": 60_000, "M5": 300_000, "M15": 900_000, "M30": 1_800_000,
    "H1": 3_600_000, "H4": 14_400_000, "D1": 86_400_000,
}


class OkxMarketDataUnavailable(RuntimeError):
    pass


class OkxMarketSource:
    """An isolated, direct OKX candle source used only by live Elliott analysis."""

    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None):
        self.client = client or httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=20)
        self._owns_client = client is None
        self.cache: dict[tuple[str, str], list[Candle]] = {}
        self.locks: dict[tuple[str, str], asyncio.Lock] = {}
        self.semaphore = asyncio.Semaphore(6)

    async def close(self):
        if self._owns_client:
            await self.client.aclose()

    async def load(self, symbol: str, limits: Mapping[str, int], entry_timeframe: str,
                   entry_timestamp: int) -> dict[tuple[str, Timeframe], list[Candle]]:
        loaded = await asyncio.gather(*(
            self._load_timeframe(symbol, timeframe, limit, entry_timestamp if timeframe == entry_timeframe else None)
            for timeframe, limit in limits.items()
        ))
        return {(symbol, Timeframe(timeframe)): candles
                for timeframe, candles in zip(limits, loaded, strict=True)}

    async def _load_timeframe(self, symbol: str, timeframe: str, limit: int,
                              expected_timestamp: int | None) -> list[Candle]:
        key = (symbol, timeframe)
        async with self.locks.setdefault(key, asyncio.Lock()):
            newest = await self._latest_closed(symbol, timeframe, expected_timestamp)
            merged = self._merge(self.cache.get(key, []), newest)
            candidate = merged[-limit:]
            cursor = min(item.timestamp for item in newest) if newest else None
            pages = 1
            max_pages = (limit + 299) // 300 + 3
            while not self._complete(candidate, timeframe, limit):
                if cursor is None or pages >= max_pages:
                    raise OkxMarketDataUnavailable(
                        f"OKX returned an incomplete {symbol} {timeframe} series ({len(candidate)}/{limit})"
                    )
                page = await self._page(symbol, timeframe, cursor)
                if not page:
                    raise OkxMarketDataUnavailable(f"OKX history ended before {symbol} {timeframe} was complete")
                previous_cursor = cursor
                cursor = min(item.timestamp for item in page)
                merged = self._merge(merged, page)
                candidate = merged[-limit:]
                pages += 1
                if cursor >= previous_cursor:
                    raise OkxMarketDataUnavailable(f"OKX cursor did not advance for {symbol} {timeframe}")
            if expected_timestamp is not None and candidate[-1].timestamp < expected_timestamp:
                raise OkxMarketDataUnavailable(
                    f"OKX latest {symbol} {timeframe} candle is stale: "
                    f"{candidate[-1].timestamp} < {expected_timestamp}"
                )
            self.cache[key] = candidate
            return candidate

    async def _latest_closed(self, symbol: str, timeframe: str,
                             expected_timestamp: int | None) -> list[Candle]:
        page: list[Candle] = []
        for attempt in range(3):
            page = await self._page(symbol, timeframe)
            if expected_timestamp is None or (page and page[-1].timestamp >= expected_timestamp):
                return page
            await asyncio.sleep(.25 * (2 ** attempt))
        return page

    async def _page(self, symbol: str, timeframe: str, after: int | None = None) -> list[Candle]:
        params = {"instId": symbol, "bar": OKX_TIMEFRAMES[timeframe], "limit": "300"}
        if after is not None:
            params["after"] = str(after)
        for attempt in range(4):
            try:
                async with self.semaphore:
                    response = await self.client.get("/api/v5/market/history-candles", params=params)
                if response.status_code == 429:
                    await asyncio.sleep(.25 * (2 ** attempt))
                    continue
                response.raise_for_status()
                body = response.json()
                if body.get("code") != "0":
                    raise OkxMarketDataUnavailable(body.get("msg", "OKX market data error"))
                result = [self._candle(symbol, timeframe, item) for item in body.get("data", []) if item[8] == "1"]
                return sorted(result, key=lambda item: item.timestamp)
            except (httpx.HTTPError, ValueError, IndexError) as exc:
                if attempt == 3:
                    raise OkxMarketDataUnavailable(f"Could not load {symbol} {timeframe} from OKX: {exc}") from exc
                await asyncio.sleep(.25 * (2 ** attempt))
        raise OkxMarketDataUnavailable(f"Could not load {symbol} {timeframe} from OKX")

    @staticmethod
    def _candle(symbol: str, timeframe: str, item: list) -> Candle:
        return Candle(
            symbol=symbol, timeframe=Timeframe(timeframe), timestamp=int(item[0]),
            open=float(item[1]), high=float(item[2]), low=float(item[3]), close=float(item[4]),
            volume=float(item[5]), quote_volume=float(item[7]), is_closed=True,
        )

    @staticmethod
    def _merge(current: list[Candle], incoming: list[Candle]) -> list[Candle]:
        return sorted({item.timestamp: item for item in [*current, *incoming]}.values(),
                      key=lambda item: item.timestamp)

    @staticmethod
    def _complete(candles: list[Candle], timeframe: str, limit: int) -> bool:
        if len(candles) < limit:
            return False
        step = TIMEFRAME_MILLISECONDS[timeframe]
        return all(right.timestamp - left.timestamp == step for left, right in zip(candles, candles[1:]))
