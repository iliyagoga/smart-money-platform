from math import floor,isfinite

from .models import *

class RiskManager:
    def calculate(self,signal:TradeSignal,capital:float,config:RiskConfig,daily_pnl:float=0,
                  open_positions:int=0,active_orders:int=0,consecutive_losses:int=0,
                  last_loss_at:int|None=None,now:int|None=None,
                  ignore_loss_limits:bool=False,risk_percent_override:float|None=None,
                  allocation_percent:float=100,use_margin:bool=True,leverage_override:int|None=None,
                  lot_size:float|None=None,minimum_order_size:float|None=None,
                  capital_ceiling:float|None=None,loss_limit_capital:float|None=None)->RiskDecision:
        timestamp=now if now is not None else now_ms()
        decision_meta={"consecutive_losses":consecutive_losses}
        if not isfinite(capital) or capital<=0:return RiskDecision(signal_id=signal.signal_id,approved=False,rejection_reason="Trading capital must be positive")
        loss_capital=capital if loss_limit_capital is None else loss_limit_capital
        if not isfinite(loss_capital) or loss_capital<=0:return RiskDecision(signal_id=signal.signal_id,approved=False,rejection_reason="Trading capital must be positive")
        if not ignore_loss_limits and daily_pnl<0 and abs(daily_pnl)/loss_capital*100>=config.max_daily_loss_percent:return RiskDecision(signal_id=signal.signal_id,approved=False,rejection_reason="Daily loss limit exceeded")
        # The caller scopes occupancy to the asset for allocated portfolios and
        # to the whole trading loop for sequential portfolios.
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
        if risk_percent_override is None:
            risk_percent=min(config.max_risk_per_trade_percent,kelly)
        else:
            # The platform risk config is a hard production safety boundary.
            # A per-asset value of zero means "no custom limit", not "disable risk control".
            requested=risk_percent_override if risk_percent_override>0 else config.max_risk_per_trade_percent
            risk_percent=min(config.max_risk_per_trade_percent,requested)
        capital_multiplier=config.loss_size_multiplier if consecutive_losses and not ignore_loss_limits else 1
        capital_base=min(capital,capital_ceiling) if capital_ceiling is not None else capital
        sizing_capital=capital_base*max(0,min(allocation_percent,100))/100*capital_multiplier
        leverage=min(leverage_override or config.leverage,config.leverage) if use_margin else 1
        capacity=sizing_capital*leverage/signal.entry_price
        size=capacity if risk_percent==0 else min(sizing_capital*risk_percent/100/distance,capacity)
        if lot_size:
            size=floor((size+lot_size*1e-9)/lot_size)*lot_size
        minimum=max(config.min_position_size,minimum_order_size or 0)
        risk_amount=distance*size
        if size<minimum:return RiskDecision(signal_id=signal.signal_id,approved=False,position_size=size,rejection_reason="Position size below minimum")
        return RiskDecision(signal_id=signal.signal_id,approved=True,position_size=size,position_value=size*signal.entry_price,
          leverage=leverage,risk_amount=risk_amount,risk_percent_of_capital=risk_amount/capital*100 if capital else 0,
          capital_multiplier=capital_multiplier,**decision_meta)
