"""Aggregate independently funded assets on a shared timeline, without rebalancing."""
from math import sqrt
from statistics import mean, pstdev

from .performance import extended_performance


def compact_asset_result(result: dict) -> dict:
    # Portfolio reports use combined equity/trades, not individual price-chart payloads.
    omitted = {'chart_candles', 'chart_candles_by_timeframe', 'scenarios',
               'elliott_patterns', 'pattern_diagnostics', 'decisions'}
    return {key: value for key, value in result.items() if key not in omitted}


def aggregate_portfolio(request: dict, runs: list[dict]) -> dict:
    initial = request['initial_capital']
    start = request['assets'][0]['request']['test_from']
    end = request['assets'][0]['request']['test_to']
    cash = max(0.0, initial * (1 - sum(a['allocation_percent'] for a in request['assets']) / 100))
    balances, events, trades, contributions = [], {}, [], []
    benchmark = 0.0
    for index, (asset, run) in enumerate(zip(request['assets'], runs, strict=True)):
        result = run['result']
        capital = initial * asset['allocation_percent'] / 100
        balances.append(capital)
        for point in result['equity']:
            if start <= point['timestamp'] <= end:
                # The last point wins when the engine closes a position at the same timestamp.
                events.setdefault(point['timestamp'], {})[index] = point['equity']
        events.setdefault(end, {})[index] = result['final_capital']
        symbol = asset['request']['symbol']
        for trade in result['trades']:
            trades.append({**trade, 'symbol': symbol, 'run_id': str(run['id']),
                           'leverage': result.get('strategy_config', {}).get('leverage', asset['request']['config']['leverage'])})
        pnl = result['final_capital'] - capital
        contributions.append({
            'symbol': symbol, 'run_id': str(run['id']), 'allocation_percent': asset['allocation_percent'],
            'initial_capital': capital, 'final_capital': result['final_capital'], 'net_profit': pnl,
            'total_return_percent': pnl / capital * 100, 'contribution_percent': pnl / initial * 100,
            'total_trades': result['total_trades'], 'win_rate': result['win_rate'],
            'max_drawdown_percent': result['max_drawdown_percent'],
        })
        benchmark += result.get('benchmark_return_percent', 0) * asset['allocation_percent'] / 100
    equity = [{'timestamp': start, 'equity': initial}]
    for timestamp, updates in sorted(events.items()):
        for index, value in updates.items():
            balances[index] = value
        point = {'timestamp': timestamp, 'equity': cash + sum(balances)}
        if equity[-1]['timestamp'] == timestamp:
            equity[-1] = point
        else:
            equity.append(point)
    final = cash + sum(balances)
    peak, drawdown = initial, 0.0
    for point in equity:
        peak = max(peak, point['equity'])
        drawdown = max(drawdown, (peak - point['equity']) / peak * 100)
    trades.sort(key=lambda trade: (trade['exit_time'], trade['entry_time'], trade['symbol']))
    for index, trade in enumerate(trades, 1):
        trade['id'] = index
    wins = [trade for trade in trades if trade['pnl'] > 0]
    profit = sum(trade['pnl'] for trade in wins)
    loss = -sum(trade['pnl'] for trade in trades if trade['pnl'] < 0)
    # Daily observations keep annualization independent of each asset's candle timeframe.
    daily = {}
    for point in equity:
        daily[point['timestamp'] // 86_400_000] = point['equity']
    previous, returns = initial, []
    for day in range(start // 86_400_000, end // 86_400_000 + 1):
        value = daily.get(day, previous)
        returns.append(value / previous - 1 if previous > 0 else 0.0)
        previous = value
    sharpe = mean(returns) / pstdev(returns) * sqrt(365) if len(returns) > 1 and pstdev(returns) else 0.0
    return {
        'initial_capital': initial, 'final_capital': final, 'net_profit': final - initial,
        'total_return_percent': (final / initial - 1) * 100, 'max_drawdown_percent': drawdown,
        'total_trades': len(trades), 'win_rate': len(wins) / len(trades) * 100 if trades else 0,
        'profit_factor': profit / loss if loss else None,
        'average_trade': (final - initial) / len(trades) if trades else 0,
        'sharpe_ratio': sharpe, 'benchmark_return_percent': benchmark,
        'trades': trades, 'equity': equity, 'portfolio': {
            'name': request['name'], 'cash': cash, 'assets': contributions,
            'request': request, 'drawdown_basis': 'SYNCHRONIZED_EQUITY',
        },
        'dataset': {'test_from': start, 'test_to': end, 'closed_candles_only': True,
                    'test_candles': sum(run['result'].get('dataset', {}).get('test_candles', 0) for run in runs),
                    'timeframes': sorted({tf for asset in request['assets'] for tf in asset['request']['timeframes']})},
        **extended_performance(initial, final, equity),
    }
