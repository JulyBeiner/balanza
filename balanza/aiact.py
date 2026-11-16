"""What the EU AI Act (Regulation (EU) 2024/1689) asks of a high-risk model,
and how much evidence Balanza holds for each requirement.

Important: Balanza organises evidence. It does not give legal advice and it
does not replace the conformity assessment. The words used here are
"evidence ready / needs attention / gap", never "compliant".
"""
from __future__ import annotations

from datetime import date

# High-risk obligations for stand-alone Annex III systems (credit scoring is
# one of them) apply from this date, after the 2026 "Digital Omnibus on AI"
# moved it from 2 August 2026.
HIGH_RISK_DATE = date(2027, 12, 2)

USE_CASES = {
    "credit_scoring": {
        "label": "Credit scoring of individuals",
        "risk_class": "high",
        "basis": "Annex III, point 5(b): AI systems used to evaluate the creditworthiness of natural persons or to establish their credit score.",
    },
    "insurance_pricing": {
        "label": "Life or health insurance: risk and pricing",
        "risk_class": "high",
        "basis": "Annex III, point 5(c): risk assessment and pricing for natural persons in life and health insurance.",
    },
    "fraud_detection": {
        "label": "Financial fraud detection",
        "risk_class": "not_high",
        "basis": "Annex III, point 5(b) leaves out AI systems used to detect financial fraud.",
    },
    "chatbot": {
        "label": "Customer chatbot or assistant",
        "risk_class": "limited",
        "basis": "Art. 50: people must be told that they are talking to an AI system.",
    },
    "other": {
        "label": "Other use",
        "risk_class": "unclassified",
        "basis": "Needs a case-by-case assessment against Art. 6 and Annex III.",
    },
}

RISK_LABELS = {
    "high": "High-risk",
    "limited": "Transparency duties",
    "not_high": "Not high-risk",
    "unclassified": "To be assessed",
}

# The free-text answers only the lender can give.
DOC_FIELDS = {
    "intended_purpose": {
        "label": "Intended purpose",
        "help": "What decision does the model support, for which customers and products, and who uses its output?",
    },
    "data_description": {
        "label": "Data used",
        "help": "Where the training and test data comes from, the period it covers, how it was cleaned and what it leaves out.",
    },
    "design_choices": {
        "label": "Design choices",
        "help": "Type of model, the inputs it uses and why, what it optimises, and the approval threshold.",
    },
    "human_oversight": {
        "label": "Human oversight",
        "help": "Who can review and overrule the model, in which cases a person must decide, and how they are trained.",
    },
    "limitations": {
        "label": "Known limitations",
        "help": "Situations and groups where the model is less reliable, and uses it was not built for.",
    },
    "risk_management": {
        "label": "Risk management",
        "help": "The risks identified (including the failed checks), who owns each one and the measure taken.",
    },
    "logging": {
        "label": "Logging in production",
        "help": "What is recorded for each decision (inputs, score, decision, model version, reviewer) and for how long.",
    },
    "monitoring_plan": {
        "label": "Monitoring plan",
        "help": "What is measured after launch, how often, the limits that trigger action and who acts.",
    },
}

MIN_ANSWER = 40  # characters; shorter answers are treated as not written yet
TO_COMPLETE = "[to complete"  # left by Balanza's drafts wherever only the lender knows the answer


def is_written(text: str | None) -> bool:
    """An answer counts once it is long enough and has no part left to complete."""
    text = (text or "").strip()
    return len(text) >= MIN_ANSWER and TO_COMPLETE not in text

