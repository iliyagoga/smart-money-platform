import type { BacktestSettings } from "./types";

export const defaultBacktestSettings: BacktestSettings = {
  initialCapital: 10_000, strategy: "ELLIOTT", fastPeriod: 9, slowPeriod: 21,
  feePercent: 0.05, makerFeePercent: 0.02, takerFeePercent: 0.05, slippagePercent: 0.02,
  stopLossPercent: 2, takeProfitPercent: 4, positionSizePercent: 25, leverage: 1,
  fundingPercentPerDay: 0, fundingIntervalHours: 8, executionLatencyMs: 0,
  tickSize: 0.01, lotSize: 0.000001, minimumOrderSize: 0.000001,
  volumeParticipationPercent: 5, liquidationFeePercent: 0.5, trailingStopPercent: undefined,
  directionMode: "BOTH", riskPerTradePercent: 1, smcTargetMode: "TEMPLATE", smcTargetRr: 1.5,
  smcMinTargetRr: 1.5, smcMaxTargetRr: 8, kellyFraction: 0.25, confidenceThreshold: 0.5,
  templateIds: [], localRetraining: false,
  elliott: {
    useMargin: false, reinvestProfits: true, macroTimeframe: "H4", structureTimeframe: "H1", entryTimeframe: "M15",
    atrPeriod: 14, zigzagReversalAtr: 1.5, minSwingAtr: 1, wave1MinAtr: 1.5, wave1MinEfficiency: 0.45,
    wave2MinRetracement: 0.382, wave2MaxRetracement: 0.786, entryModel: "CHOCH_RETRACE", entryRetracement: 0.5,
    entryExpiryBars: 4, chochMinAtr: 0.5, chochMinBodyRatio: 0.5, macroFilter: "STRUCTURE", adxPeriod: 14,
    adxMin: 0, requireDiConfirmation: false, stopBufferAtr: 0.2, takeProfitCount: 2, takeProfitRr: 2,
    secondTakeProfitRr: 3, minimumRr: 1.5, breakEvenAtOneR: false, firstTakeAction: "PARTIAL_CLOSE",
  },
};
