import asyncio
import csv
import io
import json
import logging
import time
from math import isfinite
from uuid import UUID, uuid4

import asyncpg
import httpx

from .elliott import run_elliott_replay
from .models import (AssetCreate, BacktestCreate, OptimizationSessionCreate,
                     OptimizationSessionUpdate, PortfolioBacktestCreate, StrategyType)
from .settings import Settings
from .portfolio import aggregate_portfolio, compact_asset_result


TIMEFRAME_INTERVALS = {
    "M1": 60_000, "M5": 300_000, "M15": 900_000, "M30": 1_800_000,
    "H1": 3_600_000, "H4": 14_400_000, "D1": 86_400_000,
}


def validate_candle_series(timeframe: str, candles: list[dict]) -> None:
    """Reject malformed, duplicate, unordered or internally incomplete market data."""
    previous_timestamp = None
    step = TIMEFRAME_INTERVALS[timeframe]
    for index, candle in enumerate(candles):
        timestamp = int(candle["timestamp"])
        values = {key: float(candle[key]) for key in ("open", "high", "low", "close", "volume")}
        if not all(isfinite(value) for value in values.values()):
            raise ValueError(f"non-finite {timeframe} candle at {timestamp}")
        if min(values["open"], values["high"], values["low"], values["close"]) <= 0:
            raise ValueError(f"non-positive {timeframe} price at {timestamp}")
        if values["volume"] < 0:
            raise ValueError(f"negative {timeframe} volume at {timestamp}")
        if values["high"] < max(values["open"], values["low"], values["close"]) \
                or values["low"] > min(values["open"], values["high"], values["close"]):
            raise ValueError(f"invalid {timeframe} OHLC at {timestamp}")
        if previous_timestamp is not None:
            difference = timestamp - previous_timestamp
            if difference <= 0:
                raise ValueError(f"duplicate or unordered {timeframe} candle at index {index}")
            if difference != step:
                raise ValueError(f"internal {timeframe} candle gap after {previous_timestamp}")
        previous_timestamp = timestamp


