"""The measurements, checked against numbers worked out by hand."""
import math

import numpy as np
import pytest

from balanza import metrics


def test_auc_small_example():
    # 4 loans. Pairs (defaulter, repayer): 0.35>0.1 yes, 0.35>0.4 no, 0.8>0.1 yes, 0.8>0.4 yes -> 3 of 4.
    y = np.array([0, 0, 1, 1])
    score = np.array([0.1, 0.4, 0.35, 0.8])
    assert metrics.auc(y, score) == pytest.approx(0.75)
    assert metrics.gini(y, score) == pytest.approx(0.5)


def test_auc_extremes_and_ties():
    y = np.array([0, 0, 1, 1])
    assert metrics.auc(y, np.array([0.1, 0.2, 0.8, 0.9])) == pytest.approx(1.0)
    assert metrics.auc(y, np.array([0.9, 0.8, 0.2, 0.1])) == pytest.approx(0.0)
    assert metrics.auc(y, np.array([0.5, 0.5, 0.5, 0.5])) == pytest.approx(0.5)  # ties count half


def test_auc_needs_both_outcomes():
    assert math.isnan(metrics.auc(np.array([0, 0, 0]), np.array([0.1, 0.2, 0.3])))


def test_ks_small_example():
    # Sorted by score: 0.1(repaid) 0.35(default) 0.4(repaid) 0.8(default)
    # share of defaulters seen: 0, .5, .5, 1 · share of repayers seen: .5, .5, 1, 1 -> widest gap .5
    y = np.array([0, 0, 1, 1])
    score = np.array([0.1, 0.4, 0.35, 0.8])
    assert metrics.ks(y, score) == pytest.approx(0.5)
    assert metrics.ks(y, np.array([0.1, 0.2, 0.8, 0.9])) == pytest.approx(1.0)


def test_brier():
    # (0.8-1)^2 = 0.04 and (0.3-0)^2 = 0.09 -> average 0.065
    assert metrics.brier(np.array([1, 0]), np.array([0.8, 0.3])) == pytest.approx(0.065)


def test_calibration_table_and_ece():
    y = np.array([0, 0, 0, 1])
    score = np.array([0.1, 0.1, 0.5, 0.5])
    table = metrics.calibration_table(y, score, bins=2)
    assert table == [
        {"bin": 1, "n": 2, "predicted": 0.1, "observed": 0.0},
        {"bin": 2, "n": 2, "predicted": 0.5, "observed": 0.5},
    ]
    # gaps: 0.1 and 0.0, same size groups -> 0.05
    assert metrics.expected_calibration_error(y, score, bins=2) == pytest.approx(0.05)


def test_psi_is_zero_for_the_same_data():
    data = np.random.default_rng(1).random(1000)
    assert metrics.psi(data, data) == pytest.approx(0.0, abs=1e-12)


def test_psi_hand_example():
    # Reference: half the loans below 0.5, half above. Now: 80% below, 20% above.
    profile = {"edges": [0.5], "shares": [0.5, 0.5]}
    actual = np.array([0.2] * 8 + [0.9] * 2)
    expected = (0.8 - 0.5) * math.log(0.8 / 0.5) + (0.2 - 0.5) * math.log(0.2 / 0.5)
    assert metrics.psi_against(profile, actual) == pytest.approx(expected)
    assert expected == pytest.approx(0.4159, abs=1e-4)


def test_psi_grows_when_the_population_moves():
    rng = np.random.default_rng(2)
    reference = rng.normal(0, 1, 5000)
    small = metrics.psi(reference, rng.normal(0.1, 1, 5000))
    large = metrics.psi(reference, rng.normal(1.0, 1, 5000))
    assert small < 0.10 < 0.25 < large


def test_group_table():
    group = np.array(["A", "A", "A", "A", "B", "B", "B", "B"])
    y = np.array([0, 0, 0, 1, 0, 0, 1, 1])
    score = np.array([0.1, 0.1, 0.3, 0.6, 0.1, 0.4, 0.5, 0.7])
    approved = np.array([1, 1, 1, 0, 1, 0, 0, 0])
    a, b = metrics.group_table(group, y, score, approved)
    assert a == {"group": "A", "n": 4, "approval_rate": 0.75, "good_approval_rate": 1.0, "default_rate": 0.25, "defaults": 1, "auc": 1.0}
    assert b == {"group": "B", "n": 4, "approval_rate": 0.25, "good_approval_rate": 0.5, "default_rate": 0.5, "defaults": 2, "auc": 1.0}


def test_roc_points_start_and_end():
    y = np.array([0, 0, 1, 1])
    points = metrics.roc_points(y, np.array([0.1, 0.4, 0.35, 0.8]))
    assert points[0] == [0.0, 0.0]
    assert points[-1] == [1.0, 1.0]


def test_auc_standard_error_hand_example():
    # AUC 0.75 with 170 defaults and 1,330 repaid loans (a typical month).
    a, bad, good = 0.75, 170, 1330
    q1, q2 = a / (2 - a), 2 * a * a / (1 + a)
    expected = math.sqrt((a * (1 - a) + (bad - 1) * (q1 - a * a) + (good - 1) * (q2 - a * a)) / (bad * good))
    assert metrics.auc_standard_error(a, bad, good) == pytest.approx(expected)
    assert expected == pytest.approx(0.0224, abs=5e-4)
    # more loans -> less noise
    assert metrics.auc_standard_error(a, 1700, 13300) < expected / 3


def test_auc_standard_error_matches_simulation():
    # Draw many samples from the same population and compare the spread.
    rng = np.random.default_rng(5)
    values = []
    for _ in range(300):
        y = (rng.random(800) < 0.15).astype(int)
        score = rng.normal(0, 1, 800) + 0.9 * y
        values.append(metrics.auc(y, score))
    formula = metrics.auc_standard_error(float(np.mean(values)), 120, 680)
    assert np.std(values) == pytest.approx(formula, rel=0.2)


def test_beyond_chance():
    assert metrics.beyond_chance(0.02, 0.02) == 0.0           # inside the noise
    assert metrics.beyond_chance(0.10, 0.02) == pytest.approx(0.10 - 1.645 * 0.02)
