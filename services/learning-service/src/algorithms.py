from __future__ import annotations

import math
import random


FEATURE_NAMES = ("confidence", "risk_reward", "pnl_excursion_ratio", "duration_log", "direction_long")


def feature_vector(features: dict) -> list[float]:
    return [float(features.get(name, 0)) for name in FEATURE_NAMES]


def sigmoid(value: float) -> float:
    value = max(-30.0, min(30.0, value))
    return 1.0 / (1.0 + math.exp(-value))


def fit_logistic(samples: list[dict], epochs: int = 500, rate: float = 0.08) -> tuple[list[float], float]:
    weights = [0.0] * len(FEATURE_NAMES)
    bias = 0.0
    for _ in range(epochs):
        dw = [0.0] * len(weights)
        db = 0.0
        for sample in samples:
            values = feature_vector(sample["features"])
            error = sigmoid(sum(w * x for w, x in zip(weights, values)) + bias) - sample["outcome"]
            for index, value in enumerate(values):
                dw[index] += error * value
            db += error
        scale = 1.0 / len(samples)
        weights = [w - rate * (g * scale + 0.001 * w) for w, g in zip(weights, dw)]
        bias -= rate * db * scale
    return weights, bias


def evaluate(samples: list[dict], weights: list[float], bias: float) -> dict[str, float]:
    tp = fp = tn = fn = 0
    for sample in samples:
        predicted = sigmoid(sum(w * x for w, x in zip(weights, feature_vector(sample["features"]))) + bias) >= 0.5
        actual = bool(sample["outcome"])
        tp += predicted and actual; fp += predicted and not actual
        tn += not predicted and not actual; fn += not predicted and actual
    total = max(1, len(samples)); precision = tp / max(1, tp + fp); recall = tp / max(1, tp + fn)
    return {"accuracy": (tp + tn) / total, "precision": precision, "recall": recall, "f1": 2 * precision * recall / max(1e-12, precision + recall)}


def train_walk_forward(samples: list[dict]) -> tuple[dict, dict]:
    split = max(1, int(len(samples) * 0.8))
    training, validation = samples[:split], samples[split:] or samples[-1:]
    weights, bias = fit_logistic(training)
    metrics = evaluate(validation, weights, bias)
    return {"feature_names": FEATURE_NAMES, "weights": weights, "bias": bias}, metrics


def thompson_preferences(stats: dict[str, tuple[int, int]], seed: int | None = None) -> dict[str, float]:
    rng = random.Random(seed)
    draws = {name: rng.betavariate(success + 1, failure + 1) for name, (success, failure) in stats.items()}
    total = sum(draws.values()) or 1.0
    return {name: value / total for name, value in draws.items()}

