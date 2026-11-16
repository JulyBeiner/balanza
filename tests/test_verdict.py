"""The verdict: one page for the person who decides."""
import pytest

from balanza import aiact, seed, verdict
from balanza.validation import read_csv, run_validation

ALARM = {
    "period": "2026-10", "overall": "fail",
    "signals": [
        {"display": "PSI 0.289", "status": "fail"},
        {"display": "AUC 0.695 (-0.073 vs validation)", "status": "warn"},
        {"display": "predicted 15.8% vs real 27.1%", "status": "fail"},
    ],
}
QUIET = {**ALARM, "overall": "pass", "signals": [{"display": "PSI 0.010", "status": "pass"}]}
EVERY_ANSWER = {field: "Written by the lender, reviewed and signed by the head of model risk." for field in aiact.DOC_FIELDS}


@pytest.fixture(scope="module")
def validation():
    result = run_validation(read_csv(seed.demo_dataset_csv()))
    return {**result, "dataset_name": seed.DEMO_DATASET_NAME, "dataset_sha256": "ab" * 32, "created_at": "2026-11-16T07:31:09Z"}


def model(risk_class="high", **docs):
    use = next(u for u in aiact.USE_CASES.values() if u["risk_class"] == risk_class)
    return {"name": "Demo", "owner": "Model Risk", "risk_class": risk_class, "risk_basis": use["basis"], "docs": {**seed.DEMO_DOCS, **docs}}


def passing(validation):
    """The same validation, as it would be once every finding is closed."""
    return {**validation, "checks": [{**c, "status": "pass"} if c["status"] in ("warn", "fail") else c for c in validation["checks"]]}


def test_the_demo_model_is_not_ready_and_the_heaviest_points_come_first(validation):
    v = verdict.verdict(model(), validation, [ALARM])
    assert v["state"] == "fail" and v["statement"] == "Not ready for inspection."
    assert v["readiness"] == 50 and v["counts"] == {"ready": 4, "attention": 0, "gap": 4}
    assert [w["status"] for w in v["weights"]] == ["fail", "fail", "missing", "warn"]  # failed tests, then missing answers, then warnings
    bias, production, answers, data = v["weights"]
    assert bias["title"] == "Its results differ by age band" and "ratio 0.73" in bias["facts"] and bias["articles"] == ["Art. 9", "Art. 10"]
    assert production["facts"].startswith("October 2026: PSI 0.289") and production["articles"] == ["Art. 72"]
    assert answers["title"] == "3 of the 8 written answers are missing" and "Balanza has drafted them" in answers["facts"]
    assert data["articles"] == ["Art. 10"]
    assert (v["steps"], v["drafted"], v["reach"]) == (6, 3, 100)


def test_ready_only_when_nothing_weighs(validation):
    v = verdict.verdict(model(**EVERY_ANSWER), passing(validation), [QUIET])
    assert v["state"] == "pass" and v["statement"] == "Ready for inspection."
    assert v["weights"] == [] and v["steps"] == 0 and v["reach"] is None
    assert v["readiness"] == 100


def test_a_warning_alone_is_nearly_ready(validation):
    v = verdict.verdict(model(**EVERY_ANSWER), passing(validation), [{**ALARM, "overall": "warn"}])
    assert v["state"] == "warn" and v["statement"] == "Nearly ready for inspection."
    assert [w["title"] for w in v["weights"]] == ["In production it no longer behaves as validated"]


def test_an_untested_model_says_so_first_and_promises_nothing():
    v = verdict.verdict(model(), None, [])
    assert v["state"] == "fail"
    assert v["weights"][0]["title"] == "The model has not been tested"
    assert v["reach"] is None  # what a first validation will find cannot be known


def test_other_risk_classes_are_named_for_what_they_are():
    for risk_class, statement in (("not_high", "Not classed as high-risk."), ("limited", "Transparency duties only."), ("unclassified", "Still to be classified.")):
        v = verdict.verdict(model(risk_class), None, [])
        assert v["state"] == "na" and v["statement"] == statement
        assert "good practice" in v["summary"]


def test_the_page_never_claims_compliance():
    words = " ".join(verdict.STATEMENTS.values()).lower()
    assert "compliant" not in words and "complies" not in words
