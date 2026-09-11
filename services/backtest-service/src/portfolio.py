"""Aggregate portfolio asset replays using fixed or shared sequential capital."""
from math import floor, sqrt
from statistics import mean, pstdev

from .performance import extended_performance


def compact_asset_result(result: dict) -> dict:
    # Portfolio reports use combined equity/trades, not individual price-chart payloads.
    omitted = {'chart_candles', 'chart_candles_by_timeframe', 'scenarios',
               'elliott_patterns', 'pattern_diagnostics', 'decisions'}
    return {key: value for key, value in result.items() if key not in omitted}


def aggregate_portfolio(request: dict, runs: list[dict]) -> dict:
    if request.get('capital_mode', 'ALLOCATED') == 'SEQUENTIAL':
        return _aggregate_sequential(request, runs)
    return _aggregate_allocated(request, runs)


def _aggregate_allocated(request: dict, runs: list[dict]) -> dict:
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
            'name': request['name'], 'cash': cash, 'capital_mode': 'ALLOCATED', 'assets': contributions,
            'request': request, 'drawdown_basis': 'SYNCHRONIZED_EQUITY',
        },
        'dataset': {'test_from': start, 'test_to': end, 'closed_candles_only': True,
                    'test_candles': sum(run['result'].get('dataset', {}).get('test_candles', 0) for run in runs),
                    'timeframes': sorted({tf for asset in request['assets'] for tf in asset['request']['timeframes']})},
        **extended_performance(initial, final, equity),
    }


def _scaled_trade(trade: dict, desired_capital: float, source_capital: float,
                  config: dict) -> tuple[dict, float] | None:
    """Scale a candidate produced by an isolated replay to the shared capital."""
    if desired_capital <= 0 or source_capital <= 0:
        return None
    original_quantity = float(trade.get('quantity', 0))
    ratio = desired_capital / source_capital
    if original_quantity > 0:
        lot = float(config.get('lot_size') or 0)
        capital_quantity = float(trade.get('capital_quantity', original_quantity)) * ratio
        volume_capacity = float(trade.get('volume_capacity_quantity', float('inf')))
        quantity = min(capital_quantity, volume_capacity)
        if lot > 0:
            quantity = floor((quantity + lot * 1e-9) / lot) * lot
        minimum = float(config.get('minimum_order_size') or 0)
        if quantity <= 0 or quantity + 1e-12 < minimum:
            return None
        ratio = quantity / original_quantity
    else:
        quantity = original_quantity

    scaled = {**trade, 'quantity': quantity}
    for field in ('pnl', 'fees', 'funding', 'risk_capital'):
        if field in scaled and scaled[field] is not None:
            scaled[field] = float(scaled[field]) * ratio
    scaled['exits'] = [
        {**item,
         'quantity': float(item.get('quantity', 0)) * ratio,
         'pnl': float(item.get('pnl', 0)) * ratio,
         'fees': float(item.get('fees', 0)) * ratio}
        for item in trade.get('exits', [])
    ]
    return scaled, ratio


def _append_equity(equity: list[dict], point: dict) -> None:
    if equity and equity[-1]['timestamp'] == point['timestamp']:
        equity[-1] = point
    else:
        equity.append(point)


