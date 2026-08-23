from src.algorithms import evaluate, fit_logistic, thompson_preferences, train_walk_forward

def samples(count=30):
    return [{"features":{"confidence":i/count,"risk_reward":2 if i>count/2 else .5,"direction_long":i%2},"outcome":1 if i>count/2 else 0} for i in range(count)]
def test_logistic_learns_separable_samples():
    w,b=fit_logistic(samples()); assert evaluate(samples(),w,b)["accuracy"]>.9
def test_walk_forward_returns_model_and_metrics():
    model,metrics=train_walk_forward(samples()); assert len(model["weights"])==5; assert 0<=metrics["f1"]<=1
def test_bandit_preferences_are_normalized_and_reproducible():
    first=thompson_preferences({"A":(10,1),"B":(1,10)},seed=7); second=thompson_preferences({"A":(10,1),"B":(1,10)},seed=7); assert first==second; assert abs(sum(first.values())-1)<1e-9; assert first["A"]>first["B"]

