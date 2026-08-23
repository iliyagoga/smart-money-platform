import asyncio
import csv
import io
import json
from uuid import UUID, uuid4

import asyncpg
import httpx

from .engine import run_backtest
from .models import AssetCreate, BacktestCreate
from .settings import Settings


class BacktestService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.db: asyncpg.Pool | None = None
        self.client: httpx.AsyncClient | None = None
        self.tasks: set[asyncio.Task] = set()

    async def start(self):
        self.db = await asyncpg.create_pool(self.settings.database_url)
        self.client = httpx.AsyncClient(timeout=30)
        async with self.db.acquire() as connection:
            await connection.execute("""
                CREATE TABLE IF NOT EXISTS trading_assets(
                    symbol text PRIMARY KEY, display_name text, category text NOT NULL, enabled boolean NOT NULL DEFAULT true,
                    price_precision smallint NOT NULL, quantity_precision smallint NOT NULL,
                    minimum_order_size double precision NOT NULL, validation_status text NOT NULL DEFAULT 'PENDING',
                    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
                );
                CREATE TABLE IF NOT EXISTS backtest_runs(
                    id uuid PRIMARY KEY, user_id text NOT NULL, symbol text NOT NULL, timeframe text NOT NULL,
                    status text NOT NULL, progress smallint NOT NULL DEFAULT 0, request jsonb NOT NULL,
                    result jsonb, error text, created_at timestamptz NOT NULL DEFAULT now(),
                    started_at timestamptz, completed_at timestamptz
                );
                CREATE INDEX IF NOT EXISTS backtest_runs_user_idx ON backtest_runs(user_id, created_at DESC);
            """)
            await connection.execute("""
                INSERT INTO trading_assets(symbol,display_name,category,price_precision,quantity_precision,minimum_order_size,validation_status)
                VALUES('BTC-USDT-SWAP','Bitcoin perpetual','crypto',2,6,.000001,'ACTIVE'),
                      ('ETH-USDT-SWAP','Ethereum perpetual','crypto',2,6,.000001,'ACTIVE')
                ON CONFLICT(symbol) DO NOTHING
            """)
            queued = await connection.fetch("SELECT id FROM backtest_runs WHERE status IN ('QUEUED','RUNNING')")
        for row in queued:
            self.schedule(row["id"])

    async def stop(self):
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        if self.client:
            await self.client.aclose()
        if self.db:
            await self.db.close()

    def schedule(self, run_id: UUID):
        task = asyncio.create_task(self.execute(run_id))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def create_run(self, user_id: str, request: BacktestCreate) -> UUID:
        run_id = uuid4()
        async with self.db.acquire() as connection:
            asset_exists = await connection.fetchval(
                "SELECT EXISTS(SELECT 1 FROM trading_assets WHERE symbol=$1 AND enabled)", request.symbol
            )
            if not asset_exists:
                raise ValueError("asset is not enabled")
            await connection.execute(
                "INSERT INTO backtest_runs(id,user_id,symbol,timeframe,status,request) VALUES($1,$2,$3,$4,'QUEUED',$5::jsonb)",
                run_id, user_id, request.symbol, request.timeframe, request.model_dump_json()
            )
        self.schedule(run_id)
        return run_id

    async def execute(self, run_id: UUID):
        async with self.db.acquire() as connection:
            row = await connection.fetchrow("SELECT request FROM backtest_runs WHERE id=$1", run_id)
            if not row:
                return
            await connection.execute(
                "UPDATE backtest_runs SET status='RUNNING',progress=10,started_at=now(),error=NULL WHERE id=$1", run_id
            )
        try:
            request = BacktestCreate.model_validate(json.loads(row["request"]) if isinstance(row["request"], str) else row["request"])
            response = await self.client.get(
                f"{self.settings.data_service_url}/market/candles",
                params={"symbol": request.symbol, "timeframe": request.timeframe, "limit": request.candle_limit},
            )
            response.raise_for_status()
            candles = response.json().get("candles", [])
            async with self.db.acquire() as connection:
                await connection.execute("UPDATE backtest_runs SET progress=55 WHERE id=$1", run_id)
            result = await asyncio.to_thread(run_backtest, candles, request.config)
            async with self.db.acquire() as connection:
                await connection.execute(
                    "UPDATE backtest_runs SET status='COMPLETED',progress=100,result=$2::jsonb,completed_at=now() WHERE id=$1",
                    run_id, json.dumps(result, separators=(",", ":"))
                )
        except Exception as exc:
            async with self.db.acquire() as connection:
                await connection.execute(
                    "UPDATE backtest_runs SET status='FAILED',error=$2,completed_at=now() WHERE id=$1", run_id, str(exc)[:2000]
                )

    async def runs(self, user_id: str, limit: int = 50):
        async with self.db.acquire() as connection:
            rows = await connection.fetch(
                "SELECT id,symbol,timeframe,status,progress,error,created_at,completed_at,result FROM backtest_runs "
                "WHERE user_id=$1 ORDER BY created_at DESC LIMIT $2", user_id, limit
            )
        return [self.serialize_run(row, include_result=False) for row in rows]

    async def run(self, run_id: UUID, user_id: str):
        async with self.db.acquire() as connection:
            row = await connection.fetchrow("SELECT * FROM backtest_runs WHERE id=$1 AND user_id=$2", run_id, user_id)
        return self.serialize_run(row, include_result=True) if row else None

    @staticmethod
    def serialize_run(row, include_result: bool):
        item = {key: row[key] for key in ("id", "symbol", "timeframe", "status", "progress", "error", "created_at", "completed_at")}
        item = {**item, "id": str(item["id"]), "created_at": item["created_at"].isoformat(),
                "completed_at": item["completed_at"].isoformat() if item["completed_at"] else None}
        if include_result:
            item["result"] = json.loads(row["result"]) if isinstance(row["result"], str) else row["result"]
        return item

    async def assets(self, enabled_only: bool = True):
        query = "SELECT * FROM trading_assets" + (" WHERE enabled" if enabled_only else "") + " ORDER BY symbol"
        async with self.db.acquire() as connection:
            rows = await connection.fetch(query)
        return [{**dict(row), "created_at": row["created_at"].isoformat(), "updated_at": row["updated_at"].isoformat()} for row in rows]

    async def add_asset(self, asset: AssetCreate):
        async with self.db.acquire() as connection:
            row = await connection.fetchrow("""
                INSERT INTO trading_assets(symbol,display_name,category,price_precision,quantity_precision,minimum_order_size,validation_status)
                VALUES($1,$2,$3,$4,$5,$6,'ACTIVE')
                ON CONFLICT(symbol) DO UPDATE SET display_name=excluded.display_name,category=excluded.category,
                    price_precision=excluded.price_precision,quantity_precision=excluded.quantity_precision,
                    minimum_order_size=excluded.minimum_order_size,enabled=true,updated_at=now()
                RETURNING *
            """, asset.symbol, asset.display_name, asset.category, asset.price_precision,
                asset.quantity_precision, asset.minimum_order_size)
        return dict(row)

    async def disable_asset(self, symbol: str):
        async with self.db.acquire() as connection:
            return await connection.fetchval(
                "UPDATE trading_assets SET enabled=false,updated_at=now() WHERE symbol=$1 RETURNING symbol", symbol.upper()
            )

    async def export(self, run_id: UUID, user_id: str, format_name: str):
        run = await self.run(run_id, user_id)
        if not run or run["status"] != "COMPLETED":
            return None
        if format_name == "json":
            return "application/json", json.dumps(run, ensure_ascii=False, indent=2)
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=[
            "id", "direction", "entry_time", "exit_time", "entry_price", "exit_price", "quantity", "pnl",
            "pnl_percent", "fees", "funding", "reason"
        ])
        writer.writeheader()
        writer.writerows(run["result"]["trades"])
        return "text/csv", output.getvalue()
