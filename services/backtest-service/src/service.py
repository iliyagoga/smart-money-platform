import asyncio
import csv
import io
import json
import time
from math import isfinite
from pathlib import Path
from uuid import UUID, uuid4

import asyncpg
import httpx
import boto3

from .engine import run_backtest
from .elliott import run_elliott_replay
from .models import AssetCreate, BacktestCreate, StrategyType
from .replay import FrozenModel, run_smc_replay, train_local_model
from .settings import Settings


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
        self.semaphore = asyncio.Semaphore(settings.job_concurrency)
        self.s3 = boto3.client(
            "s3", endpoint_url=settings.minio_endpoint, aws_access_key_id=settings.minio_access_key,
            aws_secret_access_key=settings.minio_secret_key,
        )

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
            await connection.execute("ALTER TABLE trading_assets ADD COLUMN IF NOT EXISTS tick_size double precision")
            await connection.execute("ALTER TABLE trading_assets ADD COLUMN IF NOT EXISTS lot_size double precision")
            await connection.execute("ALTER TABLE trading_assets ADD COLUMN IF NOT EXISTS contract_value double precision NOT NULL DEFAULT 1")
            queued = await connection.fetch("SELECT id FROM backtest_runs WHERE status IN ('QUEUED','RUNNING')")
        for row in queued:
            self.schedule(row["id"])

    async def stop(self):
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

    async def execute(self, run_id: UUID):
        async with self.semaphore:
            await self._execute(run_id)

    async def _execute(self, run_id: UUID):
        async with self.db.acquire() as connection:
            row = await connection.fetchrow("SELECT request,status FROM backtest_runs WHERE id=$1", run_id)
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
            warmup_bars = (max(request.config.slow_period, request.config.rsi_period, 35)
                           if request.config.strategy not in (StrategyType.SMC, StrategyType.ELLIOTT)
                           else 250)
            test_candles = await self.load_candles(
                request.symbol, request.timeframes, request.test_from, request.test_to, request.candle_limit,
                warmup_bars=warmup_bars if request.test_from is not None else 0,
            )
            for candles in test_candles.values():
                for candle in candles: candle["volume"] *= execution_spec["contract_value"]
            async with self.db.acquire() as connection:
                await connection.execute("UPDATE backtest_runs SET progress=35 WHERE id=$1", run_id)
            if request.config.strategy == StrategyType.SMC:
                model = None
                if request.config.local_retraining:
                    if request.train_from is None:
                        raise ValueError("explicit train and test periods are required for local retraining")
                    training_candles = await self.load_candles(
                        request.symbol, request.timeframes, request.train_from, request.train_to,
                        self.settings.max_candles,
                    )
                    for candles in training_candles.values():
                        for candle in candles: candle["volume"] *= execution_spec["contract_value"]
                    async with self.db.acquire() as connection:
                        await connection.execute("UPDATE backtest_runs SET progress=50 WHERE id=$1", run_id)
                    model = await asyncio.to_thread(
                        train_local_model, training_candles, request.timeframe, request.config,
                        self.settings.scenario_template_dir,
                    )
                    async with self.db.acquire() as connection:
                        await connection.execute("UPDATE backtest_runs SET progress=70 WHERE id=$1", run_id)
                    artifact_path = await self.save_local_model(run_id, model, request)
                else:
                    model = await self.load_frozen_model(request.model_version, request.test_from)
                async with self.db.acquire() as connection:
                    await connection.execute("UPDATE backtest_runs SET progress=80 WHERE id=$1", run_id)
                result = await asyncio.to_thread(
                    run_smc_replay, test_candles, request.timeframe, request.config,
                    self.settings.scenario_template_dir, model, request.test_from,
                )
                result["dataset"]["timeframes"] = request.timeframes
                result["dataset"]["execution_timeframe"] = request.timeframe
                result["dataset"]["requested_train_from"] = request.train_from
                result["dataset"]["requested_train_to"] = request.train_to
                result["dataset"]["requested_test_from"] = request.test_from
                result["dataset"]["requested_test_to"] = request.test_to
                if request.config.local_retraining:
                    result["model_training"]["artifact_path"] = artifact_path
            elif request.config.strategy == StrategyType.ELLIOTT:
                async with self.db.acquire() as connection:
                    await connection.execute("UPDATE backtest_runs SET progress=80 WHERE id=$1", run_id)
                result = await asyncio.to_thread(run_elliott_replay, test_candles, request.config, request.test_from)
                result["dataset"]["timeframes"] = request.timeframes
                result["dataset"]["execution_timeframe"] = request.config.elliott.entry_timeframe
                result["dataset"]["structure_timeframe"] = request.config.elliott.structure_timeframe
                result["dataset"]["macro_timeframe"] = request.config.elliott.macro_timeframe
            else:
                result = await asyncio.to_thread(
                    run_backtest, test_candles[request.timeframe], request.config, request.test_from,
                )
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
                "stop_loss_percent": request.config.stop_loss_percent,
                "smc_min_stop_percent": request.config.smc_min_stop_percent,
                "take_profit_percent": request.config.take_profit_percent,
            }
            result["request_config"] = request.model_dump(mode="json")
            result["execution_spec"] = execution_spec
            result["engine"] = {
                "name": ({StrategyType.SMC: "SMC_CLOSE_TIME_REPLAY", StrategyType.ELLIOTT: "ELLIOTT_CLOSE_TIME_REPLAY"}
                         .get(request.config.strategy, "INDICATOR_REPLAY")),
                "version": 2,
                "template_versions": {
                    path.stem: json.loads(path.read_text(encoding="utf-8")).get("version", 1)
                    for path in Path(self.settings.scenario_template_dir).glob("*.json")
                } if request.config.strategy == StrategyType.SMC else {},
            }
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

    async def save_local_model(self, run_id, model, request):
        bucket = "models"
        key = f"backtests/{run_id}/local-template-model.json"
        artifact = {
            "type": "TEMPLATE_BAYES_WALK_FORWARD", "run_id": str(run_id),
            "train_from": request.train_from, "train_to": request.train_to,
            "outcomes": model.outcomes, "metrics": model.metrics, "folds": model.folds,
        }
        await asyncio.to_thread(
            self.s3.put_object, Bucket=bucket, Key=key, Body=json.dumps(artifact).encode(),
            ContentType="application/json",
        )
        return f"s3://{bucket}/{key}"

    async def load_frozen_model(self, version, test_from):
        try:
            async with self.db.acquire() as connection:
                if version:
                    row = await connection.fetchrow(
                        "SELECT version,path,training_date FROM model_versions WHERE version=$1", version,
                    )
                else:
                    row = await connection.fetchrow(
                        """
                        SELECT version,path,training_date FROM model_versions
                        WHERE ($1::bigint IS NULL OR training_date<to_timestamp($1/1000.0))
                        ORDER BY is_active DESC,training_date DESC LIMIT 1
                        """,
                        test_from,
                    )
        except asyncpg.UndefinedTableError:
            return None
        if not row:
            return None
        if test_from and int(row["training_date"].timestamp() * 1000) >= test_from:
            raise ValueError("selected model was trained after the backtest period started")
        bucket, key = row["path"].removeprefix("s3://").split("/", 1)
        response = await asyncio.to_thread(self.s3.get_object, Bucket=bucket, Key=key)
        artifact = json.loads(await asyncio.to_thread(response["Body"].read))
        return FrozenModel(
            version=artifact["version"], feature_names=list(artifact["feature_names"]),
            weights=[float(item) for item in artifact["weights"]], bias=float(artifact.get("bias", 0)),
        )

    async def runs(self, user_id: str, limit: int = 50, offset: int = 0):
        async with self.db.acquire() as connection:
            rows = await connection.fetch(
                "SELECT id,symbol,timeframe,status,progress,error,created_at,completed_at,result FROM backtest_runs "
                "WHERE user_id=$1 ORDER BY created_at DESC LIMIT $2 OFFSET $3", user_id, limit, offset
            )
            total = await connection.fetchval("SELECT count(*) FROM backtest_runs WHERE user_id=$1", user_id)
        return {"runs": [self.serialize_run(row, include_result=False) for row in rows], "total": total}

    async def run(self, run_id: UUID, user_id: str):
        async with self.db.acquire() as connection:
            row = await connection.fetchrow("SELECT * FROM backtest_runs WHERE id=$1 AND user_id=$2", run_id, user_id)
        return self.serialize_run(row, include_result=True) if row else None

    async def cancel_run(self, run_id: UUID, user_id: str):
        async with self.db.acquire() as connection:
            cancelled = await connection.fetchval(
                """UPDATE backtest_runs SET status='CANCELLED',completed_at=now()
                   WHERE id=$1 AND user_id=$2 AND status IN ('QUEUED','RUNNING') RETURNING id""",
                run_id, user_id,
            )
        task = self.tasks.get(run_id)
        if cancelled and task and not task.done():
            task.cancel()
        return cancelled

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
        query = "SELECT * FROM trading_assets" + (" WHERE enabled" if enabled_only else "") + " ORDER BY symbol"
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
            "id", "direction", "entry_time", "exit_time", "entry_price", "exit_price", "quantity", "pnl",
            "pnl_percent", "fees", "funding", "reason", "scenario_id", "template_id", "confidence",
        ])
        writer.writeheader()
        writer.writerows(run["result"]["trades"])
        return "text/csv", output.getvalue()
