import asyncio
import json
import os
from math import sin
from unittest.mock import AsyncMock
from contextlib import asynccontextmanager
from uuid import uuid4

import asyncpg
import pytest
from pydantic import ValidationError

from src.models import PortfolioBacktestCreate
from src.portfolio import aggregate_portfolio, compact_asset_result
from src.service import BacktestService


def request():
    return PortfolioBacktestCreate.model_validate({
        'name': 'Test portfolio', 'initial_capital': 1000,
        'assets': [{'allocation_percent': weight, 'request': {
            'symbol': symbol, 'timeframe': 'M1', 'timeframes': ['M1'],
            'test_from': 1000, 'test_to': 4000,
            'config': {'strategy': 'ELLIOTT', 'elliott': {'entry_timeframe': 'M1', 'structure_timeframe': 'M15', 'macro_timeframe': 'H1'}},
        }} for symbol, weight in [('AAA', 50), ('BBB', 30)]],
    })


def results():
    return [{'id': str(uuid4()), 'result': {
        'initial_capital': initial, 'final_capital': final,
        'equity': [{'timestamp': t, 'equity': v} for t, v in points],
        'trades': [{'id': 1, 'entry_time': 1000, 'exit_time': 3000,
                    'pnl': final-initial, 'direction': 'LONG'}],
        'total_trades': 1, 'win_rate': 100 if final > initial else 0,
        'max_drawdown_percent': 80, 'benchmark_return_percent': 10,
    }} for initial, final, points in [
        (500, 550, [(1000, 500), (2000, 600), (3000, 540), (3000, 550)]),
        (300, 270, [(1000, 300), (2500, 270)]),
    ]]


def test_aggregate_synchronizes_equity_cash_and_contributions():
    result = aggregate_portfolio(request().model_dump(), results())
    assert [point['equity'] for point in result['equity']] == [1000, 1100, 1070, 1020, 1020]
    assert result['initial_capital'] == 1000
    assert result['final_capital'] == 1020
    assert result['net_profit'] == 20
    assert result['max_drawdown_percent'] == pytest.approx(80 / 1100 * 100)
    assert result['win_rate'] == 50
    assert result['profit_factor'] == pytest.approx(50 / 30)
    assert result['portfolio']['cash'] == pytest.approx(200)
    assert sum(asset['contribution_percent'] for asset in result['portfolio']['assets']) == pytest.approx(result['total_return_percent'])
    assert [trade['id'] for trade in result['trades']] == [1, 2]
    assert {trade['symbol'] for trade in result['trades']} == {'AAA', 'BBB'}
    assert result['benchmark_return_percent'] == 8


def test_zero_trade_portfolio_has_flat_equity():
    runs = results()
    for run in runs:
        value = run['result']
        value.update(final_capital=value['initial_capital'], equity=[], trades=[], total_trades=0)
    result = aggregate_portfolio(request().model_dump(), runs)
    assert result['net_profit'] == 0
    assert result['max_drawdown_percent'] == 0
    assert result['sharpe_ratio'] == 0
    assert result['total_trades'] == 0


def test_portfolio_rejects_invalid_allocations_symbols_and_periods():
    for field, value in [('allocation_percent', 80), ('allocation_percent', 0), ('allocation_percent', float('nan'))]:
        data = request().model_dump()
        data['assets'][0][field] = value
        with pytest.raises(ValidationError):
            PortfolioBacktestCreate.model_validate(data)
    for field, value in [('symbol', 'AAA'), ('test_from', 2000), ('test_to', None)]:
        data = request().model_dump()
        data['assets'][1]['request'][field] = value
        with pytest.raises(ValidationError):
            PortfolioBacktestCreate.model_validate(data)


def test_sequential_portfolio_allows_each_asset_to_use_full_capital():
    data = request().model_dump()
    data['capital_mode'] = 'SEQUENTIAL'
    for asset in data['assets']:
        asset['allocation_percent'] = 100
    validated = PortfolioBacktestCreate.model_validate(data)
    assert [asset.allocation_percent for asset in validated.assets] == [100, 100]


