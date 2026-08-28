from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from itertools import product
import multiprocessing
import os

from .models import AlgorithmOverrides, BacktestConfig
from .replay import initialize_indicators, precompute_external_patterns, run_smc_replay


_WORKER_CONTEXT = None


def _initialize_worker(candles, primary_timeframe, config, template_dir, external_patterns):
    global _WORKER_CONTEXT
    _WORKER_CONTEXT = (candles, primary_timeframe, config, template_dir, external_patterns)


def _evaluate_candidate(parameters):
    candles, primary_timeframe, config, template_dir, external_patterns = _WORKER_CONTEXT
    template_id = "DEMO_SMC_V1"
    base = config.algorithm_overrides.get(template_id, AlgorithmOverrides())
    overrides = AlgorithmOverrides.model_validate({**base.model_dump(), **parameters})
    candidate_config = config.model_copy(update={
        "algorithm_overrides": {**config.algorithm_overrides, template_id: overrides},
    })
    report = run_smc_replay(
        candles, primary_timeframe, candidate_config, template_dir, detailed=False,
        external_patterns=external_patterns,
    )
    return _score(report, config.optimization), parameters, candidate_config, report


def _evaluate_candidates(candles, primary_timeframe, config, template_dir, patterns, parameters):
    worker_limit = max(1, int(os.getenv("BACKTEST_OPTIMIZATION_WORKERS", "4")))
    workers = min(worker_limit, len(parameters))
    if workers == 1:
        _initialize_worker(candles, primary_timeframe, config, template_dir, patterns)
        return map(_evaluate_candidate, parameters)
    # The service runs optimization from an asyncio worker thread. Spawn is
    # safe in that situation; fork could inherit locks held by other threads.
    context = multiprocessing.get_context("spawn")
    executor = ProcessPoolExecutor(
        max_workers=workers, mp_context=context, initializer=_initialize_worker,
        initargs=(candles, primary_timeframe, config, template_dir, patterns),
    )
    return executor.map(_evaluate_candidate, parameters, chunksize=1), executor


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
        progress_callback(progress_completed, progress_total, "PREPARING_PATTERNS")
    adx_periods = {base.adx_period}
    adx_periods.update(int(value) for value in grid.get("adx_period", []))
    initialize_indicators(training_candles, adx_periods)
    initialize_indicators(validation_candles, adx_periods)
    # SMC structure does not depend on the optimization parameters. Evaluate
    # the external batch library once per dataset and replay its confirmed
    # events for every candidate.
    training_patterns = precompute_external_patterns(training_candles)
    validation_patterns = precompute_external_patterns(validation_candles)
    if progress_callback:
        progress_callback(progress_completed, progress_total, "OPTIMIZATION")

    training_results = []
    evaluated = _evaluate_candidates(
        training_candles, primary_timeframe, config, template_dir, training_patterns, combinations,
    )
    iterator, executor = evaluated if isinstance(evaluated, tuple) else (evaluated, None)
    try:
        for item in iterator:
            training_results.append(item)
            progress_completed += 1
            if progress_callback:
                progress_callback(progress_completed, progress_total, "OPTIMIZATION")
    finally:
        if executor is not None:
            executor.shutdown(wait=True, cancel_futures=True)
    training_results.sort(key=lambda item: item[0], reverse=True)

    validation_results = []
    validation_parameters = [item[1] for item in training_results[:optimization.validation_candidates]]
    training_by_parameters = {tuple(sorted(item[1].items())): item for item in training_results}
    evaluated = _evaluate_candidates(
        validation_candles, primary_timeframe, config, template_dir, validation_patterns, validation_parameters,
    )
    iterator, executor = evaluated if isinstance(evaluated, tuple) else (evaluated, None)
    try:
        for score, parameters, candidate_config, report in iterator:
            training_score, _, _, training_report = training_by_parameters[tuple(sorted(parameters.items()))]
            validation_results.append((score, parameters, candidate_config, report, training_score, training_report))
            progress_completed += 1
            if progress_callback:
                progress_callback(progress_completed, progress_total, "VALIDATION")
    finally:
        if executor is not None:
            executor.shutdown(wait=True, cancel_futures=True)
    validation_results.sort(key=lambda item: item[0], reverse=True)
    if not validation_results or validation_results[0][0] == float("-inf"):
        raise ValueError("no optimization candidate satisfies the minimum trade count on validation")

    validation_score, parameters, winner_config, _, training_score, training_report = validation_results[0]
    # Produce the large audit/chart payload once, for the selected candidate.
    winner = run_smc_replay(
        validation_candles, primary_timeframe, winner_config, template_dir, detailed=True,
        external_patterns=validation_patterns,
    )
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
