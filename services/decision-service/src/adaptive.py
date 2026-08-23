import math
class AdaptiveModel:
    def __init__(self,weight=.35):self.weight=weight;self.version=None;self.feature_names=[];self.weights=[];self.bias=0.
    @property
    def loaded(self):return bool(self.version and self.weights)
    def load(self,a):
        names=list(a.get("feature_names",[]));weights=[float(x) for x in a.get("weights",[])]
        if not names or len(names)!=len(weights):raise ValueError("Invalid model artifact")
        self.version=a["version"];self.feature_names=names;self.weights=weights;self.bias=float(a.get("bias",0))
    def predict(self,f):
        z=max(-30,min(30,self.bias+sum(w*float(f.get(n,0)) for n,w in zip(self.feature_names,self.weights))));return 1/(1+math.exp(-z))
    def blend(self,baseline,f):return baseline if not self.loaded else baseline*(1-self.weight)+self.predict(f)*self.weight
def scenario_ml_features(s):
    entry=(s.entry_zone_low+s.entry_zone_high)/2;risk=abs(entry-s.stop_loss_price);reward=abs(s.take_profit_prices[0]-entry)
    return {"confidence":float(s.confidence),"risk_reward":reward/risk if risk else 0,"pnl_excursion_ratio":0,"duration_log":0,"direction_long":1 if s.direction=="LONG" else 0}
def bandit_adjust(confidence,preference,max_adjustment=.05):
    if preference is None:return confidence
    return max(0,min(1,confidence+max(-max_adjustment,min(max_adjustment,(preference-.5)*2*max_adjustment))))