def test_sequential_portfolio_uses_latest_capital_and_skips_overlaps():
    data = request().model_dump()
    data['capital_mode'] = 'SEQUENTIAL'
    data['assets'][0]['allocation_percent'] = 100
    data['assets'][1]['allocation_percent'] = 50
    runs = [
        {'id': 'aaa', 'result': {
            'initial_capital': 1000, 'final_capital': 1100,
            'equity': [{'timestamp': 1000, 'equity': 1000}, {'timestamp': 2000, 'equity': 1100}],
            'trades': [{'id': 1, 'entry_time': 1000, 'exit_time': 2000, 'entry_price': 100,
                        'exit_price': 110, 'quantity': 10, 'pnl': 100, 'pnl_percent': 10,
                        'fees': 0, 'direction': 'LONG', 'reason': 'FIXED_RR_TARGET'}],
            'total_trades': 1, 'win_rate': 100, 'max_drawdown_percent': 0,
            'benchmark_return_percent': 10,
        }},
        {'id': 'bbb', 'result': {
            'initial_capital': 500, 'final_capital': 570,
            'equity': [{'timestamp': 1500, 'equity': 500}, {'timestamp': 1800, 'equity': 520},
                       {'timestamp': 2500, 'equity': 550}, {'timestamp': 3000, 'equity': 570}],
            'trades': [
                {'id': 1, 'entry_time': 1500, 'exit_time': 1800, 'entry_price': 50,
                 'exit_price': 52, 'quantity': 10, 'pnl': 20, 'pnl_percent': 4,
                 'fees': 0, 'direction': 'LONG', 'reason': 'FIXED_RR_TARGET'},
                {'id': 2, 'entry_time': 2500, 'exit_time': 3000, 'entry_price': 50,
                 'exit_price': 55, 'quantity': 10, 'pnl': 50, 'pnl_percent': 10,
                 'fees': 0, 'direction': 'LONG', 'reason': 'FIXED_RR_TARGET'},
            ],
            'total_trades': 2, 'win_rate': 100, 'max_drawdown_percent': 0,
            'benchmark_return_percent': 14,
        }},
    ]
    result = aggregate_portfolio(data, runs)
    # BBB's first trade overlaps AAA and is ignored. Its next trade requests
    # 50% of the now-current 1100 balance, not 50% of the original balance.
    assert [(trade['symbol'], trade['entry_time']) for trade in result['trades']] == [
        ('AAA', 1000), ('BBB', 2500),
    ]
    assert result['trades'][1]['allocated_capital'] == pytest.approx(550)
    assert result['trades'][1]['quantity'] == pytest.approx(550 / 520 * 10)
    assert result['final_capital'] == pytest.approx(1100 + 50 * 550 / 520)
    assert result['portfolio']['capital_mode'] == 'SEQUENTIAL'
    assert result['portfolio']['skipped_overlapping_trades'] == 1
    assert result['portfolio']['assets'][1]['skipped_trades'] == 1
    assert all(left['exit_time'] <= right['entry_time']
               for left, right in zip(result['trades'], result['trades'][1:]))


