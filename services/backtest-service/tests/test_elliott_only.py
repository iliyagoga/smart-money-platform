import pytest
from pydantic import ValidationError
from src.models import BacktestConfig, BacktestCreate


def test_default_request_uses_elliott_timeframes():
    request = BacktestCreate(symbol="btc-usdt-swap")
    assert request.config.strategy == "ELLIOTT"
    assert request.timeframe == request.config.elliott.entry_timeframe
    assert set((request.config.elliott.entry_timeframe, request.config.elliott.structure_timeframe,
                request.config.elliott.macro_timeframe)) <= set(request.timeframes)


@pytest.mark.parametrize("strategy", ["SMC", "SMA_CROSS", "RSI", "MACD", "BOLLINGER"])
def test_unsupported_strategies_are_rejected(strategy):
    with pytest.raises(ValidationError):
        BacktestConfig(strategy=strategy)


def test_training_and_template_options_are_not_exposed():
    assert not {"template_ids", "local_retraining", "smc_target_rr"} & BacktestConfig.model_fields.keys()
    assert not {"train_from", "train_to", "model_version"} & BacktestCreate.model_fields.keys()
