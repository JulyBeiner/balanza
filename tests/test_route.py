"""The route to 100% and the drafts written from the evidence."""
import re

import pytest

from balanza import aiact, route, seed
from balanza.validation import read_csv, run_validation

ALARM = {
    "period": "2026-10", "overall": "fail",
    "signals": [
        {"display": "PSI 0.289", "status": "fail"},
        {"display": "AUC 0.695 (-0.073 vs validation)", "status": "warn"},
        {"display": "predicted 15.8% vs real 27.1%", "status": "fail"},
    ],
}


@pytest.fixture(scope="module")
def validation():
    result = run_validation(read_csv(seed.demo_dataset_csv()))
    return {**result, "dataset_name": seed.DEMO_DATASET_NAME, "dataset_sha256": "ab" * 32, "created_at": "2026-11-16T07:31:09Z"}


def model(**docs):
    return {"name": "Demo", "docs": {**seed.DEMO_DOCS, **docs}}


def test_the_route_starts_with_the_quick_answers_and_ends_at_100(validation):
    plan = route.route(model(), validation, [ALARM])
    assert plan["readiness"] == 50
    assert [step["id"] for step in plan["steps"]] == [
        "write.limitations", "write.risk_management", "write.monitoring_plan",  # written answers first
        "act.data", "act.fairness",                                            # then the findings of the tests
        "monitor.alarm",                                                       # then production
    ]
    assert [step["number"] for step in plan["steps"]] == [1, 2, 3, 4, 5, 6]
    first = plan["steps"][0]
    assert first["readiness_after"] == 62 and first["closes"] == ["Art. 13"]
    assert first["has_draft"] and first["action"] == "Review the draft"
    readings = [step["readiness_after"] for step in plan["steps"]]
    assert readings == sorted(readings) and readings[-1] == 100  # every step moves forward, the last one finishes
    bias = next(step for step in plan["steps"] if step["id"] == "act.fairness")
    assert bias["closes"] == ["Art. 9", "Art. 10"] and "ratio 0.73" in bias["what"]


def test_without_a_validation_the_route_starts_there_and_drafts_nothing():
    plan = route.route(model(), None, [])
    assert plan["steps"][0]["id"] == "validate" and plan["steps"][0]["readiness_after"] is None
    assert route.drafts(model(), None, []) == {}
    assert not any(step.get("has_draft") for step in plan["steps"])


def test_a_model_with_everything_in_order_has_no_steps(validation):
    clean = {**validation, "checks": [{**c, "status": "pass"} for c in validation["checks"]]}
    answer = "Written by the lender, in a couple of full sentences, as the rule asks."
    plan = route.route(model(limitations=answer, risk_management=answer, monitoring_plan=answer), clean, [{**ALARM, "overall": "pass"}])
    assert plan == {"readiness": 100, "steps": []}


def test_drafts_are_written_from_the_lenders_own_numbers(validation):
    drafts = route.drafts(model(), validation, [ALARM])
    assert set(drafts) == {"limitations", "risk_management", "monitoring_plan"}  # only what is missing
    assert "18-24 approved 64.3% vs 60+ 87.9% (ratio 0.73)" in drafts["limitations"]
    assert "1,806 loans kept aside" in drafts["limitations"]
    assert "2026-10" in drafts["limitations"] and "PSI 0.289" in drafts["risk_management"]
    assert "AUC, against 0.768 at validation" in drafts["monitoring_plan"]
    for text in drafts.values():
        assert aiact.TO_COMPLETE in text                     # what only the lender knows is left open
        assert len(text) <= 6000                             # fits in an answer
        assert not re.search(r"compl(y|ies|iant|iance)|guarantee|certif", text, re.I)  # Balanza never says "compliant"


def test_a_draft_does_not_count_until_the_lender_completes_it(validation):
    draft = route.drafts(model(), validation, [ALARM])["limitations"]
    assert not aiact.is_written(draft)
    art13 = lambda docs: next(r for r in aiact.evidence(model(**docs), validation, [ALARM])["requirements"] if r["id"] == "art13")
    saved_as_is = art13({"limitations": draft})
    assert saved_as_is["state"] == "gap"
    assert saved_as_is["items"][-1]["detail"] == "Parts still to complete (Documentation tab)."
    step = route.route(model(limitations=draft), validation, [ALARM])["steps"][0]
    assert step["id"] == "write.limitations" and step["action"] == "Finish the answer" and not step["has_draft"]
    completed = re.sub(r"\[to complete[^\]]*\]", "consumer loans above 60,000 euros", draft)
    assert aiact.is_written(completed) and art13({"limitations": completed})["state"] == "ready"
