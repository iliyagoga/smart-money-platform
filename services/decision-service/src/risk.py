from .models import *

class RiskManager:
    def calculate(self,signal:TradeSignal,capital:float,config:RiskConfig,daily_pnl:float=0,open_positions:int=0)->RiskDecision:
        if daily_pnl<0 and abs(daily_pnl)/capital*100>=config.max_daily_loss_percent:return RiskDecision(signal_id=signal.signal_id,approved=False,rejection_reason="Daily loss limit exceeded")
        if open_positions>=config.max_positions:return RiskDecision(signal_id=signal.signal_id,approved=False,rejection_reason="Maximum open positions reached")
        distance=abs(signal.entry_price-signal.stop_loss_price)
        if distance<=0:return RiskDecision(signal_id=signal.signal_id,approved=False,rejection_reason="Stop loss distance must be positive")
        kelly=max(0,2*signal.confidence-1)*config.kelly_fraction*100
        risk_percent=min(config.max_risk_per_trade_percent,kelly)
        risk_amount=capital*risk_percent/100;size=risk_amount/distance
        if size<config.min_position_size:return RiskDecision(signal_id=signal.signal_id,approved=False,position_size=size,rejection_reason="Position size below minimum")
        return RiskDecision(signal_id=signal.signal_id,approved=True,position_size=size,position_value=size*signal.entry_price,
          leverage=config.leverage,risk_amount=risk_amount,risk_percent_of_capital=risk_percent)
