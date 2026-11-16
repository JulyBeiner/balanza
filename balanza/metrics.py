"""The measurements Balanza takes on a model. NumPy only, no black boxes.

Conventions used everywhere:
- y:      1 = the loan was NOT repaid (default), 0 = it was repaid.
- score:  the model's probability of default (0 to 1). Higher = riskier.
"""
from __future__ import annotations

import numpy as np


def _average_ranks(values: np.ndarray) -> np.ndarray:
    """Rank from 1..n, giving tied values the average of their ranks."""
    order = np.argsort(values, kind="mergesort")
    sorted_values = values[order]
    ranks = np.empty(len(values), dtype=float)
    # start index of each run of equal values
    starts = np.flatnonzero(np.r_[True, sorted_values[1:] != sorted_values[:-1]])
    ends = np.r_[starts[1:], len(values)]
    for start, end in zip(starts, ends):
        ranks[order[start:end]] = (start + end + 1) / 2.0
    return ranks


def auc(y: np.ndarray, score: np.ndarray) -> float:
    """Chance that a random defaulter gets a higher score than a random repayer.

    0.5 = the model is guessing. 1.0 = it separates them perfectly.
    """
    y = np.asarray(y).astype(int)
    score = np.asarray(score, dtype=float)
    bad = int(y.sum())
    good = len(y) - bad
    if bad == 0 or good == 0:
        return float("nan")
    ranks = _average_ranks(score)
    return float((ranks[y == 1].sum() - bad * (bad + 1) / 2.0) / (bad * good))


Z95 = 1.645  # one-sided 95% confidence


def auc_standard_error(auc_value: float, n_bad: int, n_good: int) -> float:
    """How much an AUC moves by pure chance with this many loans.

    Hanley & McNeil (1982). With few defaults the AUC is a noisy number, and
    Balanza must not raise an alarm for noise.
    """
    if n_bad < 1 or n_good < 1 or auc_value != auc_value:
        return float("nan")
    a = auc_value
    q1 = a / (2 - a)
    q2 = 2 * a * a / (1 + a)
    variance = (a * (1 - a) + (n_bad - 1) * (q1 - a * a) + (n_good - 1) * (q2 - a * a)) / (n_bad * n_good)
    return float(np.sqrt(max(variance, 0.0)))


def beyond_chance(gap: float, standard_error: float) -> float:
    """The part of a gap that chance alone does not explain (95% confidence)."""
    if standard_error != standard_error:
        return gap
    return max(0.0, gap - Z95 * standard_error)


def gini(y: np.ndarray, score: np.ndarray) -> float:
    """The same information as AUC, on the scale banks usually report."""
    return 2.0 * auc(y, score) - 1.0


def ks(y: np.ndarray, score: np.ndarray) -> float:
    """Biggest gap between the score curves of defaulters and repayers."""
    y = np.asarray(y).astype(int)
    score = np.asarray(score, dtype=float)
    bad = int(y.sum())
    good = len(y) - bad
    if bad == 0 or good == 0:
        return float("nan")
    order = np.argsort(score, kind="mergesort")
    y_sorted = y[order]
    s_sorted = score[order]
    cum_bad = np.cumsum(y_sorted) / bad
    cum_good = np.cumsum(1 - y_sorted) / good
    # only compare at the last row of each distinct score
    last = np.r_[s_sorted[1:] != s_sorted[:-1], True]
    return float(np.max(np.abs(cum_bad[last] - cum_good[last])))


def roc_points(y: np.ndarray, score: np.ndarray, points: int = 60) -> list[list[float]]:
    """A light version of the ROC curve, for drawing."""
    y = np.asarray(y).astype(int)
    score = np.asarray(score, dtype=float)
    bad = max(int(y.sum()), 1)
    good = max(len(y) - int(y.sum()), 1)
    order = np.argsort(-score, kind="mergesort")
    tpr = np.r_[0.0, np.cumsum(y[order]) / bad]
    fpr = np.r_[0.0, np.cumsum(1 - y[order]) / good]
    pick = np.unique(np.linspace(0, len(tpr) - 1, points).astype(int))
    return [[round(float(fpr[i]), 4), round(float(tpr[i]), 4)] for i in pick]


def brier(y: np.ndarray, score: np.ndarray) -> float:
    """Average squared distance between the PD and what really happened."""
    y = np.asarray(y, dtype=float)
    score = np.asarray(score, dtype=float)
    return float(np.mean((score - y) ** 2))


