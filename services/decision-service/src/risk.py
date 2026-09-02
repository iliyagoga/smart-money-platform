from .models import *

class RiskManager:
    def calculate(self,signal:TradeSignal,capital:float,config:RiskConfig,daily_pnl:float=0,
                  open_positions:int=0,active_orders:int=0,consecutive_losses:int=0,
                  last_loss_at:int|None=None,now:int|None=None,
                  ignore_loss_limits:bool=False)->RiskDecision:
        timestamp=now if now is not None else now_ms()
        decision_meta={"consecutive_losses":consecutive_losses}
        if not ignore_loss_limits and daily_pnl<0 and abs(daily_pnl)/capital*100>=config.max_daily_loss_percent:return RiskDecision(signal_id=signal.signal_id,approved=False,rejection_reason="Daily loss limit exceeded")
        # The strategy is deliberately sequential: a pending order or an open
        # position reserves the only trading slot.
        if open_positions+active_orders>=min(config.max_positions,1):return RiskDecision(signal_id=signal.signal_id,approved=False,rejection_reason="Another trade is still active",**decision_meta)
        cooldown_hours=0
        if consecutive_losses>=config.loss_streak_daily_stop:cooldown_hours=config.daily_stop_hours
        elif consecutive_losses>=2:cooldown_hours=config.two_loss_cooldown_hours
        cooldown_until=(last_loss_at+cooldown_hours*3_600_000) if last_loss_at is not None and cooldown_hours else None
        if not ignore_loss_limits and cooldown_until is not None and timestamp<cooldown_until:
            return RiskDecision(signal_id=signal.signal_id,approved=False,
              rejection_reason=f"Loss-streak cooldown active until {cooldown_until}",
              cooldown_until=cooldown_until,capital_multiplier=config.loss_size_multiplier,**decision_meta)
        distance=abs(signal.entry_price-signal.stop_loss_price)
        if distance<=0:return RiskDecision(signal_id=signal.signal_id,approved=False,rejection_reason="Stop loss distance must be positive")
        kelly=max(0,2*signal.confidence-1)*config.kelly_fraction*100
        risk_percent=min(config.max_risk_per_trade_percent,kelly)
        capital_multiplier=config.loss_size_multiplier if consecutive_losses and not ignore_loss_limits else 1
        risk_amount=capital*capital_multiplier*risk_percent/100;size=risk_amount/distance
        if size<config.min_position_size:return RiskDecision(signal_id=signal.signal_id,approved=False,position_size=size,rejection_reason="Position size below minimum")
        return RiskDecision(signal_id=signal.signal_id,approved=True,position_size=size,position_value=size*signal.entry_price,
          leverage=config.leverage,risk_amount=risk_amount,risk_percent_of_capital=risk_percent*capital_multiplier,
          capital_multiplier=capital_multiplier,**decision_meta)