REQUIREMENTS = [
    {
        "id": "art9",
        "article": "Art. 9",
        "title": "Risk management",
        "plain": "Know what can go wrong with the model and keep a living plan to deal with it.",
        "checks": ["fairness"],
        "docs": ["risk_management"],
    },
    {
        "id": "art10",
        "article": "Art. 10",
        "title": "Data and data governance",
        "plain": "The data must be relevant, representative and examined for bias.",
        "checks": ["data", "fairness"],
        "docs": ["data_description"],
    },
    {
        "id": "art11",
        "article": "Art. 11 and Annex IV",
        "title": "Technical documentation",
        "plain": "A file that explains how the model was built and tested, kept up to date.",
        "checks": [],
        "docs": ["intended_purpose", "design_choices"],
        "needs_validation": True,
    },
    {
        "id": "art12",
        "article": "Art. 12",
        "title": "Record-keeping",
        "plain": "Automatic logs, so that what the model did can be traced afterwards.",
        "checks": [],
        "docs": ["logging"],
        "needs_validation": True,
    },
    {
        "id": "art13",
        "article": "Art. 13",
        "title": "Transparency",
        "plain": "Whoever uses the model must understand what it does and where it fails.",
        "checks": [],
        "docs": ["intended_purpose", "limitations"],
    },
    {
        "id": "art14",
        "article": "Art. 14",
        "title": "Human oversight",
        "plain": "A person must be able to understand, question and overrule the model.",
        "checks": [],
        "docs": ["human_oversight"],
    },
    {
        "id": "art15",
        "article": "Art. 15",
        "title": "Accuracy and robustness",
        "plain": "The model must be accurate enough, and stay that way on new loans.",
        "checks": ["performance", "calibration", "stability"],
        "docs": [],
    },
    {
        "id": "art72",
        "article": "Art. 72",
        "title": "Post-market monitoring",
        "plain": "Keep watching the model after launch and act when it gets worse.",
        "checks": [],
        "docs": ["monitoring_plan"],
        "needs_monitoring": True,
    },
]

CATEGORY_LABELS = {
    "data": "Data quality checks",
    "performance": "Accuracy checks",
    "calibration": "Calibration checks",
    "stability": "Stability checks",
    "fairness": "Bias checks",
}

_RANK = {"pass": 0, "na": 0, "warn": 1, "fail": 2, "missing": 2}


def days_to_deadline(today: date | None = None) -> int:
    return (HIGH_RISK_DATE - (today or date.today())).days


def _worst(statuses: list[str]) -> str:
    return max(statuses, key=lambda status: _RANK[status]) if statuses else "missing"


def evidence(model: dict, validation: dict | None, monitoring: list[dict]) -> dict:
    """For each requirement, list the pieces of evidence and their state."""
    docs = model.get("docs") or {}
    checks = (validation or {}).get("checks", [])
    requirements = []

    for requirement in REQUIREMENTS:
        items = []

        for category in requirement["checks"]:
            in_category = [c for c in checks if c["category"] == category]
            if not validation:
                items.append({"label": CATEGORY_LABELS[category], "status": "missing", "detail": "No validation has been run yet."})
                continue
            if not in_category:
                items.append({"label": CATEGORY_LABELS[category], "status": "missing", "detail": "The dataset did not allow these checks (for example, no protected attributes)."})
                continue
            status = _worst([c["status"] for c in in_category])
            problems = [c["name"] for c in in_category if c["status"] in ("warn", "fail")]
            detail = "All checks pass." if not problems else "Open: " + "; ".join(problems) + "."
            items.append({"label": CATEGORY_LABELS[category], "status": "pass" if status == "na" else status, "detail": detail})

        for field in requirement["docs"]:
            written = is_written(docs.get(field))
            started = TO_COMPLETE in (docs.get(field) or "")
            items.append(
                {
                    "label": DOC_FIELDS[field]["label"],
                    "status": "pass" if written else "missing",
                    "detail": "Written." if written else "Parts still to complete (Documentation tab)." if started else "Not written yet (Documentation tab).",
                }
            )

        if requirement.get("needs_validation"):
            items.append(
                {
                    "label": "Validation on record",
                    "status": "pass" if validation else "missing",
                    "detail": f"Dataset fingerprint {validation['dataset_sha256'][:12]}… kept in the audit trail." if validation else "No validation has been run yet.",
                }
            )

        if requirement.get("needs_monitoring"):
            if monitoring:
                last = monitoring[-1]
                items.append(
                    {
                        "label": "Latest monitoring period",
                        "status": last["overall"],
                        "detail": f"{last['period']}: " + ", ".join(s["display"] for s in last["signals"]) + ".",
                    }
                )
            else:
                items.append({"label": "Latest monitoring period", "status": "missing", "detail": "No production data has been recorded yet."})

        worst = _worst([item["status"] for item in items])
        state = {"pass": "ready", "warn": "attention"}.get(worst, "gap")
        requirements.append({**{k: requirement[k] for k in ("id", "article", "title", "plain")}, "state": state, "items": items})

    points = {"ready": 1.0, "attention": 0.5, "gap": 0.0}
    readiness = round(100 * sum(points[r["state"]] for r in requirements) / len(requirements))
    return {
        "readiness": readiness,
        "counts": {state: sum(1 for r in requirements if r["state"] == state) for state in ("ready", "attention", "gap")},
        "requirements": requirements,
    }
