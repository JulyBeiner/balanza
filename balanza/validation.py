"""The inspection: a fixed list of checks run on a scored dataset.

Balanza does not need the model itself. It needs a table where each row is
a loan application with:
- score:   the model's probability of default (0 to 1)
- default: what really happened (1 = not repaid, 0 = repaid)
and, when available, the decision, the sample and the protected attributes.

Every check returns a status (pass / warn / fail), the number behind it, the
rule that was applied and the article of the EU AI Act it gives evidence for.
The thresholds are common industry conventions, not legal limits. They are
defaults that each lender should review and own.
"""
from __future__ import annotations

import csv
import hashlib
import io

import numpy as np

from . import metrics

RESERVED = {"score", "default", "approved", "sample", "applicant_id"}
KNOWN_PROTECTED = ["gender", "sex", "age_band", "age_group", "nationality", "marital_status", "disability"]
MIN_ROWS = 200
DEFAULT_THRESHOLD = 0.15

ORDER = {"pass": 0, "na": 0, "warn": 1, "fail": 2}


class DatasetError(ValueError):
    """The uploaded file cannot be inspected. The message says why."""


# ---------------------------------------------------------------- reading


def read_csv(text: str) -> dict:
    """Parse CSV text into a table: a dict of column name -> NumPy array."""
    reader = csv.reader(io.StringIO(text))
    try:
        header = [name.strip() for name in next(reader)]
    except StopIteration:
        raise DatasetError("The file is empty.") from None
    rows = [row for row in reader if any(cell.strip() for cell in row)]
    if not rows:
        raise DatasetError("The file has a header but no rows.")
    if any(len(row) != len(header) for row in rows):
        raise DatasetError("Some rows have a different number of columns than the header.")

    table = {}
    for index, name in enumerate(header):
        cells = [row[index].strip() for row in rows]
        try:
            table[name] = np.array([float(c) if c != "" else np.nan for c in cells], dtype=float)
        except ValueError:
            table[name] = np.array(cells, dtype=object)
    return table


