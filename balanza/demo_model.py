"""The demo credit risk model: a logistic regression written with NumPy only.

It estimates the probability that a loan will not be repaid (PD, "probability
of default"). It is deliberately simple: Balanza is not about this model, it
is about checking ANY model. This one gives us something to check.
"""
from __future__ import annotations

import numpy as np

from .synthetic import FEATURES, generate

APPROVAL_THRESHOLD = 0.15  # approve the loan when PD is below 15%


def design_matrix(table: dict) -> np.ndarray:
    """Turn the raw columns into the numbers the model learns from."""
    columns = []
    for name in FEATURES:
        values = np.asarray(table[name], dtype=float)
        if name in ("income", "loan_amount"):
            values = np.log(np.maximum(values, 1.0))  # money is easier to learn in log scale
        columns.append(values)
    return np.column_stack(columns)


class CreditScorecard:
    """Logistic regression fitted with Newton's method (IRLS)."""

    def __init__(self, ridge: float = 1e-3):
        self.ridge = ridge
        self.mean = None
        self.scale = None
        self.weights = None

    def _prepare(self, x: np.ndarray) -> np.ndarray:
        standardized = (x - self.mean) / self.scale
        return np.column_stack([np.ones(len(standardized)), standardized])

    def fit(self, x: np.ndarray, y: np.ndarray, iterations: int = 25) -> "CreditScorecard":
        self.mean = x.mean(axis=0)
        self.scale = x.std(axis=0)
        self.scale[self.scale == 0] = 1.0
        a = self._prepare(x)
        w = np.zeros(a.shape[1])
        penalty = self.ridge * np.eye(a.shape[1])
        penalty[0, 0] = 0.0  # do not shrink the intercept
        for _ in range(iterations):
            p = 1.0 / (1.0 + np.exp(-(a @ w)))
            gradient = a.T @ (p - y) + penalty @ w
            hessian = (a * (p * (1 - p))[:, None]).T @ a + penalty
            step = np.linalg.solve(hessian, gradient)
            w = w - step
            if np.max(np.abs(step)) < 1e-8:
                break
        self.weights = w
        return self

    def predict(self, x: np.ndarray) -> np.ndarray:
        return 1.0 / (1.0 + np.exp(-(self._prepare(x) @ self.weights)))

    def drivers(self) -> list[dict]:
        """How strongly each input pushes the PD up (+) or down (-)."""
        pairs = zip(FEATURES, self.weights[1:])
        ranked = sorted(pairs, key=lambda item: -abs(item[1]))
        return [{"feature": name, "weight": round(float(weight), 3)} for name, weight in ranked]


def build_demo(seed: int = 7, n: int = 6000) -> tuple[CreditScorecard, dict]:
    """Train the demo model and return it with a fully scored dataset.

    70% of the rows are used to build the model ("development"),
    30% are kept aside to test it honestly ("validation").
    """
    table = generate(n=n, seed=seed)
    rng = np.random.default_rng(seed + 1000)
    is_development = rng.random(n) < 0.70

    x = design_matrix(table)
    y = table["default"].astype(float)
    model = CreditScorecard().fit(x[is_development], y[is_development])

    return model, score_table(model, table, is_development)


def score_table(model: CreditScorecard, table: dict, is_development: np.ndarray | None = None) -> dict:
    """Add the model's score and decision to a table of applications."""
    scored = dict(table)
    score = model.predict(design_matrix(table))
    scored["score"] = score.round(5)
    scored["approved"] = (score < APPROVAL_THRESHOLD).astype(int)
    if is_development is not None:
        scored["sample"] = np.where(is_development, "development", "validation").astype(object)
    return scored