def calibration_table(y: np.ndarray, score: np.ndarray, bins: int = 10) -> list[dict]:
    """Split loans into equal groups by score; compare predicted vs real defaults."""
    y = np.asarray(y, dtype=float)
    score = np.asarray(score, dtype=float)
    order = np.argsort(score, kind="mergesort")
    rows = []
    for index, chunk in enumerate(np.array_split(order, bins)):
        if len(chunk) == 0:
            continue
        rows.append(
            {
                "bin": index + 1,
                "n": int(len(chunk)),
                "predicted": round(float(score[chunk].mean()), 4),
                "observed": round(float(y[chunk].mean()), 4),
            }
        )
    return rows


def expected_calibration_error(y: np.ndarray, score: np.ndarray, bins: int = 10) -> float:
    """Average gap between predicted and real default rate, weighted by group size."""
    table = calibration_table(y, score, bins)
    total = sum(row["n"] for row in table)
    return float(sum(row["n"] * abs(row["predicted"] - row["observed"]) for row in table) / total)


def reference_profile(expected: np.ndarray, bins: int = 10) -> dict:
    """Remember the shape of a distribution: bin borders and share per bin.

    Saved when a model is validated, so later data can be compared with it
    without keeping the original rows.
    """
    expected = np.asarray(expected, dtype=float)
    inner = np.unique(np.quantile(expected, np.linspace(0, 1, bins + 1))[1:-1])
    counts = np.bincount(np.searchsorted(inner, expected, side="right"), minlength=len(inner) + 1)
    return {
        "edges": [float(e) for e in inner],
        "shares": [float(c) for c in counts / max(len(expected), 1)],
    }


def psi_against(profile: dict, actual: np.ndarray) -> float:
    """PSI of new data against a saved reference profile."""
    actual = np.asarray(actual, dtype=float)
    inner = np.asarray(profile["edges"], dtype=float)
    counts = np.bincount(np.searchsorted(inner, actual, side="right"), minlength=len(inner) + 1)
    floor = 1e-4  # avoids dividing by zero when a bin is empty
    e_share = np.maximum(np.asarray(profile["shares"], dtype=float), floor)
    a_share = np.maximum(counts / max(len(actual), 1), floor)
    return float(np.sum((a_share - e_share) * np.log(a_share / e_share)))


def psi(expected: np.ndarray, actual: np.ndarray, bins: int = 10) -> float:
    """Population Stability Index: how much a distribution has moved.

    `expected` is the reference (when the model was built), `actual` is now.
    0 = identical. Rule of thumb: under 0.10 stable, over 0.25 a real shift.
    """
    return psi_against(reference_profile(expected, bins), actual)


def score_histogram(y: np.ndarray, score: np.ndarray, bins: int = 20) -> dict:
    """Share of repayers and defaulters in each score range, for drawing."""
    y = np.asarray(y).astype(int)
    score = np.asarray(score, dtype=float)
    top = float(min(1.0, max(0.05, np.quantile(score, 0.995))))
    edges = np.linspace(0.0, top, bins + 1)
    clipped = np.minimum(score, top)
    good = np.histogram(clipped[y == 0], bins=edges)[0] / max(int((y == 0).sum()), 1)
    bad = np.histogram(clipped[y == 1], bins=edges)[0] / max(int((y == 1).sum()), 1)
    return {
        "edges": [round(float(e), 4) for e in edges],
        "repaid": [round(float(v), 4) for v in good],
        "default": [round(float(v), 4) for v in bad],
    }


def group_table(group: np.ndarray, y: np.ndarray, score: np.ndarray, approved: np.ndarray) -> list[dict]:
    """How the model treats each group of people."""
    group = np.asarray(group).astype(str)
    y = np.asarray(y).astype(int)
    score = np.asarray(score, dtype=float)
    approved = np.asarray(approved).astype(int)
    rows = []
    for name in sorted(set(group.tolist())):
        mask = group == name
        repayers = mask & (y == 0)
        rows.append(
            {
                "group": name,
                "n": int(mask.sum()),
                # share of this group that gets the loan
                "approval_rate": round(float(approved[mask].mean()), 4),
                # among people who WOULD repay, share that gets the loan
                "good_approval_rate": round(float(approved[repayers].mean()), 4) if repayers.any() else None,
                "default_rate": round(float(y[mask].mean()), 4),
                "defaults": int(y[mask].sum()),
                "auc": _round_or_none(auc(y[mask], score[mask])),
            }
        )
    return rows


def _round_or_none(value: float, digits: int = 4):
    return None if value != value else round(float(value), digits)  # NaN check
