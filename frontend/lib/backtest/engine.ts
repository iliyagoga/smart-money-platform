import type { BacktestInput, BacktestResult, BacktestTrade, OpenBacktestPosition, TradeDirection } from "./types";

const average = (values: number[], end: number, period: number): number => {
  let sum = 0;
  for (let index = end - period + 1; index <= end; index += 1) sum += values[index];
  return sum / period;
};

export function runBacktest({ candles, settings }: BacktestInput): BacktestResult {
  const sortedCandles = [...candles].sort((left, right) => left.timestamp - right.timestamp);
  const closes = sortedCandles.map((candle) => candle.close);
  const feeRate = settings.feePercent / 100;
  const slippageRate = settings.slippagePercent / 100;
  let capital = settings.initialCapital;
  let position: OpenBacktestPosition | undefined;
  const trades: BacktestTrade[] = [];
  const equity = [{ timestamp: sortedCandles[0]?.timestamp ?? 0, equity: capital }];

  const closePosition = (rawPrice: number, timestamp: number, reason: BacktestTrade["reason"]) => {
    if (!position) return;
    const exitPrice = rawPrice * (position.direction === "LONG" ? 1 - slippageRate : 1 + slippageRate);
    const multiplier = position.direction === "LONG" ? 1 : -1;
    const grossPnl = (exitPrice - position.entryPrice) * position.quantity * multiplier;
    const fees = (position.entryPrice + exitPrice) * position.quantity * feeRate;
    const pnl = grossPnl - fees;
    capital += pnl;
    trades.push({
      id: trades.length + 1,
      direction: position.direction,
      entryTime: position.entryTime,
      exitTime: timestamp,
      entryPrice: position.entryPrice,
      exitPrice,
      quantity: position.quantity,
      pnl,
      pnlPercent: pnl / (position.entryPrice * position.quantity) * 100,
      reason,
    });
    position = undefined;
  };

  const openPosition = (direction: TradeDirection, price: number, timestamp: number) => {
    const entryPrice = price * (direction === "LONG" ? 1 + slippageRate : 1 - slippageRate);
    const allocatedCapital = capital * settings.positionSizePercent / 100;
    position = { direction, entryPrice, entryTime: timestamp, quantity: allocatedCapital / entryPrice };
  };

  for (let index = settings.slowPeriod; index < sortedCandles.length; index += 1) {
    const candle = sortedCandles[index];
    const previousFast = average(closes, index - 1, settings.fastPeriod);
    const previousSlow = average(closes, index - 1, settings.slowPeriod);
    const fast = average(closes, index, settings.fastPeriod);
    const slow = average(closes, index, settings.slowPeriod);
    const longSignal = previousFast <= previousSlow && fast > slow;
    const shortSignal = previousFast >= previousSlow && fast < slow;

    if (position) {
      const movePercent = (candle.close - position.entryPrice) / position.entryPrice * 100 * (position.direction === "LONG" ? 1 : -1);
      if (movePercent <= -settings.stopLossPercent) closePosition(candle.close, candle.timestamp, "STOP_LOSS");
      else if (movePercent >= settings.takeProfitPercent) closePosition(candle.close, candle.timestamp, "TAKE_PROFIT");
      else if ((position.direction === "LONG" && shortSignal) || (position.direction === "SHORT" && longSignal)) {
        closePosition(candle.close, candle.timestamp, "SIGNAL");
      }
    }

    if (!position) {
      if (longSignal && settings.directionMode !== "SHORT") openPosition("LONG", candle.close, candle.timestamp);
      else if (shortSignal && settings.directionMode !== "LONG") openPosition("SHORT", candle.close, candle.timestamp);
    }

    const unrealized = position
      ? (candle.close - position.entryPrice) * position.quantity * (position.direction === "LONG" ? 1 : -1)
      : 0;
    equity.push({ timestamp: candle.timestamp, equity: capital + unrealized });
  }

  const lastCandle = sortedCandles.at(-1);
  if (position && lastCandle) closePosition(lastCandle.close, lastCandle.timestamp, "END_OF_DATA");
  if (lastCandle) equity.push({ timestamp: lastCandle.timestamp, equity: capital });

  let peak = settings.initialCapital;
  let maxDrawdownPercent = 0;
  equity.forEach((point) => {
    peak = Math.max(peak, point.equity);
    maxDrawdownPercent = Math.max(maxDrawdownPercent, (peak - point.equity) / peak * 100);
  });
  const wins = trades.filter((trade) => trade.pnl > 0);
  const grossProfit = wins.reduce((sum, trade) => sum + trade.pnl, 0);
  const grossLoss = Math.abs(trades.filter((trade) => trade.pnl < 0).reduce((sum, trade) => sum + trade.pnl, 0));
  const netProfit = capital - settings.initialCapital;

  return {
    initialCapital: settings.initialCapital,
    finalCapital: capital,
    netProfit,
    totalReturnPercent: netProfit / settings.initialCapital * 100,
    maxDrawdownPercent,
    winRate: trades.length ? wins.length / trades.length * 100 : 0,
    profitFactor: grossLoss ? grossProfit / grossLoss : undefined,
    totalTrades: trades.length,
    averageTrade: trades.length ? netProfit / trades.length : 0,
    trades,
    equity,
    chartCandles: sortedCandles.map(({ timestamp, open, high, low, close, volume }) => ({ timestamp, open, high, low, close, volume })),
    chartCandlesByTimeframe: {},
    structureOverlaysByTimeframe: {},
    scenarios: [],
    patternDiagnostics: {},
  };
}
