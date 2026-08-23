from math import exp
from .models import *
from .adaptive import AdaptiveModel,bandit_adjust,scenario_ml_features

class ProbabilityEngine:
    """Deterministic ensemble-compatible baseline; replace scorers with loaded ML models."""
    def __init__(self,adaptive=None):self.adaptive=adaptive or AdaptiveModel()
    def calculate(self,features:list[float],scenario=None,bandit_preference=None)->ProbabilityResponse:
        bounded=[max(-6,min(6,float(x))) for x in features]
        mean=sum(bounded)/len(bounded);spread=(sum((x-mean)**2 for x in bounded)/len(bounded))**.5
        sigmoid=lambda x:1/(1+exp(-x))
        gmdh=sigmoid(.65*mean);xgboost=sigmoid(.55*mean-.08*spread);lightgbm=sigmoid(.6*mean+.05*(bounded[0] if bounded else 0))
        meta=.25*gmdh+.35*xgboost+.4*lightgbm
        if scenario is not None:meta=bandit_adjust(self.adaptive.blend(meta,scenario_ml_features(scenario)),bandit_preference)
        details=ConfidenceDetails(gmdh=gmdh,xgboost=xgboost,lightgbm=lightgbm,meta=meta)
        return ProbabilityResponse(confidence=max(0,min(1,meta)),confidence_details=details)
    def scenario_features(self,s:Scenario)->list[float]:
        rr=abs(s.take_profit_prices[0]-(s.entry_zone_low+s.entry_zone_high)/2)/max(abs((s.entry_zone_low+s.entry_zone_high)/2-s.stop_loss_price),1e-12)
        return [2+(s.confidence-.5)*4,(rr-1)/2,min(3,len(s.reasons))*.25,-min(3,len(s.objections))*.25,min(3,len(s.objects_used))*.2]
