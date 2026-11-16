"""The route: what to do next, in order, until the evidence is ready.

A lender without a model-risk team does not need another list of gaps. It
needs the next step. The route turns the evidence register into steps, says
how far each one moves the reading, and drafts the written answers from the
lender's own test results.

A draft is a starting point. It carries "[to complete: ...]" wherever only
the lender knows the answer, and an answer with one of those left in it does
not count as written. Balanza never saves a draft by itself: the lender
reviews it, corrects it and signs it.
"""
from __future__ import annotations

from . import aiact

# Categories of checks, in the words used to ask for action.
FINDINGS = {
    "data": "the data findings",
    "performance": "the accuracy findings",
    "calibration": "the calibration findings",
    "stability": "the stability findings",
    "fairness": "the bias findings",
}
PLACEHOLDER = "x" * aiact.MIN_ANSWER  # stands for "this answer has been written" when looking ahead


def _open_checks(validation: dict | None, category: str | None = None) -> list[dict]:
    return [
        c for c in (validation or {}).get("checks", [])
        if c["status"] in ("warn", "fail") and (category is None or c["category"] == category)
    ]


def _alarm(monitoring: list[dict]) -> dict | None:
    """The latest monitoring period, when it is not a pass."""
    return monitoring[-1] if monitoring and monitoring[-1]["overall"] != "pass" else None


def _finding_line(check: dict) -> str:
    return f"{check['name']}: {check['display']}."


def _signals(period: dict) -> str:
    return ", ".join(s["display"] for s in period["signals"] if s["status"] != "pass")


# ---------------------------------------------------------------- drafts


def drafts(model: dict, validation: dict | None, monitoring: list[dict]) -> dict[str, str]:
    """A first draft of each answer that the test results can support.

    Only for answers not written yet, and only where there is evidence to
    write from. What the lender alone knows is left as "[to complete: ...]".
    """
    if not validation:
        return {}
    docs = model.get("docs") or {}
    missing = [field for field in aiact.DOC_FIELDS if not aiact.is_written(docs.get(field))]
    findings = _open_checks(validation)
    alarm = _alarm(monitoring)
    tested = (
        f"{validation['n_evaluated']:,} loans" + (" kept aside" if validation.get("has_samples") else "")
        + f" from {validation['dataset_name']}"
    )
    out = {}

    if "limitations" in missing:
        lines = [f"The model was tested on {tested}. These are the weak points the tests found:"]
        lines += [f"- {_finding_line(c)} {c['meaning']}" for c in findings] or ["- The tests found no weak point."]
        unmeasured = [c["name"] for c in validation["checks"] if c["status"] == "na"]
        if unmeasured:
            lines.append("Not measured: " + "; ".join(unmeasured) + ".")
        if alarm:
            lines.append(f"In production, the period {alarm['period']} raised an alarm: {_signals(alarm)}.")
        lines += [
            "The model was not built for: [to complete: loan types, amounts or customers outside its intended use].",
            "The data does not cover: [to complete: periods or economic conditions missing from the data].",
        ]
        out["limitations"] = "\n".join(lines)

    if "risk_management" in missing:
        lines = ["Risks found by the tests, with an owner and a measure for each:"]
        for c in findings:
            lines.append(f"- {_finding_line(c)} Owner: [to complete: name or role]. Measure: [to complete: what will be done and by when].")
        if alarm:
            lines.append(f"- The model is drifting in production ({alarm['period']}: {_signals(alarm)}). Owner: [to complete: name or role]. Measure: [to complete: what will be done and by when].")
        if not findings and not alarm:
            lines.append("- The tests and the monitoring found no open risk.")
        lines.append("Other risks, beyond what the tests can see: [to complete: for example misuse, data errors at the source, changes in the market].")
        lines.append("These risks are reviewed [to complete: how often and by whom].")
        out["risk_management"] = "\n".join(lines)

    if "monitoring_plan" in missing:
        lines = [
            "Every month, on the loans whose outcome is known, three things are measured against the validated model:",
            "- Whether the applicants have changed (PSI of the scores). Watch above 0.10, act above 0.25.",
            f"- Whether the model is still accurate (AUC, against {validation['auc']:.3f} at validation). Only drops that chance cannot explain count.",
            "- Whether it still predicts the right number of defaults (predicted against real default rate).",
        ]
        if monitoring:
            last = monitoring[-1]
            lines.append(f"Months on record: {len(monitoring)}. Latest, {last['period']}: " + ", ".join(s["display"] for s in last["signals"]) + ".")
        lines += [
            "Who reviews the result each month: [to complete: name or role].",
            "On a warning: [to complete: what is done and within how many days].",
            "On a fail: [to complete: for example, stop using the model for new loans until it is validated again].",
        ]
        out["monitoring_plan"] = "\n".join(lines)

    if "data_description" in missing:
        by_id = {c["id"]: c for c in validation["checks"]}
        lines = [f"{validation['dataset_name']}: {validation['n_rows']:,} loans, with a real default rate of {100 * validation['default_rate']:.1f}%."]
        if validation.get("has_samples"):
            lines.append(f"{validation['n_evaluated']:,} of them were kept aside to test the model and were not used to build it.")
        for check_id in ("data.missing", "data.duplicates", "data.representation"):
            if check_id in by_id:
                lines.append(_finding_line(by_id[check_id]))
        if validation.get("protected_attributes"):
            names = ", ".join(a.replace("_", " ") for a in validation["protected_attributes"])
            lines.append(f"Protected attributes in the file: {names}. [to complete: confirm they are used only to test for bias and are never given to the model].")
        lines += [
            "Where the data comes from and the period it covers: [to complete].",
            "How it was cleaned and what it leaves out: [to complete].",
        ]
        out["data_description"] = "\n".join(lines)

    return out


