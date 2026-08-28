from __future__ import annotations

from itertools import product

from .models import AlgorithmOverrides, BacktestConfig
from .replay import initialize_indicators, run_smc_replay


def _score(report: dict, config) -> float:
    if report["total_trades"] < config.minimum_trades:
        return float("-inf")
    return report["total_return_percent"] - report["max_drawdown_percent"] * config.drawdown_penalty


def _summary(report: dict, parameters: dict, score: float) -> dict:
    return {
        "parameters": parameters,
        "score": score if score != float("-inf") else None,
        "total_return_percent": report["total_return_percent"],
        "max_drawdown_percent": report["max_drawdown_percent"],
        "total_trades": report["total_trades"],
        "win_rate": report["win_rate"],
        "profit_factor": report["profit_factor"],
    }


def optimize_smc_replay(
    training_candles: dict[str, list[dict]],
    validation_candles: dict[str, list[dict]],
    primary_timeframe: str,
    config: BacktestConfig,
    template_dir: str,
    progress_callback=None,
) -> dict:
    optimization = config.optimization
    template_id = "DEMO_SMC_V1"
    base = config.algorithm_overrides.get(template_id, AlgorithmOverrides())
    grid = {
        "minimum_ob_strength": [.35, .45, .55],
        "minimum_impulse_atr": [.8, 1, 1.2],
        "minimum_volume_ratio": [.8, 1],
        "minimum_adx": [15, 18, 22],
        "stop_buffer_atr": [.1],
        **optimization.parameter_grid,
    }
    for name, (minimum, maximum) in optimization.parameter_bounds.items():
        count = 2 if name == "minimum_volume_ratio" else 3
        grid[name] = [minimum] if minimum == maximum else [
            minimum + (maximum - minimum) * index / (count - 1) for index in range(count)
        ]
    names = list(grid)
    combinations = [dict(zip(names, values)) for values in product(
        *(grid[name] for name in names)
    )]
    total_combinations = len(combinations)
    if total_combinations > optimization.max_combinations:
        step = total_combinations / optimization.max_combinations
        combinations = [combinations[int(index * step)] for index in range(optimization.max_combinations)]
    validation_count = min(optimization.validation_candidates, len(combinations))
    progress_total = len(combinations) + validation_count
    progress_completed = 0
    if progress_callback:
        progress_callback(progress_completed, progress_total, "OPTIMIZATION")
    adx_periods = {base.adx_period}
    adx_periods.update(int(value) for value in grid.get("adx_period", []))
    initialize_indicators(training_candles, adx_periods)
    initialize_indicators(validation_candles, adx_periods)

    training_results = []
    for parameters in combinations:
        overrides = AlgorithmOverrides.model_validate({**base.model_dump(), **parameters})
        candidate_config = config.model_copy(update={
            "algorithm_overrides": {**config.algorithm_overrides, template_id: overrides},
        })
        report = run_smc_replay(training_candles, primary_timeframe, candidate_config, template_dir)
        score = _score(report, optimization)
        training_results.append((score, parameters, candidate_config, report))
        progress_completed += 1
        if progress_callback:
            progress_callback(progress_completed, progress_total, "OPTIMIZATION")
    training_results.sort(key=lambda item: item[0], reverse=True)

    validation_results = []
    for training_score, parameters, candidate_config, training_report in training_results[:optimization.validation_candidates]:
        report = run_smc_replay(validation_candles, primary_timeframe, candidate_config, template_dir)
        score = _score(report, optimization)
        validation_results.append((score, parameters, candidate_config, report, training_score, training_report))
        progress_completed += 1
        if progress_callback:
            progress_callback(progress_completed, progress_total, "VALIDATION")
    validation_results.sort(key=lambda item: item[0], reverse=True)
    if not validation_results or validation_results[0][0] == float("-inf"):
        raise ValueError("no optimization candidate satisfies the minimum trade count on validation")

    validation_score, parameters, _, winner, training_score, training_report = validation_results[0]
    winner["optimization"] = {
        "objective": "total_return_percent - max_drawdown_percent * drawdown_penalty",
        "available_combinations": total_combinations,
        "tested_combinations": len(combinations),
        "validated_candidates": len(validation_results),
        "best_parameters": parameters,
        "training_winner": _summary(training_report, parameters, training_score),
        "training_leaderboard": [
            _summary(report, candidate, score)
            for score, candidate, _, report in training_results[:20]
        ],
        "validation_leaderboard": [
            _summary(report, candidate, score)
            for score, candidate, _, report, _, _ in validation_results
        ],
    }
    return winner
