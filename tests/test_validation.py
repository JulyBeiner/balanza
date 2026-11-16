"""The inspection as a whole, on the invented demo data."""
import numpy as np
import pytest

from balanza.demo_model import build_demo, score_table
from balanza.synthetic import generate, to_csv
from balanza.validation import DatasetError, fingerprint, grade, read_csv, run_monitoring, run_validation


@pytest.fixture(scope="module")
def demo():
    model, scored = build_demo()
    return model, scored, run_validation(read_csv(to_csv(scored)))


def by_id(result):
    return {check["id"]: check for check in result["checks"]}


def test_grade():
    assert grade(0.75, 0.70, 0.60, True) == "pass"
    assert grade(0.65, 0.70, 0.60, True) == "warn"
    assert grade(0.55, 0.70, 0.60, True) == "fail"
    assert grade(0.05, 0.10, 0.25, False) == "pass"
    assert grade(0.20, 0.10, 0.25, False) == "warn"
    assert grade(0.30, 0.10, 0.25, False) == "fail"
    assert grade(float("nan"), 0.10, 0.25, False) == "na"


def test_demo_model_is_accurate_and_stable(demo):
    _, _, result = demo
    checks = by_id(result)
    assert result["n_rows"] == 6000
    assert 0.74 < result["auc"] < 0.80
    for check_id in ("performance.auc", "performance.ks", "calibration.level", "calibration.ece", "stability.score", "stability.overfit"):
        assert checks[check_id]["status"] == "pass", check_id


def test_demo_model_bias_is_found(demo):
    # The invented data makes young applicants look riskier through income and
    # job tenure. Balanza must notice, even though the model never sees age.
    _, _, result = demo
    checks = by_id(result)
    assert checks["fairness.age_band.approval"]["status"] == "fail"
    assert checks["fairness.age_band.opportunity"]["status"] == "fail"
    assert checks["fairness.gender.approval"]["status"] == "pass"
    assert result["overall"] == "fail"
    assert result["protected_attributes"] == ["gender", "age_band"]


def test_every_check_explains_itself(demo):
    _, _, result = demo
    for check in result["checks"]:
        assert check["status"] in ("pass", "warn", "fail", "na")
        assert check["meaning"] and check["rule"] and check["articles"]
    assert sum(result["counts"].values()) == len(result["checks"])


def test_same_file_same_fingerprint(demo):
    _, scored, _ = demo
    text = to_csv(scored)
    assert fingerprint(text) == fingerprint(to_csv(scored))
    assert fingerprint(text) != fingerprint(text + "\n")


def test_minimal_file_only_needs_score_and_default(demo):
    _, scored, _ = demo
    minimal = {"score": scored["score"], "default": scored["default"]}
    result = run_validation(read_csv(to_csv(minimal)))
    checks = by_id(result)
    assert result["derived_decision"] is True
    assert result["protected_attributes"] == []
    assert checks["stability.score"]["status"] == "na"
    assert checks["performance.auc"]["status"] == "pass"


def test_age_band_is_derived_from_age(demo):
    _, scored, _ = demo
    table = {name: scored[name] for name in ("score", "default", "approved", "age")}
    result = run_validation(read_csv(to_csv(table)))
    assert result["protected_attributes"] == ["age_band"]


def test_missing_values_are_reported(demo):
    _, scored, _ = demo
    text = to_csv({name: scored[name] for name in ("score", "default", "income")})
    lines = text.split("\n")
    for index in range(1, 601):  # blank the income of 600 of 6,000 rows -> 10%
        score, default, _ = lines[index].split(",")
        lines[index] = f"{score},{default},"
    result = run_validation(read_csv("\n".join(lines)))
    check = by_id(result)["data.missing"]
    assert check["status"] == "fail"
    assert check["value"] == pytest.approx(0.10)


@pytest.mark.parametrize(
    "text, message",
    [
        ("", "empty"),
        ("score,default\n", "no rows"),
        ("score,outcome\n0.1,0\n", "'default' is missing"),
        ("score,default\n0.1,0\n0.2,1\n", "At least 200 rows"),
        ("score,default\n" + "1.5,0\n" * 150 + "0.2,1\n" * 150, "between 0 and 1"),
        ("score,default\n" + "0.5,0\n" * 150 + "0.2,2\n" * 150, "only 0 (repaid) and 1"),
        ("score,default\n" + "0.5,0\n" * 300, "both repaid"),
        ("score,default\n0.1,0,extra\n", "different number of columns"),
    ],
)
def test_bad_files_are_refused_with_a_clear_message(text, message):
    with pytest.raises(DatasetError, match=message.replace("(", r"\(").replace(")", r"\)")):
        run_validation(read_csv(text))


def test_monitoring_is_quiet_when_nothing_changes(demo):
    model, _, result = demo
    # One ordinary month. (By design about 1 quiet month in 100 can still show a
    # warning; test_monitoring_rarely_cries_wolf checks that rate.)
    batch = score_table(model, generate(n=1500, seed=310))
    record = run_monitoring(batch, result["reference_profile"], result["auc"], result["auc_se"])
    assert record["overall"] == "pass"
    assert record["psi"] < 0.10


def test_monitoring_alerts_when_applicants_change(demo):
    model, _, result = demo
    batch = score_table(model, generate(n=1500, seed=301, drift=1.25, concept=0.4))
    record = run_monitoring(batch, result["reference_profile"], result["auc"], result["auc_se"])
    signals = {signal["id"]: signal["status"] for signal in record["signals"]}
    assert record["overall"] == "fail"
    assert signals["drift"] == "fail"
    assert record["default_rate"] > record["predicted_rate"]


def test_synthetic_data_is_reproducible():
    first, second = generate(n=500, seed=3), generate(n=500, seed=3)
    assert all(np.array_equal(first[name], second[name]) for name in first)


def test_monitoring_rarely_cries_wolf(demo):
    # 60 months where nothing changed. A rule that ignored chance flagged
    # about 1 month in 5 here; a monitoring tool that does that gets ignored.
    model, _, result = demo
    alarms = 0
    for seed in range(400, 460):
        batch = score_table(model, generate(n=1500, seed=seed))
        record = run_monitoring(batch, result["reference_profile"], result["auc"], result["auc_se"])
        alarms += record["overall"] != "pass"
    assert alarms <= 2


def test_what_if_agrees_with_the_checks_at_the_cut_off_in_use():
    """Moving the cut-off is plain arithmetic with the same rules as the checks."""
    from balanza import seed
    from balanza.validation import read_csv

    result = run_validation(read_csv(seed.demo_dataset_csv()))
    rows = result["what_if"]
    assert [row["cut_off"] for row in rows] == [step / 100 for step in range(1, 51)]
    now = next(row for row in rows if row["cut_off"] == result["threshold"])
    assert now["approval_rate"] == result["approval_rate"]  # the demo approves exactly below 15%
    checks = {c["name"]: c for c in result["checks"]}
    assert len(now["bias"]) == 4
    for measure in now["bias"]:
        assert measure["status"] == checks[measure["name"]]["status"]
    assert "ratio 0.73" in now["bias"][2]["display"] and "gap 22.7 pts" in now["bias"][3]["display"]
    approvals = [row["approval_rate"] for row in rows]
    assert approvals == sorted(approvals)  # a higher cut-off never approves fewer loans
    assert all(0 <= row["good_rejected"] <= 1 for row in rows)