def fingerprint(text: str) -> str:
    """A short, unique signature of the file, to prove later what was tested."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _is_number(column: np.ndarray) -> bool:
    return column.dtype.kind in "fiu"


def _missing_share(column: np.ndarray) -> float:
    if _is_number(column):
        return float(np.mean(np.isnan(column.astype(float))))
    return float(np.mean(column == ""))


def protected_columns(table: dict) -> list[str]:
    found = [name for name in KNOWN_PROTECTED if name in table]
    return found


def prepare(table: dict, threshold: float = DEFAULT_THRESHOLD) -> dict:
    """Check that the table has what we need and fill in what can be derived."""
    for required in ("score", "default"):
        if required not in table:
            raise DatasetError(f"Column '{required}' is missing. The file needs at least 'score' and 'default'.")
        if not _is_number(table[required]):
            raise DatasetError(f"Column '{required}' must contain only numbers.")

    table = dict(table)
    keep = ~(np.isnan(table["score"]) | np.isnan(table["default"]))
    dropped = int((~keep).sum())
    if dropped:
        table = {name: column[keep] for name, column in table.items()}
    table["_dropped_rows"] = dropped

    if len(table["score"]) < MIN_ROWS:
        raise DatasetError(f"At least {MIN_ROWS} rows with a score and an outcome are needed to inspect a model.")
    if table["score"].min() < 0 or table["score"].max() > 1:
        raise DatasetError("Column 'score' must be a probability between 0 and 1.")
    if not np.isin(table["default"], [0, 1]).all():
        raise DatasetError("Column 'default' must contain only 0 (repaid) and 1 (not repaid).")
    if table["default"].sum() == 0 or table["default"].sum() == len(table["default"]):
        raise DatasetError("Column 'default' needs both repaid (0) and not repaid (1) loans.")

    table["_derived_decision"] = "approved" not in table
    if "approved" not in table:
        table["approved"] = (table["score"] < threshold).astype(float)
    if "age_band" not in table and "age_group" not in table and "age" in table and _is_number(table["age"]):
        from .synthetic import age_band

        table["age_band"] = age_band(table["age"])
    return table


# ---------------------------------------------------------------- grading


def grade(value: float, pass_at: float, warn_at: float, higher_is_better: bool) -> str:
    if value != value:  # NaN
        return "na"
    if higher_is_better:
        return "pass" if value >= pass_at else "warn" if value >= warn_at else "fail"
    return "pass" if value <= pass_at else "warn" if value <= warn_at else "fail"


def _check(check_id, category, name, value, display, status, rule, meaning, articles) -> dict:
    return {
        "id": check_id,
        "category": category,
        "name": name,
        "value": None if value is None or value != value else round(float(value), 4),
        "display": display,
        "status": status,
        "rule": rule,
        "meaning": meaning,
        "articles": articles,
    }


def _pct(value: float, digits: int = 1) -> str:
    return f"{100 * value:.{digits}f}%"


# ---------------------------------------------------------------- the checks


def run_validation(table: dict, threshold: float = DEFAULT_THRESHOLD) -> dict:
    """Run every check and return the full inspection result."""
    table = prepare(table, threshold)
    n_total = len(table["score"])

    has_samples = "sample" in table and {"development", "validation"} <= set(table["sample"].astype(str).tolist())
    if has_samples:
        sample = table["sample"].astype(str)
        evaluate = sample == "validation"
        reference = sample == "development"
    else:
        evaluate = np.ones(n_total, dtype=bool)
        reference = None

    y = table["default"][evaluate].astype(int)
    score = table["score"][evaluate]
    approved = table["approved"][evaluate].astype(int)
    checks = []

    # ---- data (Art. 10: data and data governance)
    defaults = int(y.sum())
    checks.append(
        _check(
            "data.volume", "data", "Enough cases to measure",
            defaults, f"{len(y):,} loans, {defaults:,} defaults",
            grade(defaults, 100, 30, True),
            "Pass with 100+ defaults, warn with 30+",
            "With few defaults every other number here is unreliable. More outcome data is needed before trusting the results.",
            ["Art. 10"],
        )
    )

    data_columns = [name for name in table if not name.startswith("_")]
    worst_missing = max(_missing_share(table[name]) for name in data_columns)
    worst_missing = max(worst_missing, table["_dropped_rows"] / (n_total + table["_dropped_rows"]))
    checks.append(
        _check(
            "data.missing", "data", "Missing values",
            worst_missing, f"{_pct(worst_missing)} in the worst column",
            grade(worst_missing, 0.01, 0.05, False),
            "Pass up to 1%, warn up to 5%",
            "Empty cells mean the model is deciding with incomplete information. Find out why they are empty and document how they are handled.",
            ["Art. 10"],
        )
    )

    if "applicant_id" in table:
        ids = table["applicant_id"].astype(str)
        duplicates = 1 - len(set(ids.tolist())) / len(ids)
        checks.append(
            _check(
                "data.duplicates", "data", "Duplicated applications",
                duplicates, f"{_pct(duplicates)} of rows",
                grade(duplicates, 0.0, 0.01, False),
                "Pass with none, warn up to 1%",
                "The same application counted twice makes the model look more certain than it is. Remove duplicates before validating.",
                ["Art. 10"],
            )
        )

    groups = protected_columns(table)
    fairness_charts = {}
    if groups:
        smallest_name, smallest_n = None, None
        for attribute in groups:
            values = table[attribute][evaluate].astype(str)
            for name in set(values.tolist()):
                size = int((values == name).sum())
                if smallest_n is None or size < smallest_n:
                    smallest_name, smallest_n = f"{attribute} = {name}", size
        checks.append(
            _check(
                "data.representation", "data", "Every group is represented",
                smallest_n, f"smallest group: {smallest_name} ({smallest_n:,} loans)",
                grade(smallest_n, 200, 50, True),
                "Pass with 200+ loans per group, warn with 50+",
                "The model has been tested on very few people of this group, so its behaviour for them is not proven. Collect more cases or flag it as a known limitation.",
                ["Art. 10"],
            )
        )

    # ---- performance (Art. 15: accuracy)
    auc = metrics.auc(y, score)
    auc_se = metrics.auc_standard_error(auc, int(y.sum()), int((1 - y).sum()))
    checks.append(
        _check(
            "performance.auc", "performance", "Tells good and bad payers apart (AUC)",
            auc, f"AUC {auc:.3f}, Gini {2 * auc - 1:.3f}",
            grade(auc, 0.70, 0.60, True),
            "Pass from 0.70, warn from 0.60",
            "AUC is the chance that the model ranks a defaulter as riskier than a repayer. 0.5 is a coin flip.",
            ["Art. 15"],
        )
    )
    ks = metrics.ks(y, score)
    checks.append(
        _check(
            "performance.ks", "performance", "Separation between payers (KS)",
            ks, f"KS {ks:.3f}",
            grade(ks, 0.30, 0.20, True),
            "Pass from 0.30, warn from 0.20",
            "KS is the widest gap between the scores of defaulters and repayers. A small gap means the scores overlap too much to decide with.",
            ["Art. 15"],
        )
    )

    # ---- calibration (Art. 15: accuracy)
    predicted_rate = float(score.mean())
    observed_rate = float(y.mean())
    level_gap = abs(predicted_rate - observed_rate) / observed_rate
    checks.append(
        _check(
            "calibration.level", "calibration", "Predicts the right number of defaults",
            level_gap, f"predicted {_pct(predicted_rate)} vs real {_pct(observed_rate)}",
            grade(level_gap, 0.10, 0.25, False),
            "Pass within 10% of the real rate, warn within 25%",
            "If the model expects fewer defaults than really happen, the lender is taking more risk than it thinks (and the other way round).",
            ["Art. 15"],
        )
    )
    ece = metrics.expected_calibration_error(y, score)
    checks.append(
        _check(
            "calibration.ece", "calibration", "Probabilities can be trusted at every risk level",
            ece, f"average gap {_pct(ece)}",
            grade(ece, 0.02, 0.05, False),
            "Pass up to 2 points, warn up to 5",
            "Loans are split in ten groups from safest to riskiest. This is the average distance between predicted and real defaults in those groups.",
            ["Art. 15"],
        )
    )

    # ---- stability (Art. 15: robustness)
    profile = None
    if reference is not None:
        profile = metrics.reference_profile(table["score"][reference])
        score_psi = metrics.psi_against(profile, score)
        checks.append(
            _check(
                "stability.score", "stability", "Scores behave the same on unseen loans (PSI)",
                score_psi, f"PSI {score_psi:.3f}",
                grade(score_psi, 0.10, 0.25, False),
                "Pass under 0.10, warn under 0.25",
                "Compares the scores on the loans used to build the model with the loans kept aside. A big difference means the model learned its training data by heart.",
                ["Art. 15"],
            )
        )
        features = [
            name for name in data_columns
            if name not in RESERVED and name != "age" and _is_number(table[name]) and not np.isnan(table[name]).any()
        ]
        if features:
            feature_psi = {name: metrics.psi(table[name][reference], table[name][evaluate]) for name in features}
            worst = max(feature_psi, key=feature_psi.get)
            checks.append(
                _check(
                    "stability.inputs", "stability", "Inputs look the same in both samples",
                    feature_psi[worst], f"largest shift: {worst} (PSI {feature_psi[worst]:.3f})",
                    grade(feature_psi[worst], 0.10, 0.25, False),
                    "Pass under 0.10, warn under 0.25",
                    "If an input is distributed differently in the test loans, the test is not a fair picture of what the model will see.",
                    ["Art. 10", "Art. 15"],
                )
            )
        y_reference = table["default"][reference].astype(int)
        auc_reference = metrics.auc(y_reference, table["score"][reference])
        noise = float(np.hypot(auc_se, metrics.auc_standard_error(auc_reference, int(y_reference.sum()), int((1 - y_reference).sum()))))
        overfit = metrics.beyond_chance(auc_reference - auc, noise)
        checks.append(
            _check(
                "stability.overfit", "stability", "No loss of accuracy on unseen loans",
                overfit, f"AUC {auc_reference:.3f} when built, {auc:.3f} on unseen loans",
                grade(overfit, 0.03, 0.06, False),
                "Pass up to 0.03 lower beyond chance, warn up to 0.06",
                "A model that is much better on the loans it was built with than on new ones will disappoint in production.",
                ["Art. 15"],
            )
        )
    else:
        profile = metrics.reference_profile(score)
        checks.append(
            _check(
                "stability.score", "stability", "Scores behave the same on unseen loans (PSI)",
                None, "not measured",
                "na",
                "Needs a 'sample' column with 'development' and 'validation' rows",
                "Without knowing which loans built the model and which were kept aside, stability cannot be measured.",
                ["Art. 15"],
            )
        )

    # ---- fairness (Art. 10: examination of possible biases; Art. 9: risks to fundamental rights)
    for attribute in groups:
        rows = metrics.group_table(table[attribute][evaluate], y, score, approved)
        fairness_charts[attribute] = rows
        label = attribute.replace("_", " ")

        rates = [row["approval_rate"] for row in rows]
        best = max(rows, key=lambda row: row["approval_rate"])
        worst = min(rows, key=lambda row: row["approval_rate"])
        ratio = min(rates) / max(rates) if max(rates) > 0 else float("nan")
        checks.append(
            _check(
                f"fairness.{attribute}.approval", "fairness", f"Similar approval rates by {label}",
                ratio,
                f"{worst['group']} approved {_pct(worst['approval_rate'])} vs {best['group']} {_pct(best['approval_rate'])} (ratio {ratio:.2f})",
                grade(ratio, 0.90, 0.80, True),
                "Pass from 0.90, warn from 0.80 (four-fifths rule of thumb)",
                "Lowest approval rate divided by the highest. A low ratio is not proof of discrimination, but it must be explained and justified.",
                ["Art. 10", "Art. 9"],
            )
        )

        good_rates = [(row["group"], row["good_approval_rate"]) for row in rows if row["good_approval_rate"] is not None]
        if len(good_rates) >= 2:
            high = max(good_rates, key=lambda item: item[1])
            low = min(good_rates, key=lambda item: item[1])
            gap = high[1] - low[1]
            checks.append(
                _check(
                    f"fairness.{attribute}.opportunity", "fairness", f"Good payers get the same chance by {label}",
                    gap,
                    f"good payers approved: {low[0]} {_pct(low[1])} vs {high[0]} {_pct(high[1])} (gap {100 * gap:.1f} pts)",
                    grade(gap, 0.05, 0.10, False),
                    "Pass up to 5 points, warn up to 10",
                    "Looks only at people who did repay. If one group of good payers is rejected much more often, the model is costing them loans they deserved.",
                    ["Art. 10", "Art. 9"],
                )
            )

        measured = [row for row in rows if row["auc"] is not None and row["n"] >= 100]
        if len(measured) >= 2:
            high = max(measured, key=lambda row: row["auc"])
            low = min(measured, key=lambda row: row["auc"])
            gap = high["auc"] - low["auc"]
            noise = float(np.hypot(*(metrics.auc_standard_error(r["auc"], r["defaults"], r["n"] - r["defaults"]) for r in (high, low))))
            clear_gap = metrics.beyond_chance(gap, noise)
            checks.append(
                _check(
                    f"fairness.{attribute}.accuracy", "fairness", f"Equally accurate by {label}",
                    clear_gap,
                    f"AUC {low['group']} {low['auc']:.3f} vs {high['group']} {high['auc']:.3f}"
                    + (f" (gap {gap:.3f}, {clear_gap:.3f} beyond chance)" if clear_gap > 0 else f" (gap {gap:.3f}, within chance for these group sizes)"),
                    grade(clear_gap, 0.05, 0.10, False),
                    "Pass up to 0.05 beyond chance, warn up to 0.10 (groups with 100+ loans)",
                    "A model that is less accurate for one group makes more mistakes with those people, in both directions.",
                    ["Art. 10", "Art. 15"],
                )
            )

    overall = max((c["status"] for c in checks), key=lambda status: ORDER[status])
    if overall == "na":
        overall = "pass"
    counts = {status: sum(1 for c in checks if c["status"] == status) for status in ("pass", "warn", "fail", "na")}

    return {
        "overall": overall,
        "counts": counts,
        "n_rows": int(n_total),
        "n_evaluated": int(len(y)),
        "default_rate": round(observed_rate, 4),
        "approval_rate": round(float(approved.mean()), 4),
        "auc": round(float(auc), 6),
        "auc_se": round(float(auc_se), 4),
        "threshold": threshold,
        "derived_decision": bool(table["_derived_decision"]),
        "has_samples": bool(has_samples),
        "protected_attributes": groups,
        "checks": checks,
        "reference_profile": profile,
        "charts": {
            "roc": metrics.roc_points(y, score),
            "calibration": metrics.calibration_table(y, score),
            "scores": metrics.score_histogram(y, score),
            "fairness": fairness_charts,
        },
    }


# ---------------------------------------------------------------- monitoring


def run_monitoring(
    table: dict, profile: dict, baseline_auc: float, baseline_se: float = 0.0, threshold: float = DEFAULT_THRESHOLD
) -> dict:
    """Compare one period of production loans with the validated model.

    One month has few loans, so numbers move by chance. Accuracy and
    calibration only raise an alarm for the part of the change that chance
    does not explain (95% confidence).
    """
    table = prepare(table, threshold)
    y = table["default"].astype(int)
    score = table["score"]
    approved = table["approved"].astype(int)

    drift = metrics.psi_against(profile, score)
    auc = metrics.auc(y, score)
    auc_drop = baseline_auc - auc
    auc_noise = float(np.hypot(metrics.auc_standard_error(auc, int(y.sum()), int((1 - y).sum())), baseline_se))
    clear_drop = metrics.beyond_chance(auc_drop, auc_noise)
    predicted = float(score.mean())
    observed = float(y.mean())
    rate_noise = float(np.sqrt(predicted * (1 - predicted) / len(y)))
    level_gap = metrics.beyond_chance(abs(predicted - observed), rate_noise) / observed

    signals = [
        {
            "id": "drift",
            "name": "Applicants have changed (PSI)",
            "display": f"PSI {drift:.3f}",
            "status": grade(drift, 0.10, 0.25, False),
            "rule": "Pass under 0.10, warn under 0.25",
        },
        {
            "id": "accuracy",
            "name": "Accuracy against validation",
            "display": f"AUC {auc:.3f} ({-auc_drop:+.3f} vs validation)",
            "status": grade(clear_drop, 0.03, 0.06, False),
            "rule": "Pass up to 0.03 lower beyond chance, warn up to 0.06",
        },
        {
            "id": "calibration",
            "name": "Predicted vs real defaults",
            "display": f"predicted {_pct(predicted)} vs real {_pct(observed)}",
            "status": grade(level_gap, 0.10, 0.25, False),
            "rule": "Pass within 10% of the real rate beyond chance, warn within 25%",
        },
    ]
    overall = max((s["status"] for s in signals), key=lambda status: ORDER[status])
    return {
        "overall": overall,
        "n_rows": int(len(y)),
        "psi": round(drift, 4),
        "auc": round(float(auc), 6),
        "auc_noise": round(metrics.Z95 * auc_noise, 4),
        "default_rate": round(observed, 4),
        "predicted_rate": round(predicted, 4),
        "approval_rate": round(float(approved.mean()), 4),
        "signals": signals,
    }
