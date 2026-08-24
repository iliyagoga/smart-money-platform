from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import FastAPI, Header, HTTPException, Query, Response

from .models import AssetCreate, BacktestCreate
from .service import BacktestService
from .settings import settings

service = BacktestService(settings)


@asynccontextmanager
async def lifespan(app):
    await service.start()
    yield
    await service.stop()


app = FastAPI(title="Smart Money Backtest Service", version="1.0.0", lifespan=lifespan)


@app.get("/health")
async def health():
    async with service.db.acquire() as connection:
        await connection.fetchval("SELECT 1")
    return {"status": "UP", "active_jobs": len(service.tasks)}


@app.get("/assets")
async def assets(enabled_only: bool = True):
    return {"assets": await service.assets(enabled_only)}


@app.get("/datasets/{symbol}")
async def dataset(symbol: str):
    return {"symbol": symbol.strip().upper(), "timeframes": await service.dataset(symbol)}


@app.delete("/datasets/{symbol}")
async def delete_dataset(symbol: str, timeframe: str | None = None):
    if timeframe is not None and timeframe not in {"M1", "M5", "M15", "M30", "H1", "H4", "D1"}:
        raise HTTPException(422, "Unsupported timeframe")
    return {"symbol":symbol.strip().upper(),"timeframe":timeframe,"deleted_candles":await service.delete_dataset(symbol,timeframe)}


@app.get("/datasets/{symbol}/audit")
async def audit_dataset(symbol: str, timeframes: list[str] = Query(), from_timestamp: int | None = None,
                        to_timestamp: int | None = None):
    supported = {"M1", "M5", "M15", "M30", "H1", "H4", "D1"}
    if not timeframes or any(item not in supported for item in timeframes):
        raise HTTPException(422, "Unsupported timeframe")
    reports = await service.audit_dataset(symbol, timeframes, from_timestamp, to_timestamp)
    return {"symbol": symbol.strip().upper(), "healthy": all(
        not item["missing_candles"] and not item["invalid_candles"] and item["covers_requested_range"] for item in reports
    ), "timeframes": reports}


@app.post("/assets", status_code=201)
async def add_asset(asset: AssetCreate):
    return await service.add_asset(asset)


@app.delete("/assets/{symbol}")
async def disable_asset(symbol: str):
    if not await service.disable_asset(symbol):
        raise HTTPException(404, "Asset not found")
    return {"success": True, "symbol": symbol.upper()}


@app.post("/backtests", status_code=202)
async def create_backtest(request: BacktestCreate, x_user_id: str = Header(default="local")):
    try:
        run_id = await service.create_run(x_user_id, request)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"id": str(run_id), "status": "QUEUED"}


@app.get("/backtests")
async def backtests(x_user_id: str = Header(default="local"), limit: int = Query(default=50, ge=1, le=500)):
    return {"runs": await service.runs(x_user_id, limit)}


@app.get("/backtests/compare")
async def compare(ids: list[UUID] = Query(), x_user_id: str = Header(default="local")):
    runs = [await service.run(run_id, x_user_id) for run_id in ids[:10]]
    return {"runs": [run for run in runs if run]}


@app.get("/backtests/{run_id}")
async def backtest(run_id: UUID, x_user_id: str = Header(default="local")):
    run = await service.run(run_id, x_user_id)
    if not run:
        raise HTTPException(404, "Backtest not found")
    return run


@app.post("/backtests/{run_id}/cancel")
async def cancel_backtest(run_id: UUID, x_user_id: str = Header(default="local")):
    if not await service.cancel_run(run_id, x_user_id):
        raise HTTPException(409, "Only a queued backtest can be cancelled")
    return {"id": str(run_id), "status": "CANCELLED"}


@app.get("/backtests/{run_id}/export")
async def export_backtest(run_id: UUID, format: str = Query(default="csv", pattern="^(csv|json)$"),
                          x_user_id: str = Header(default="local")):
    exported = await service.export(run_id, x_user_id, format)
    if not exported:
        raise HTTPException(409, "Completed backtest is required")
    media_type, content = exported
    return Response(content, media_type=media_type,
                    headers={"Content-Disposition": f'attachment; filename="backtest-{run_id}.{format}"'})
