import { describe, expect, it } from "vitest";
import { toBackendBacktestConfig } from "./backendConfig";
import { defaultBacktestSettings } from "./defaultSettings";

describe("backtest configuration serialization", () => {
  it("uses one complete snake-case contract for single and portfolio runs", () => {
    const config = toBackendBacktestConfig(defaultBacktestSettings);

    expect(config).toMatchObject({
      strategy: "ELLIOTT",
      initial_capital: 10_000,
      risk_per_trade_percent: 1,
      maker_fee_percent: .02,
      execution_latency_ms: 0,
      elliott: {
        entry_model: "CHOCH_RETRACE",
        entry_expiry_bars: 4,
        first_take_action: "PARTIAL_CLOSE",
        break_even_at_one_r: false,
      },
    });
  });

  it("applies exchange metadata and preserves backend-only fields", () => {
    const config = toBackendBacktestConfig(
      defaultBacktestSettings,
      { tickSize: .1, lotSize: .01, minimumOrderSize: .1 },
      { maintenance_margin_percent: .75, elliott: { wave1_min_candles: 5 } },
    );

    expect(config).toMatchObject({
      tick_size: .1,
      lot_size: .01,
      minimum_order_size: .1,
      maintenance_margin_percent: .75,
      elliott: { wave1_min_candles: 5, atr_period: 14 },
    });
  });
});
