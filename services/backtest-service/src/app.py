from contextlib import asynccontextmanager
from uuid import UUID

from pydantic import AwareDatetime

from fastapi import FastAPI, Header, HTTPException, Query, Response

from .models import AssetCreate, BacktestCreate, OptimizationSessionCreate, OptimizationSessionUpdate, PortfolioBacktestCreate
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


@app.post("/portfolio-backtests", status_code=202)
async def create_portfolio_backtest(request: PortfolioBacktestCreate, x_user_id: str = Header(default="local")):
    try:
        run_id = await service.create_portfolio_run(x_user_id, request)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"id": str(run_id), "status": "QUEUED"}


@app.get("/backtests")
async def backtests(x_user_id: str = Header(default="local"), limit: int = Query(default=10, ge=1, le=100),
                    offset: int = Query(default=0, ge=0)):
    return await service.runs(x_user_id, limit, offset)


@app.delete("/backtests")
async def delete_backtests(date_from: AwareDatetime, date_to: AwareDatetime,
                           x_user_id: str = Header(default="local")):
    if date_from >= date_to:
        raise HTTPException(422, "date_from must be earlier than date_to")
    return {"deleted_count": await service.delete_runs_in_period(x_user_id, date_from, date_to)}


@app.get("/backtests/compare")
async def compare(ids: list[UUID] = Query(), x_user_id: str = Header(default="local")):
    runs = [await service.run(run_id, x_user_id) for run_id in ids[:10]]
    return {"runs": [run for run in runs if run]}


@app.get("/backtests/{run_id}")
async def backtest(run_id: UUID, summary: bool = Query(default=False),
                   x_user_id: str = Header(default="local")):
    run = await service.run(run_id, x_user_id, summary=summary)
    if not run:
        raise HTTPException(404, "Backtest not found")
    return run


@app.delete("/backtests/{run_id}")
async def delete_backtest(run_id: UUID, x_user_id: str = Header(default="local")):
    if not await service.delete_run(run_id, x_user_id):
        raise HTTPException(409, "Backtest not found or still active")
    return {"id": str(run_id), "deleted": True}


@app.post("/backtests/{run_id}/cancel")
async def cancel_backtest(run_id: UUID, x_user_id: str = Header(default="local")):
    if not await service.cancel_run(run_id, x_user_id):
        raise HTTPException(409, "Only a queued or running backtest can be cancelled")
    return {"id": str(run_id), "status": "CANCELLED"}


@app.post("/optimizations", status_code=201)
async def create_optimization(request: OptimizationSessionCreate, x_user_id: str = Header(default="local")):
    return await service.create_optimization(x_user_id, request)


@app.get("/optimizations/active")
async def active_optimization(x_user_id: str = Header(default="local")):
    return await service.active_optimization(x_user_id)


@app.put("/optimizations/{session_id}")
async def update_optimization(session_id: UUID, request: OptimizationSessionUpdate,
                              x_user_id: str = Header(default="local")):
    updated = await service.update_optimization(session_id, x_user_id, request)
    if not updated:
        raise HTTPException(404, "Optimization session not found")
    return updated


@app.get("/backtests/{run_id}/export")
async def export_backtest(run_id: UUID, format: str = Query(default="csv", pattern="^(csv|json)$"),
                          x_user_id: str = Header(default="local")):
    exported = await service.export(run_id, x_user_id, format)
    if not exported:
        raise HTTPException(409, "Completed backtest is required")
    media_type, content = exported
    return Response(content, media_type=media_type,
                    headers={"Content-Disposition": f'attachment; filename="backtest-{run_id}.{format}"'})