# ---------------------------------------------------------------- the route


def _look_ahead(model: dict, validation: dict | None, monitoring: list[dict], written: set, passing: set, quiet: bool) -> dict:
    """The evidence as it would be once some steps are done."""
    docs = {**(model.get("docs") or {}), **{field: PLACEHOLDER for field in written}}
    if validation and passing:
        validation = {**validation, "checks": [
            {**c, "status": "pass"} if c["category"] in passing and c["status"] in ("warn", "fail") else c
            for c in validation["checks"]
        ]}
    if monitoring and quiet:
        monitoring = [*monitoring[:-1], {**monitoring[-1], "overall": "pass"}]
    return aiact.evidence({**model, "docs": docs}, validation, monitoring)


def route(model: dict, validation: dict | None, monitoring: list[dict]) -> dict:
    """The steps left, in the order to take them, each with the reading it leads to."""
    docs = model.get("docs") or {}
    now = aiact.evidence(model, validation, monitoring)
    available = drafts(model, validation, monitoring)
    articles = {r["id"]: r["article"].split(" and ")[0] for r in aiact.REQUIREMENTS}
    written, passing, quiet = set(), set(), False
    before = now
    steps = []

    def add(step: dict, after: dict | None) -> None:
        nonlocal before
        if after is not None:
            was = {r["id"]: r["state"] for r in before["requirements"]}
            step["readiness_after"] = after["readiness"]
            step["closes"] = [articles[r["id"]] for r in after["requirements"] if r["state"] == "ready" and was[r["id"]] != "ready"]
            before = after
        else:
            step["readiness_after"], step["closes"] = None, []
        step["number"] = len(steps) + 1
        steps.append(step)

    # 1. Nothing can be weighed without a file.
    if not validation:
        add({
            "id": "validate", "kind": "validate", "tab": "validation", "action": "Go to validation",
            "title": "Validate a scored file",
            "what": "Upload the model's scored loans. Every requirement that rests on a test is waiting for this, and so are the drafts of the written answers.",
            "articles": [articles[r["id"]] for r in aiact.REQUIREMENTS if r["checks"] or r.get("needs_validation")],
        }, None)

    # 2. The written answers: quick to close, and Balanza can draft some of them.
    missing = [field for field in aiact.DOC_FIELDS if not aiact.is_written(docs.get(field))]

    def gain(field: str) -> int:
        return _look_ahead(model, validation, monitoring, {field}, set(), False)["readiness"] - now["readiness"]

    for field in sorted(missing, key=lambda f: (-gain(f), f not in available, list(aiact.DOC_FIELDS).index(f))):
        written.add(field)
        label = aiact.DOC_FIELDS[field]["label"]
        drafted = field in available
        started = bool((docs.get(field) or "").strip())
        add({
            "id": f"write.{field}", "kind": "write", "tab": "documentation", "field": field, "has_draft": drafted and not started,
            "action": "Finish the answer" if started else "Review the draft" if drafted else "Write the answer",
            "title": f"Write: {label.lower()}",
            "what": aiact.DOC_FIELDS[field]["help"]
            + (" The answer on record still has parts to complete." if started
               else " Balanza has drafted it from the test results: review it, complete it and save it." if drafted else ""),
            "articles": [articles[r["id"]] for r in aiact.REQUIREMENTS if field in r["docs"]],
        }, _look_ahead(model, validation, monitoring, written, passing, quiet))

    # 3. The findings of the tests: each needs a decision, then a new validation.
    for category, name in FINDINGS.items():
        findings = _open_checks(validation, category)
        if not findings:
            continue
        passing.add(category)
        add({
            "id": f"act.{category}", "kind": "decide", "tab": "validation",
            "action": "Try another cut-off" if category == "fairness" else "See the findings",
            "title": f"Decide on {name}",
            "what": "Open: " + " ".join(_finding_line(c) for c in findings)
            + " For each one, change the model or how it is used, or explain and justify it. Then validate again.",
            "articles": [articles[r["id"]] for r in aiact.REQUIREMENTS if category in r["checks"]],
            "hypothetical": True,
        }, _look_ahead(model, validation, monitoring, written, passing, quiet))

    # 4. Production: start watching, or act on the alarm.
    if validation and not monitoring:
        add({
            "id": "monitor.start", "kind": "monitor", "tab": "monitoring", "action": "Go to monitoring",
            "title": "Record the first month of production loans",
            "what": "Upload one month of scored loans with their outcome. Balanza compares them with the validated model.",
            "articles": [articles["art72"]],
        }, None)
    alarm = _alarm(monitoring)
    if alarm:
        quiet = True
        add({
            "id": "monitor.alarm", "kind": "monitor", "tab": "monitoring", "action": "See the monitoring",
            "title": f"Act on the monitoring alarm of {alarm['period']}",
            "what": f"Open: {_signals(alarm)}. Find the cause, decide whether the model can stay in use, and record the next month.",
            "articles": [articles["art72"]],
            "hypothetical": True,
        }, _look_ahead(model, validation, monitoring, written, passing, quiet))

    return {"readiness": now["readiness"], "steps": steps}
