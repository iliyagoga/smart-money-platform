import asyncio
import csv
import io
import json
import time
from uuid import UUID, uuid4

import asyncpg
import httpx
import boto3

from .engine import run_backtest
from .models import AssetCreate, BacktestCreate, StrategyType
from .replay import FrozenModel, run_smc_replay, train_local_model
from .settings import Settings


class BacktestService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.db: asyncpg.Pool | None = None
        self.client: httpx.AsyncClient | None = None
        self.tasks: set[asyncio.Task] = set()
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
            test_candles = await self.load_candles(
                request.symbol, request.timeframes, request.test_from, request.test_to, request.candle_limit,
            )
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
                    self.settings.scenario_template_dir, model,
                )
                result["dataset"]["timeframes"] = request.timeframes
                result["dataset"]["requested_train_from"] = request.train_from
                result["dataset"]["requested_train_to"] = request.train_to
                result["dataset"]["requested_test_from"] = request.test_from
                result["dataset"]["requested_test_to"] = request.test_to
                if request.config.local_retraining:
                    result["model_training"]["artifact_path"] = artifact_path
            else:
                result = await asyncio.to_thread(run_backtest, test_candles[request.timeframe], request.config)
            async with self.db.acquire() as connection:
                await connection.execute(
                    "UPDATE backtest_runs SET status='COMPLETED',progress=100,result=$2::jsonb,completed_at=now() WHERE id=$1",
                    run_id, json.dumps(result, separators=(",", ":"))
                )
        except Exception as exc:
            async with self.db.acquire() as connection:
                await connection.execute(
                    "UPDATE backtest_runs SET status='FAILED',error=$2,completed_at=now() WHERE id=$1",
                    run_id, str(exc)[:2000],
                )

    async def load_candles(self, symbol, timeframes, start, end, limit):
        intervals = {"M1":60_000,"M5":300_000,"M15":900_000,"H1":3_600_000,"H4":14_400_000,"D1":86_400_000}
        bounded_limit = min(limit, self.settings.max_candles)
        result = {}
        async with self.db.acquire() as connection:
            for timeframe in timeframes:
                rows = await connection.fetch(
                    """
                    SELECT symbol,timeframe,(extract(epoch FROM ts)*1000)::bigint AS timestamp,
                           open::float8,high::float8,low::float8,close::float8,volume::float8,
                           quote_volume::float8,trades_count,is_closed
                    FROM candles WHERE symbol=$1 AND timeframe=$2 AND is_closed
                      AND ($3::bigint IS NULL OR ts>=to_timestamp($3/1000.0))
                      AND ($4::bigint IS NULL OR ts<=to_timestamp($4/1000.0))
                    ORDER BY ts DESC LIMIT $5
                    """,
                    symbol, timeframe, start, end, bounded_limit,
                )
                result[timeframe] = [dict(row) for row in reversed(rows)]
        missing = [timeframe for timeframe, candles in result.items() if not candles]
        if missing:
            raise ValueError(f"no stored closed candles for: {', '.join(missing)}")
        if start is not None and end is not None:
            incomplete = []
            truncated = []
            for timeframe, candles in result.items():
                step = intervals[timeframe]
                latest_closed = (int(time.time() * 1000) // step - 1) * step
                required_end = min(end, latest_closed)
                if candles[0]["timestamp"] > start + step or candles[-1]["timestamp"] < required_end - step:
                    incomplete.append(timeframe)
                if len(candles) == bounded_limit and candles[0]["timestamp"] > start + step:
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

    async def cancel_run(self, run_id: UUID, user_id: str):
        async with self.db.acquire() as connection:
            return await connection.fetchval(
                """UPDATE backtest_runs SET status='CANCELLED',completed_at=now()
                   WHERE id=$1 AND user_id=$2 AND status='QUEUED' RETURNING id""",
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

    async def audit_dataset(self, symbol, timeframes, start=None, end=None):
        intervals = {"M1":60_000,"M5":300_000,"M15":900_000,"H1":3_600_000,"H4":14_400_000,"D1":86_400_000}
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
            "pnl_percent", "fees", "funding", "reason", "scenario_id", "template_id", "confidence",
        ])
        writer.writeheader()
        writer.writerows(run["result"]["trades"])
        return "text/csv", output.getvalue()