@pytest.mark.skipif(not os.environ.get('DATABASE_URL'), reason='Requires PostgreSQL')
def test_portfolio_lifecycle_and_history_isolation():
    async def check():
        connection = await asyncpg.connect(os.environ['DATABASE_URL'])
        transaction = connection.transaction()
        await transaction.start()
        try:
            await connection.execute('ALTER TABLE backtest_runs ADD COLUMN IF NOT EXISTS parent_id uuid REFERENCES backtest_runs(id) ON DELETE CASCADE')
            data = request()
            for asset in data.assets:
                asset.request.symbol = str(uuid4()).upper()
                await connection.execute("""INSERT INTO trading_assets(symbol,category,price_precision,quantity_precision,minimum_order_size)
                    VALUES($1,'crypto',2,6,0.001)""", asset.request.symbol)

            class Pool:
                @asynccontextmanager
                async def acquire(self):
                    yield connection

                def __getattr__(self, name):
                    return getattr(connection, name)

            instance = BacktestService.__new__(BacktestService)
            instance.db = Pool()
            scheduled = []
            instance.schedule = scheduled.append
            user = str(uuid4())
            parent = await instance.create_portfolio_run(user, data)
            assert len(scheduled) == 3
            children = await connection.fetch('SELECT * FROM backtest_runs WHERE parent_id=$1 ORDER BY symbol', parent)
            for child in children:
                config = json.loads(child['request'])['config']
                asset = next(a for a in data.assets if a.request.symbol == child['symbol'])
                assert config['initial_capital'] == 1000 * asset.allocation_percent / 100
            for asset, result in zip(data.assets, results()):
                await connection.execute("UPDATE backtest_runs SET status='COMPLETED',progress=100,result=$3::jsonb WHERE parent_id=$1 AND symbol=$2",
                                         parent, asset.request.symbol, json.dumps(result['result']))
            await instance.execute(parent)
            saved = await instance.run(parent, user)
            assert saved['status'] == 'COMPLETED'
            assert saved['result']['net_profit'] == 20
            assert (await instance.runs(user))['total'] == 1
            assert await instance.run(parent, str(uuid4())) is None
            assert 'symbol' in (await instance.export(parent, user, 'csv'))[1]
            await instance.delete_run(parent, user)
            assert await connection.fetchval('SELECT count(*) FROM backtest_runs WHERE parent_id=$1', parent) == 0

            # A failed child must not produce a partial successful portfolio report.
            parent = await instance.create_portfolio_run(user, data)
            await connection.execute("UPDATE backtest_runs SET status='FAILED',error='missing candles' WHERE parent_id=$1", parent)
            await instance.execute(parent)
            failed = await instance.run(parent, user)
            assert failed['status'] == 'FAILED'
            assert failed['result'] is None
            assert 'missing candles' in failed['error']

            # Run the real Elliott engine for both children, then aggregate the persisted output.
            for asset in data.assets:
                asset.request.test_from = 50 * 60_000
                asset.request.test_to = 149 * 60_000
            candles = [{'timestamp': index * 60_000, 'open': 100 + sin(index / 5) * 10,
                        'close': 100 + sin(index / 5) * 10, 'high': 111, 'low': 89, 'volume': 10000}
                       for index in range(150)]
            instance.load_candles = AsyncMock(return_value={'M1': candles, 'M15': candles[::15], 'H1': candles[::60]})
            instance.semaphore = asyncio.Semaphore(2)
            parent = await instance.create_portfolio_run(user, data)
            for child in await connection.fetch('SELECT id FROM backtest_runs WHERE parent_id=$1', parent):
                await instance.execute(child['id'])
            await instance.execute(parent)
            real = await instance.run(parent, user)
            assert real['status'] == 'COMPLETED', real['error']
            assert real['result']['total_trades'] >= 0
            assert real['result']['final_capital'] == pytest.approx(real['result']['equity'][-1]['equity'])
            assert sum(item['net_profit'] for item in real['result']['portfolio']['assets']) == pytest.approx(real['result']['net_profit'])
        finally:
            await transaction.rollback()
            await connection.close()
    asyncio.run(check())


def test_asset_compaction_preserves_aggregate_inputs_and_effective_leverage():
    runs = results()
    for run in runs:
        run['result'].update(chart_candles=[{'large': 'payload'}], scenarios=[{'id': 'scenario'}],
                             strategy_config={'leverage': 2})
        run['result'] = compact_asset_result(run['result'])
        assert 'chart_candles' not in run['result']
        assert 'scenarios' not in run['result']
    combined = aggregate_portfolio(request().model_dump(), runs)
    assert combined['net_profit'] == 20
    assert all(trade['leverage'] == 2 for trade in combined['trades'])