def _aggregate_sequential(request: dict, runs: list[dict]) -> dict:
    """Use one shared balance and permit at most one open trade across all assets."""
    initial = float(request['initial_capital'])
    start = request['assets'][0]['request']['test_from']
    end = request['assets'][0]['request']['test_to']
    candidates = []
    benchmark_weights = 0.0

    for asset_index, (asset, run) in enumerate(zip(request['assets'], runs, strict=True)):
        result = run['result']
        source_capital = float(result.get('initial_capital') or
                               initial * asset['allocation_percent'] / 100)
        config = asset['request']['config']
        reinvest = config.get('elliott', {}).get('reinvest_profits', True)
        for trade_index, trade in enumerate(sorted(
                result.get('trades', []), key=lambda item: (item['entry_time'], item['exit_time'], item.get('id', 0)))):
            sizing_source = source_capital if reinvest else min(
                float(result.get('initial_capital', source_capital)), source_capital)
            candidates.append({
                'asset_index': asset_index, 'trade_index': trade_index, 'asset': asset,
                'run': run, 'trade': trade, 'source_capital': sizing_source,
                'source_equity_base': source_capital, 'reinvest': reinvest,
            })
            source_capital += float(trade.get('pnl', 0))
        benchmark_weights += float(asset['allocation_percent'])

    candidates.sort(key=lambda item: (
        item['trade']['entry_time'], item['asset_index'], item['trade']['exit_time'], item['trade_index']))
    capital = initial
    available_at = start
    trades = []
    equity = [{'timestamp': start, 'equity': initial}]
    asset_pnl = [0.0 for _ in runs]
    asset_paths = [[initial] for _ in runs]
    skipped = [0 for _ in runs]

    for candidate in candidates:
        trade = candidate['trade']
        asset_index = candidate['asset_index']
        if trade['entry_time'] < available_at:
            skipped[asset_index] += 1
            continue
        allocation = float(candidate['asset']['allocation_percent']) / 100
        capital_base = max(0.0, capital)
        if not candidate['reinvest']:
            capital_base = min(initial, capital_base)
        desired_capital = capital_base * allocation
        effective_config = {
            **candidate['asset']['request']['config'],
            **candidate['run']['result'].get('strategy_config', {}),
        }
        scaled_result = _scaled_trade(
            trade, desired_capital, candidate['source_capital'], effective_config)
        if scaled_result is None:
            skipped[asset_index] += 1
            continue
        scaled, scale = scaled_result
        capital_before = capital
        symbol = candidate['asset']['request']['symbol']
        scaled.update({
            'symbol': symbol, 'run_id': str(candidate['run']['id']),
            'capital_before': capital_before, 'allocated_capital': desired_capital,
            'allocation_percent': float(candidate['asset']['allocation_percent']),
            'leverage': candidate['run']['result'].get('strategy_config', {}).get(
                'leverage', candidate['asset']['request']['config'].get('leverage', 1)),
        })

        # Reuse the isolated replay's mark-to-market path, translated to the
        # actual balance and position size used by this sequential trade.
        for point in candidate['run']['result'].get('equity', []):
            timestamp = point['timestamp']
            if trade['entry_time'] <= timestamp <= trade['exit_time']:
                translated = {
                    'timestamp': timestamp,
                    'equity': capital_before +
                              (float(point['equity']) - candidate['source_equity_base']) * scale,
                }
                if 'intrabar_min_equity' in point:
                    translated['intrabar_min_equity'] = capital_before + (
                        float(point['intrabar_min_equity']) - candidate['source_equity_base']) * scale
                _append_equity(equity, translated)

        capital += float(scaled.get('pnl', 0))
        _append_equity(equity, {'timestamp': trade['exit_time'], 'equity': capital})
        available_at = trade['exit_time']
        asset_pnl[asset_index] += float(scaled.get('pnl', 0))
        asset_paths[asset_index].append(initial + asset_pnl[asset_index])
        trades.append(scaled)

    if equity[-1]['timestamp'] < end:
        equity.append({'timestamp': end, 'equity': capital})
    for index, trade in enumerate(trades, 1):
        trade['id'] = index

    wins = [trade for trade in trades if trade.get('pnl', 0) > 0]
    profit = sum(trade['pnl'] for trade in wins)
    loss = -sum(trade['pnl'] for trade in trades if trade.get('pnl', 0) < 0)
    peak, drawdown = initial, 0.0
    for point in equity:
        peak = max(peak, point['equity'])
        observed = point.get('intrabar_min_equity', point['equity'])
        drawdown = max(drawdown, (peak - observed) / peak * 100 if peak > 0 else 0)

    contributions = []
    for index, (asset, run) in enumerate(zip(request['assets'], runs, strict=True)):
        relevant = [trade for trade in trades if trade['symbol'] == asset['request']['symbol']]
        pnl = asset_pnl[index]
        path_peak, asset_drawdown = initial, 0.0
        for value in asset_paths[index]:
            path_peak = max(path_peak, value)
            asset_drawdown = max(asset_drawdown, (path_peak - value) / path_peak * 100 if path_peak > 0 else 0)
        contributions.append({
            'symbol': asset['request']['symbol'], 'run_id': str(run['id']),
            'allocation_percent': float(asset['allocation_percent']),
            'initial_capital': initial, 'final_capital': initial + pnl, 'net_profit': pnl,
            'total_return_percent': pnl / initial * 100,
            'contribution_percent': pnl / initial * 100,
            'total_trades': len(relevant),
            'skipped_trades': skipped[index],
            'win_rate': len([trade for trade in relevant if trade.get('pnl', 0) > 0]) / len(relevant) * 100
                        if relevant else 0,
            'max_drawdown_percent': asset_drawdown,
        })

    daily = {}
    for point in equity:
        daily[point['timestamp'] // 86_400_000] = point['equity']
    previous, returns = initial, []
    for day in range(start // 86_400_000, end // 86_400_000 + 1):
        value = daily.get(day, previous)
        returns.append(value / previous - 1 if previous > 0 else 0.0)
        previous = value
    sharpe = mean(returns) / pstdev(returns) * sqrt(365) if len(returns) > 1 and pstdev(returns) else 0.0
    benchmark = sum(
        run['result'].get('benchmark_return_percent', 0) * float(asset['allocation_percent'])
        for asset, run in zip(request['assets'], runs, strict=True)
    ) / benchmark_weights if benchmark_weights else 0.0
    return {
        'initial_capital': initial, 'final_capital': capital, 'net_profit': capital - initial,
        'total_return_percent': (capital / initial - 1) * 100,
        'max_drawdown_percent': drawdown, 'total_trades': len(trades),
        'win_rate': len(wins) / len(trades) * 100 if trades else 0,
        'profit_factor': profit / loss if loss else None,
        'average_trade': (capital - initial) / len(trades) if trades else 0,
        'sharpe_ratio': sharpe, 'benchmark_return_percent': benchmark,
        'trades': trades, 'equity': equity,
        'portfolio': {
            'name': request['name'], 'cash': 0.0, 'capital_mode': 'SEQUENTIAL',
            'assets': contributions, 'request': request,
            'drawdown_basis': 'SEQUENTIAL_SHARED_EQUITY',
            'skipped_overlapping_trades': sum(skipped),
        },
        'dataset': {
            'test_from': start, 'test_to': end, 'closed_candles_only': True,
            'test_candles': sum(run['result'].get('dataset', {}).get('test_candles', 0) for run in runs),
            'timeframes': sorted({tf for asset in request['assets'] for tf in asset['request']['timeframes']}),
        },
        **extended_performance(initial, capital, equity),
    }
