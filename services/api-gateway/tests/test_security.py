import pytest
from fastapi import HTTPException

from src.security import Principal, authorize


def principal(*roles):
    return Principal("id", "user", frozenset(roles), {})


def test_viewer_can_read():
    authorize(principal("viewer"), "GET", "execution", "/positions")


def test_viewer_cannot_trade():
    with pytest.raises(HTTPException) as error:
        authorize(principal("viewer"), "POST", "execution", "/positions/id/close")
    assert error.value.status_code == 403


def test_trader_can_trade_but_not_ingest():
    authorize(principal("trader"), "POST", "execution", "/orders")
    with pytest.raises(HTTPException):
        authorize(principal("trader"), "POST", "data", "/internal/ingest/candles")


def test_only_admin_changes_risk_config():
    with pytest.raises(HTTPException):
        authorize(principal("trader"), "PATCH", "decision", "/risk/config")
    authorize(principal("admin"), "PATCH", "decision", "/risk/config")



def test_viewer_can_run_backtest_but_only_admin_manages_assets():
    authorize(principal("viewer"), "POST", "backtest", "/backtests")
    with pytest.raises(HTTPException):
        authorize(principal("trader"), "POST", "backtest", "/assets")
    authorize(principal("admin"), "POST", "backtest", "/assets")