class BacktestService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.db: asyncpg.Pool | None = None
        self.client: httpx.AsyncClient | None = None
        self.tasks: dict[UUID, asyncio.Task] = {}
        self.cleanup_task: asyncio.Task | None = None
        self.semaphore = asyncio.Semaphore(settings.job_concurrency)
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
                CREATE TABLE IF NOT EXISTS optimization_sessions(
                    id uuid PRIMARY KEY, user_id text NOT NULL, status text NOT NULL,
                    configuration jsonb NOT NULL, checkpoint jsonb NOT NULL DEFAULT '{}'::jsonb,
                    error text, created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz
                );
                CREATE INDEX IF NOT EXISTS optimization_sessions_user_idx
                    ON optimization_sessions(user_id, updated_at DESC);
            """)
            await connection.execute("""
                INSERT INTO trading_assets(symbol,display_name,category,price_precision,quantity_precision,minimum_order_size,validation_status)
                VALUES('BTC-USDT-SWAP','Bitcoin perpetual','crypto',2,6,.000001,'ACTIVE'),
                      ('ETH-USDT-SWAP','Ethereum perpetual','crypto',2,6,.000001,'ACTIVE')
                ON CONFLICT(symbol) DO NOTHING
            """)
            await connection.execute("ALTER TABLE trading_assets ADD COLUMN IF NOT EXISTS tick_size double precision")
            await connection.execute("ALTER TABLE trading_assets ADD COLUMN IF NOT EXISTS lot_size double precision")
            await connection.execute("ALTER TABLE trading_assets ADD COLUMN IF NOT EXISTS contract_value double precision NOT NULL DEFAULT 1")
            await connection.execute("ALTER TABLE backtest_runs ADD COLUMN IF NOT EXISTS parent_id uuid REFERENCES backtest_runs(id) ON DELETE CASCADE")
            await connection.execute("CREATE INDEX IF NOT EXISTS backtest_runs_parent_idx ON backtest_runs(parent_id)")
            queued = await connection.fetch("SELECT id FROM backtest_runs WHERE status IN ('QUEUED','RUNNING')")
        await self.cleanup_expired_runs()
        self.cleanup_task = asyncio.create_task(self.cleanup_loop())
        for row in queued:
            self.schedule(row["id"])

    async def cleanup_expired_runs(self):
        async with self.db.acquire() as connection:
            await connection.execute("""
                DELETE FROM backtest_runs
                WHERE parent_id IS NULL AND status IN ('COMPLETED', 'FAILED', 'CANCELLED')
                  AND COALESCE(completed_at, created_at) < now() - interval '48 hours'
            """)

    async def cleanup_loop(self):
        while True:
            await asyncio.sleep(60)
            try:
                await self.cleanup_expired_runs()
            except Exception:
                logging.getLogger(__name__).exception("Failed to clean up expired backtest reports")

    async def stop(self):
        if self.cleanup_task:
            self.cleanup_task.cancel()
            await asyncio.gather(self.cleanup_task, return_exceptions=True)
        for task in self.tasks.values():
            task.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)
        if self.client:
            await self.client.aclose()
        if self.db:
            await self.db.close()

    def schedule(self, run_id: UUID):
        if run_id in self.tasks and not self.tasks[run_id].done():
            return
        task = asyncio.create_task(self.execute(run_id))
        self.tasks[run_id] = task
        task.add_done_callback(lambda completed, identifier=run_id: self.tasks.pop(identifier, None))

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

    async def create_portfolio_run(self, user_id: str, request: PortfolioBacktestCreate):
        run_id = uuid4()
        children = []
        async with self.db.acquire() as connection, connection.transaction():
            for asset in request.assets:
                if not await connection.fetchval(
                    "SELECT EXISTS(SELECT 1 FROM trading_assets WHERE symbol=$1 AND enabled)", asset.request.symbol
                ):
                    raise ValueError(f"asset is not enabled: {asset.request.symbol}")
                asset.request.config.initial_capital = request.initial_capital * asset.allocation_percent / 100
            await connection.execute(
                """INSERT INTO backtest_runs(id,user_id,symbol,timeframe,status,request)
                   VALUES($1,$2,$3,'PORTFOLIO','QUEUED',$4::jsonb)""",
                run_id, user_id, request.name, json.dumps({'portfolio': request.model_dump()}),
            )
            for asset in request.assets:
                child_id = uuid4()
                children.append(child_id)
                await connection.execute(
                    """INSERT INTO backtest_runs(id,user_id,symbol,timeframe,status,request,parent_id)
                       VALUES($1,$2,$3,$4,'QUEUED',$5::jsonb,$6)""",
                    child_id, user_id, asset.request.symbol, asset.request.timeframe,
                    asset.request.model_dump_json(), run_id,
                )
        for child_id in children:
            self.schedule(child_id)
        self.schedule(run_id)
        return run_id

    async def execute_portfolio(self, run_id: UUID, request: dict):
        try:
            await self.db.execute(
                "UPDATE backtest_runs SET status='RUNNING',started_at=COALESCE(started_at,now()) WHERE id=$1 AND status='QUEUED'", run_id)
            while True:
                rows = await self.db.fetch("SELECT id,symbol,status,progress,error FROM backtest_runs WHERE parent_id=$1", run_id)
                if len(rows) != len(request['assets']):
                    raise ValueError("Portfolio asset runs are missing")
                if all(row['status'] in ('COMPLETED', 'FAILED', 'CANCELLED') for row in rows):
                    break
                await self.db.execute("UPDATE backtest_runs SET progress=$2 WHERE id=$1 AND status='RUNNING'",
                                      run_id, int(sum(row['progress'] for row in rows) / len(rows)))
                await asyncio.sleep(1)
            failed = [row for row in rows if row['status'] != 'COMPLETED']
            if failed:
                raise ValueError('; '.join(f"{row['symbol']}: {row['error'] or row['status']}" for row in failed))
            rows = await self.db.fetch("SELECT id,symbol,result FROM backtest_runs WHERE parent_id=$1", run_id)
            by_symbol = {row['symbol']: {**dict(row), 'result': json.loads(row['result'])
                         if isinstance(row['result'], str) else row['result']} for row in rows}
            result = await asyncio.to_thread(aggregate_portfolio, request,
                [by_symbol[asset['request']['symbol']] for asset in request['assets']])
            await self.db.execute(
                """UPDATE backtest_runs SET status='COMPLETED',progress=100,result=$2::jsonb,completed_at=now()
                   WHERE id=$1 AND status='RUNNING'""", run_id, json.dumps(result))
        except Exception as exc:
            await self.db.execute(
                """UPDATE backtest_runs SET status='FAILED',error=$2,completed_at=now()
                   WHERE id=$1 AND status IN ('QUEUED','RUNNING')""", run_id, str(exc))

    async def execute(self, run_id: UUID):
        row = await self.db.fetchrow("SELECT request,status,parent_id FROM backtest_runs WHERE id=$1", run_id)
        if not row or row['status'] not in ('QUEUED', 'RUNNING'):
            return
        request = json.loads(row['request']) if isinstance(row['request'], str) else row['request']
        if 'portfolio' in request:
            await self.execute_portfolio(run_id, request['portfolio'])
            return
        async with self.semaphore:
            await self._execute(run_id)

    async def _execute(self, run_id: UUID):
        async with self.db.acquire() as connection:
            row = await connection.fetchrow("SELECT request,status,parent_id FROM backtest_runs WHERE id=$1", run_id)
            if not row or row["status"] == "CANCELLED":
                return
            await connection.execute(
                "UPDATE backtest_runs SET status='RUNNING',progress=10,started_at=now(),error=NULL WHERE id=$1", run_id
            )
        try:
            request = BacktestCreate.model_validate(json.loads(row["request"]) if isinstance(row["request"], str) else row["request"])
            async with self.db.acquire() as connection:
                asset = await connection.fetchrow(
                    "SELECT price_precision,quantity_precision,minimum_order_size,tick_size,lot_size,contract_value FROM trading_assets WHERE symbol=$1",
                    request.symbol,
                )
            if not asset:
                raise ValueError("asset metadata is missing")
            execution_spec = {
                "tick_size": float(asset["tick_size"] or 10 ** -asset["price_precision"]),
                "lot_size": float(asset["lot_size"] or 10 ** -asset["quantity_precision"]),
                "minimum_order_size": float(asset["minimum_order_size"]),
                "contract_value": float(asset["contract_value"]),
            }
            request.config = request.config.model_copy(update={
                key: execution_spec[key] for key in ("tick_size", "lot_size", "minimum_order_size")
            })
            test_candles = await self.load_candles(
                request.symbol, request.timeframes, request.test_from, request.test_to, request.candle_limit,
                warmup_bars=250 if request.test_from is not None else 0,
            )
            for candles in test_candles.values():
                for candle in candles: candle["volume"] *= execution_spec["contract_value"]
            async with self.db.acquire() as connection:
                await connection.execute("UPDATE backtest_runs SET progress=35 WHERE id=$1", run_id)
            async with self.db.acquire() as connection:
                await connection.execute("UPDATE backtest_runs SET progress=80 WHERE id=$1", run_id)
            result = await asyncio.to_thread(run_elliott_replay, test_candles, request.config, request.test_from)
            result["dataset"]["timeframes"] = request.timeframes
            result["dataset"]["execution_timeframe"] = request.config.elliott.entry_timeframe
            result["dataset"]["structure_timeframe"] = request.config.elliott.structure_timeframe
            result["dataset"]["macro_timeframe"] = request.config.elliott.macro_timeframe
            result.setdefault("dataset", {})
            result["dataset"].setdefault("timeframes", request.timeframes)
            result["dataset"].setdefault("test_candles", len(test_candles.get(request.timeframe, [])))
            result["dataset"].setdefault("closed_candles_only", True)
            if request.test_from is not None:
                result["dataset"]["test_from"] = request.test_from
            if request.test_to is not None:
                result["dataset"]["test_to"] = request.test_to
            result["strategy_config"] = {
                "leverage": (request.config.leverage if request.config.strategy != StrategyType.ELLIOTT
                             or request.config.elliott.use_margin else 1),
                "position_size_percent": request.config.position_size_percent,
                "risk_per_trade_percent": request.config.risk_per_trade_percent,
                "use_margin": (request.config.elliott.use_margin
                               if request.config.strategy == StrategyType.ELLIOTT else True),
                "reinvest_profits": (request.config.elliott.reinvest_profits
                                     if request.config.strategy == StrategyType.ELLIOTT else True),
                "lot_size": request.config.lot_size,
                "minimum_order_size": request.config.minimum_order_size,
            }
            result["request_config"] = request.model_dump(mode="json")
            result["execution_spec"] = execution_spec
            result["engine"] = {
                "name": "ELLIOTT_CLOSE_TIME_REPLAY",
                "version": 2,
            }
            if row['parent_id'] is not None:
                result = compact_asset_result(result)
            async with self.db.acquire() as connection:
                await connection.execute(
                    "UPDATE backtest_runs SET status='COMPLETED',progress=100,result=$2::jsonb,completed_at=now() "
                    "WHERE id=$1 AND status='RUNNING'",
                    run_id, json.dumps(result, separators=(",", ":"))
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            async with self.db.acquire() as connection:
                await connection.execute(
                    "UPDATE backtest_runs SET status='FAILED',error=$2,completed_at=now() "
                    "WHERE id=$1 AND status<>'CANCELLED'",
                    run_id, str(exc)[:2000],
                )

    async def load_candles(self, symbol, timeframes, start, end, limit, warmup_bars=0):
        bounded_limit = min(limit, self.settings.max_candles)
        result = {}
        async with self.db.acquire() as connection:
            for timeframe in timeframes:
                query_start = None if start is None else max(0, start - TIMEFRAME_INTERVALS[timeframe] * warmup_bars)
                rows = await connection.fetch(
                    """
                    SELECT symbol,timeframe,(extract(epoch FROM ts)*1000)::bigint AS timestamp,
                           open::float8,high::float8,low::float8,close::float8,volume::float8,
                           quote_volume::float8,trades_count,is_closed
                    FROM candles WHERE symbol=$1 AND timeframe=$2 AND is_closed
                      AND ($3::bigint IS NULL OR ts>=to_timestamp($3/1000.0))
                      AND ($4::bigint IS NULL OR ts<to_timestamp($4/1000.0))
                    ORDER BY ts DESC LIMIT $5
                    """,
                    symbol, timeframe, query_start, end, bounded_limit,
                )
                result[timeframe] = [dict(row) for row in reversed(rows)]
        missing = [timeframe for timeframe, candles in result.items() if not candles]
        if missing:
            raise ValueError(f"no stored closed candles for: {', '.join(missing)}")
        for timeframe, candles in result.items():
            validate_candle_series(timeframe, candles)
        if start is not None and end is not None:
            incomplete = []
            truncated = []
            for timeframe, candles in result.items():
                step = TIMEFRAME_INTERVALS[timeframe]
                evaluation = [item for item in candles if item["timestamp"] >= start]
                latest_closed = (int(time.time() * 1000) // step - 1) * step
                required_end = min(end, latest_closed)
                if not evaluation or evaluation[0]["timestamp"] > start + step \
                        or evaluation[-1]["timestamp"] < required_end - step:
                    incomplete.append(timeframe)
                if len(candles) == bounded_limit and (not evaluation or evaluation[0]["timestamp"] > start + step):
                    truncated.append(timeframe)
            if truncated:
                raise ValueError(
                    f"candle_limit={bounded_limit} truncates requested period for: {', '.join(truncated)}; "
                    "increase the candle limit"
                )
            if incomplete:
                raise ValueError(f"stored candles do not cover the requested period for: {', '.join(incomplete)}")
        return result

    async def runs(self, user_id: str, limit: int = 50, offset: int = 0):
        async with self.db.acquire() as connection:
            rows = await connection.fetch(
                "SELECT id,symbol,timeframe,status,progress,error,created_at,completed_at FROM backtest_runs "
                "WHERE user_id=$1 AND parent_id IS NULL ORDER BY created_at DESC LIMIT $2 OFFSET $3", user_id, limit, offset
            )
            total = await connection.fetchval("SELECT count(*) FROM backtest_runs WHERE user_id=$1 AND parent_id IS NULL", user_id)
        return {"runs": [self.serialize_run(row, include_result=False) for row in rows], "total": total}

    async def create_optimization(self, user_id: str, request: OptimizationSessionCreate):
        session_id = uuid4()
        async with self.db.acquire() as connection:
            await connection.execute(
                """UPDATE optimization_sessions SET status='PAUSED',updated_at=now()
                   WHERE user_id=$1 AND status='RUNNING'""", user_id,
            )
            row = await connection.fetchrow(
                """INSERT INTO optimization_sessions(id,user_id,status,configuration,checkpoint)
                   VALUES($1,$2,'RUNNING',$3::jsonb,$4::jsonb) RETURNING *""",
                session_id, user_id, json.dumps(request.configuration), json.dumps(request.checkpoint),
            )
        return self.serialize_optimization(row)

    async def active_optimization(self, user_id: str):
        async with self.db.acquire() as connection:
            row = await connection.fetchrow(
                """SELECT * FROM optimization_sessions WHERE user_id=$1
                   AND status IN ('RUNNING','PAUSED') ORDER BY updated_at DESC LIMIT 1""", user_id,
            )
            if row and row["status"] == "RUNNING":
                row = await connection.fetchrow(
                    """UPDATE optimization_sessions SET status='PAUSED',updated_at=now()
                       WHERE id=$1 RETURNING *""", row["id"],
                )
        return self.serialize_optimization(row) if row else None

    async def update_optimization(self, session_id: UUID, user_id: str, request: OptimizationSessionUpdate):
        async with self.db.acquire() as connection:
            row = await connection.fetchrow(
                """UPDATE optimization_sessions SET status=$3,checkpoint=$4::jsonb,error=$5,
                   updated_at=now(),completed_at=CASE WHEN $3 IN ('CANCELLED','COMPLETED','FAILED') THEN now() ELSE NULL END
                   WHERE id=$1 AND user_id=$2 RETURNING *""",
                session_id, user_id, request.status, json.dumps(request.checkpoint), request.error,
            )
        return self.serialize_optimization(row) if row else None

    @staticmethod
    def serialize_optimization(row):
        if not row:
            return None
        return {
            "id": str(row["id"]), "status": row["status"],
            "configuration": json.loads(row["configuration"]) if isinstance(row["configuration"], str) else row["configuration"],
            "checkpoint": json.loads(row["checkpoint"]) if isinstance(row["checkpoint"], str) else row["checkpoint"],
            "error": row["error"], "created_at": row["created_at"].isoformat(),
            "updated_at": row["updated_at"].isoformat(),
            "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
        }

    async def run(self, run_id: UUID, user_id: str, summary: bool = False):
        async with self.db.acquire() as connection:
            row = await connection.fetchrow("SELECT * FROM backtest_runs WHERE id=$1 AND user_id=$2", run_id, user_id)
        serialized = self.serialize_run(row, include_result=True) if row else None
        if serialized and summary and serialized.get("result"):
            full_result = serialized["result"]
            summary_keys = {
                "initial_capital", "final_capital", "net_profit", "total_return_percent",
                "max_drawdown_percent", "win_rate", "profit_factor", "total_trades", "average_trade",
                "sharpe_ratio", "benchmark_return_percent", "average_monthly_return_percent",
                "annualized_return_percent", "losing_months", "losing_months_percent",
                "average_losing_month_percent", "equity_curve_r_squared", "recovery_factor",
                "request_config", "dataset", "portfolio",
                "elliott_diagnostics", "strategy_config", "execution_spec", "engine",
            }
            result = {key: value for key, value in full_result.items() if key in summary_keys}
            result.update({
                "trades": [], "equity": [], "chart_candles": [], "chart_candles_by_timeframe": {},
                "scenarios": [], "pattern_diagnostics": {}, "elliott_patterns": [],
            })
            serialized["result"] = result
        return serialized

    async def cancel_run(self, run_id: UUID, user_id: str):
        async with self.db.acquire() as connection:
            cancelled = await connection.fetchval(
                """UPDATE backtest_runs SET status='CANCELLED',completed_at=now()
                   WHERE id=$1 AND user_id=$2 AND status IN ('QUEUED','RUNNING') RETURNING id""",
                run_id, user_id,
            )
        if cancelled:
            children = await self.db.fetch("SELECT id FROM backtest_runs WHERE parent_id=$1", run_id)
            for child in children:
                await self.cancel_run(child['id'], user_id)
        task = self.tasks.get(run_id)
        if cancelled and task and not task.done():
            task.cancel()
        return cancelled

    async def delete_runs_in_period(self, user_id: str, date_from, date_to):
        async with self.db.acquire() as connection:
            return await connection.fetchval("""
                WITH deleted AS (
                    DELETE FROM backtest_runs
                    WHERE user_id=$1 AND parent_id IS NULL AND created_at >= $2 AND created_at < $3
                      AND status IN ('COMPLETED', 'FAILED', 'CANCELLED')
                    RETURNING id
                ) SELECT count(*) FROM deleted
            """, user_id, date_from, date_to)

    async def delete_run(self, run_id: UUID, user_id: str):
        async with self.db.acquire() as connection:
            return await connection.fetchval(
                """DELETE FROM backtest_runs
                   WHERE id=$1 AND user_id=$2 AND status NOT IN ('QUEUED','RUNNING')
                   RETURNING id""",
                run_id, user_id,
            )

    @staticmethod
    def serialize_run(row, include_result: bool):
        item = {key: row[key] for key in ("id", "symbol", "timeframe", "status", "progress", "error", "created_at", "completed_at")}
        item = {**item, "id": str(item["id"]), "created_at": item["created_at"].isoformat(),
                "completed_at": item["completed_at"].isoformat() if item["completed_at"] else None}
        if include_result:
            item["result"] = json.loads(row["result"]) if isinstance(row["result"], str) else row["result"]
        return item

    async def assets(self, enabled_only: bool = True):
        query = ("SELECT * FROM trading_assets WHERE enabled ORDER BY symbol" if enabled_only
                 else "SELECT * FROM trading_assets ORDER BY symbol")
        async with self.db.acquire() as connection:
            rows = await connection.fetch(query)
        return [{**dict(row), "created_at": row["created_at"].isoformat(), "updated_at": row["updated_at"].isoformat()} for row in rows]

    async def dataset(self, symbol: str):
        async with self.db.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT timeframe,count(*) AS candles,
                       (extract(epoch FROM min(ts))*1000)::bigint AS from_timestamp,
                       (extract(epoch FROM max(ts))*1000)::bigint AS to_timestamp
                FROM candles WHERE symbol=$1 AND is_closed GROUP BY timeframe ORDER BY timeframe
                """,
                symbol.strip().upper(),
            )
        return [dict(row) for row in rows]
    async def delete_dataset(self, symbol: str, timeframe: str | None = None):
        symbol = symbol.strip().upper()
        async with self.db.acquire() as connection:
            result = await connection.execute(
                "DELETE FROM candles WHERE symbol=$1 AND ($2::text IS NULL OR timeframe=$2)",symbol,timeframe,
            )
        return int(result.rsplit(" ",1)[-1])

    async def audit_dataset(self, symbol, timeframes, start=None, end=None):
        intervals = {"M1":60_000,"M5":300_000,"M15":900_000,"M30":1_800_000,"H1":3_600_000,"H4":14_400_000,"D1":86_400_000}
        reports=[]
        async with self.db.acquire() as connection:
            for timeframe in timeframes:
                rows=await connection.fetch(
                    """SELECT (extract(epoch FROM ts)*1000)::bigint timestamp,
                              open::float8,high::float8,low::float8,close::float8,is_closed
                       FROM candles WHERE symbol=$1 AND timeframe=$2
                         AND ($3::bigint IS NULL OR ts>=to_timestamp($3/1000.0))
                         AND ($4::bigint IS NULL OR ts<=to_timestamp($4/1000.0)) ORDER BY ts""",
                    symbol.strip().upper(),timeframe,start,end,
                )
                timestamps=[row["timestamp"] for row in rows];step=intervals[timeframe];gaps=[]
                for previous,current in zip(timestamps,timestamps[1:]):
                    if current-previous>step:
                        gaps.append({"from":previous+step,"to":current-step,"missing":(current-previous)//step-1})
                invalid=sum(
                    not row["is_closed"] or row["low"]>row["high"] or not row["low"]<=row["open"]<=row["high"]
                    or not row["low"]<=row["close"]<=row["high"] for row in rows
                )
                coverage_start=timestamps[0] if timestamps else None;coverage_end=timestamps[-1] if timestamps else None
                reports.append({
                    "timeframe":timeframe,"candles":len(rows),"from_timestamp":coverage_start,"to_timestamp":coverage_end,
                    "missing_candles":sum(item["missing"] for item in gaps),"gap_examples":gaps[:100],
                    "invalid_candles":invalid,"covers_requested_range":bool(timestamps)
                    and (start is None or coverage_start<=start) and (end is None or coverage_end>=end-step),
                })
        return reports

    async def add_asset(self, asset: AssetCreate):
        async with self.db.acquire() as connection:
            row = await connection.fetchrow("""
                INSERT INTO trading_assets(symbol,display_name,category,price_precision,quantity_precision,minimum_order_size,
                                           tick_size,lot_size,validation_status)
                VALUES($1,$2,$3,$4,$5,$6,$7,$8,'ACTIVE')
                ON CONFLICT(symbol) DO UPDATE SET display_name=excluded.display_name,category=excluded.category,
                    price_precision=excluded.price_precision,quantity_precision=excluded.quantity_precision,
                    minimum_order_size=excluded.minimum_order_size,tick_size=coalesce(excluded.tick_size,trading_assets.tick_size),
                    lot_size=coalesce(excluded.lot_size,trading_assets.lot_size),enabled=true,updated_at=now()
                RETURNING *
            """, asset.symbol, asset.display_name, asset.category, asset.price_precision,
                asset.quantity_precision, asset.minimum_order_size, asset.tick_size, asset.lot_size)
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
            "id", "symbol", "run_id", "leverage", "capital_before", "allocated_capital", "allocation_percent",
            "direction", "entry_time", "exit_time", "entry_price", "exit_price", "quantity", "pnl",
            "pnl_percent", "fees", "funding", "reason", "scenario_id", "template_id", "confidence",
        ], extrasaction="ignore")
        writer.writeheader()
        writer.writerows(run["result"]["trades"])
        return "text/csv", output.getvalue()
