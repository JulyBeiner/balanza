"""The verdict: one page for the person who decides.

The person who tries Balanza is rarely the person who signs. The one who
signs will not open an application or read a twenty-page technical file.
This page says, on one sheet of paper, where the model stands today, what
weighs most against it and what it takes to close it.

The words stay within what Balanza can know. "Ready for inspection" means
the evidence is ready: the tests pass and the written answers exist. It is
never a statement that the model complies with the AI Act.
"""
from __future__ import annotations

from datetime import date, datetime
from html import escape

from . import __version__, aiact, database, route
from .report import FIEL

# What is said in large type, for a high-risk model and for the other classes.
STATEMENTS = {
    "fail": "Not ready for inspection.",
    "warn": "Nearly ready for inspection.",
    "pass": "Ready for inspection.",
    "not_high": "Not classed as high-risk.",
    "limited": "Transparency duties only.",
    "unclassified": "Still to be classified.",
}
STATUS_WORD = {"fail": "Fail", "warn": "Warning", "missing": "Missing"}
SHOWN = 3  # a page for a busy reader: the three points that weigh most

# The findings of the tests, in the words of someone who does not read test results.
FINDINGS = {
    "fairness": ("Its results differ by {attributes}", "The same model gives groups of people different results. Correct it, or justify it."),
    "performance": ("Its accuracy is in question", "It approves loans that fail and turns away loans that would have been repaid."),
    "calibration": ("Its forecast of defaults is off", "It expects a different number of defaults than really happen."),
    "stability": ("It is not stable on loans it has not seen", "Its test results may not hold on new loans."),
    "data": ("The data it was tested on has weak points", "The other numbers on this page are only as good as the data behind them."),
}
ORDER = list(FINDINGS)


def _articles(of) -> list[str]:
    """The articles of the requirements that match, written short: "Art. 11", not "Art. 11 and Annex IV"."""
    return [r["article"].split(" and ")[0] for r in aiact.REQUIREMENTS if of(r)]


def _sentence(text: str) -> str:
    text = text.strip()
    return text[:1].upper() + text[1:] + ("" if text.endswith(".") else ".")


def _long_date(day: date) -> str:
    return f"{day.day}\u00a0{day:%B}\u00a0{day.year}"  # no %-d: it does not exist on Windows; no-break spaces keep a date on one line


def _month(period: str) -> str:
    year, month = period.split("-")
    return f"{date(int(year), int(month), 1):%B} {year}"


def _count(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def weights(model: dict, validation: dict | None, monitoring: list[dict]) -> list[dict]:
    """Everything that weighs against the model today, heaviest first."""
    docs = model.get("docs") or {}
    found = []

    if not validation:
        found.append({
            "rank": 100, "status": "missing", "title": "The model has not been tested",
            "facts": "No scored file has been validated in Balanza.",
            "why": "Without a test, nothing is known about its accuracy or its bias.",
            "articles": _articles(lambda r: r["checks"] or r.get("needs_validation")),
        })

    for index, category in enumerate(ORDER):
        open_checks = [c for c in (validation or {}).get("checks", []) if c["category"] == category and c["status"] in ("warn", "fail")]
        if not open_checks:
            continue
        open_checks.sort(key=lambda c: c["status"] != "fail")  # the failed ones first
        failed = open_checks[0]["status"] == "fail"
        title, why = FINDINGS[category]
        if category == "fairness":
            attributes = list(dict.fromkeys(c["id"].split(".")[1].replace("_", " ") for c in open_checks))
            title = title.format(attributes=" and ".join(attributes))
        more = len(open_checks) - 2
        found.append({
            "rank": (90 if failed else 60) - index, "status": "fail" if failed else "warn", "title": title,
            "facts": " ".join(_sentence(c["display"]) for c in open_checks[:2]) + (f" And {_count(more, 'more finding', 'more findings')}." if more > 0 else ""),
            "why": why,
            "articles": _articles(lambda r: category in r["checks"]),
        })

    if monitoring and monitoring[-1]["overall"] != "pass":
        last = monitoring[-1]
        failed = last["overall"] == "fail"
        found.append({
            "rank": 80 if failed else 50, "status": "fail" if failed else "warn", "title": "In production it no longer behaves as validated",
            "facts": f"{_month(last['period'])}: " + ", ".join(s["display"] for s in last["signals"] if s["status"] != "pass") + ".",
            "why": "On real loans it has moved away from the model that was tested.",
            "articles": _articles(lambda r: r.get("needs_monitoring")),
        })
    elif validation and not monitoring:
        found.append({
            "rank": 40, "status": "missing", "title": "No month of production loans on record",
            "facts": "Nothing has been recorded since the model was validated.",
            "why": "The law asks to keep watching a model once it is in use.",
            "articles": _articles(lambda r: r.get("needs_monitoring")),
        })

    unwritten = [field for field in aiact.DOC_FIELDS if not aiact.is_written(docs.get(field))]
    if unwritten:
        drafted = len(set(unwritten) & set(route.drafts(model, validation, monitoring)))
        labels = ", ".join(aiact.DOC_FIELDS[field]["label"].lower() for field in unwritten)
        found.append({
            "rank": 70, "status": "missing",
            "title": f"{len(unwritten)} of the {len(aiact.DOC_FIELDS)} written answers {'is' if len(unwritten) == 1 else 'are'} missing",
            "facts": _sentence(labels) + (
                " Balanza has drafted them from the test results." if drafted == len(unwritten)
                else f" Balanza has drafted {drafted} of them from the test results." if drafted else ""
            ),
            "why": "The law asks for these in writing, by a person who signs them.",
            "articles": _articles(lambda r: set(r["docs"]) & set(unwritten)),
        })

    return sorted(found, key=lambda item: -item["rank"])


def verdict(model: dict, validation: dict | None, monitoring: list[dict]) -> dict:
    """Where the model stands today, in the terms of the page."""
    status = aiact.evidence(model, validation, monitoring)
    counts = status["counts"]
    plan = route.route(model, validation, monitoring)
    # Where the route leads is only known when every step can be looked ahead (a first validation cannot).
    after = [step["readiness_after"] for step in plan["steps"]]
    reach = max(after) if after and None not in after else None
    high = model["risk_class"] == "high"
    state = ("fail" if counts["gap"] else "warn" if counts["attention"] else "pass") if high else "na"

    if high:
        split = [f"{counts['ready']} with the evidence ready"]
        if counts["attention"]:
            split.append(f"{counts['attention']} needing attention")
        if counts["gap"]:
            split.append(f"{counts['gap']} with a gap")
        summary = f"Of the {len(aiact.REQUIREMENTS)} requirements the EU AI Act sets for a high-risk model: " + ", ".join(split) + "."
    else:
        summary = model["risk_basis"] + " The requirements for high-risk models are kept here as good practice."

    return {
        "state": state,
        "statement": STATEMENTS[state if high else model["risk_class"]],
        "summary": summary,
        "readiness": status["readiness"],
        "counts": counts,
        "days_left": aiact.days_to_deadline(),
        "weights": [{key: item[key] for key in ("status", "title", "facts", "why", "articles")} for item in weights(model, validation, monitoring)],
        "steps": len(plan["steps"]),
        "drafted": sum(1 for step in plan["steps"] if step.get("has_draft")),
        "reach": reach if reach is not None and reach > status["readiness"] else None,
    }


# ---------------------------------------------------------------- the page

CSS = """
@font-face { font-family: "Geist"; src: url("/static/fonts/Geist-Variable.woff2") format("woff2"); font-weight: 100 900; }
@font-face { font-family: "Geist Mono"; src: url("/static/fonts/GeistMono-Variable.woff2") format("woff2"); font-weight: 100 900; }
:root { --blanco:#ffffff; --hielo:#f5f6f8; --niebla:#e8ebef; --platino:#c5cad3; --plomo:#667080; --grafito:#39414e; --tinta:#0d1117;
        --bruma:#8d96a6; --cian:#22d8f0; --azul:#2f6bff; --celeste:#4d8dff;
        --pasa:#0e7f58; --aviso:#a35f00; --falla:#c22f1c; --pasa-luz:#34d29b; --aviso-luz:#f5a93b; --falla-luz:#ff6b57;
        --sans:"Geist", system-ui, sans-serif; --mono:"Geist Mono", ui-monospace, monospace; }
* { box-sizing: border-box; }
h1, h2, h3, p, ul, figure { margin:0; padding:0; } ul { list-style:none; }
body { margin:0; background:var(--hielo); color:var(--tinta); font:400 14px/1.5 var(--sans); font-feature-settings:"ss01"; -webkit-font-smoothing:antialiased; }
/* one sheet of A4, on screen and on paper */
main { width:210mm; height:297mm; margin:40px auto; background:var(--blanco); box-shadow:0 0 0 1px var(--niebla); display:flex; flex-direction:column; overflow:hidden; }

/* the ink half: who, the verdict, the two readings */
.ink { position:relative; overflow:hidden; flex:none; background:var(--tinta); color:var(--blanco); padding:32px 56px 28px; --iris-a:var(--cian); --iris-b:var(--azul); }
.ink::after { content:""; position:absolute; left:0; right:0; bottom:0; height:4px; background:linear-gradient(90deg, var(--cian), var(--azul)); }
.ink > * { position:relative; z-index:1; }
.top { display:flex; justify-content:space-between; align-items:flex-start; gap:20px; min-height:36px; }
.brand { display:flex; align-items:center; gap:10px; font-weight:500; font-size:18px; letter-spacing:-0.035em; }
.stamp { font:500 11.5px/18px var(--mono); color:var(--platino); text-align:right; }
.stamp span { display:block; } .stamp .sealed { color:var(--cian); } .stamp .changed { color:var(--aviso-luz); }
.who { margin-top:22px; max-width:56%; }
.who b { display:block; font-size:19px; line-height:25px; font-weight:500; letter-spacing:-0.02em; }
.who span { display:block; font:500 11px/17px var(--mono); color:var(--bruma); } .who b + span { margin-top:5px; }
h1 { font-size:62px; line-height:59px; font-weight:300; letter-spacing:-0.05em; margin-top:22px; max-width:7.2em; text-wrap:balance; }
h1::before { content:""; display:block; width:18px; height:18px; margin-bottom:18px; background:var(--bruma); }
h1.fail::before { background:var(--falla-luz); }
h1.warn::before { background:var(--aviso-luz); clip-path:polygon(50% 0, 100% 100%, 0 100%); }
h1.pass::before { background:var(--pasa-luz); border-radius:50%; }
h1.na::before { height:4px; }
.summary { font-size:14px; line-height:21px; color:var(--platino); margin-top:20px; max-width:50ch; }
.readings { display:flex; gap:52px; margin-top:24px; }
.readings .value { font:300 48px/46px var(--mono); letter-spacing:-0.06em; }
.readings .value small { font-size:24px; letter-spacing:-0.02em; margin-left:2px; }
.readings .label { font-size:12px; line-height:17px; color:var(--bruma); margin-top:7px; max-width:27ch; }
.ink .huella { position:absolute; z-index:0; width:480px; height:480px; right:-190px; top:66px; }
.huella svg { width:100%; height:100%; }

/* the paper half: what weighs, what it takes, what was weighed */
.paper { flex:1; min-height:0; display:flex; flex-direction:column; padding:22px 56px 18px; }
h2 { font-size:17px; line-height:22px; font-weight:500; letter-spacing:-0.02em; }
.weights { margin-top:8px; border-top:1px solid var(--tinta); }
.weights li { display:grid; grid-template-columns:112px minmax(0, 1fr); gap:0 20px; padding:8px 0 9px; border-bottom:1px solid var(--niebla); }
.weights h3 { font-size:15px; line-height:21px; font-weight:600; letter-spacing:-0.01em; }
.weights .facts { font:500 11px/17px var(--mono); color:var(--grafito); margin-top:2px; display:-webkit-box; -webkit-box-orient:vertical; -webkit-line-clamp:2; overflow:hidden; }
.weights .why { font-size:12.5px; line-height:18px; color:var(--plomo); margin-top:3px; }
.weights .art { font:500 10.5px/16px var(--mono); color:var(--plomo); margin-top:3px; }
.s { font-weight:500; font-size:13px; line-height:21px; white-space:nowrap; }
.s::before { content:""; display:inline-block; width:9px; height:9px; margin-right:8px; background:currentColor; }
.s.fail { color:var(--falla); }
.s.warn { color:var(--aviso); } .s.warn::before { clip-path:polygon(50% 0, 100% 100%, 0 100%); }
.s.missing { color:var(--grafito); } .s.missing::before { background:none; box-shadow:inset 0 0 0 1.5px currentColor; }
.head { display:flex; justify-content:space-between; align-items:baseline; gap:28px; }
.head p { font-size:12px; line-height:17px; color:var(--plomo); text-align:right; }
.clear { font-size:15px; line-height:23px; color:var(--grafito); margin-top:8px; padding-top:14px; border-top:1px solid var(--tinta); max-width:60ch; }
.takes { margin-top:14px; }
.takes-row { display:flex; gap:52px; margin-top:8px; padding-top:12px; border-top:1px solid var(--tinta); }
.takes .value { font:300 34px/34px var(--mono); letter-spacing:-0.06em; }
.takes .value small { font-size:18px; letter-spacing:-0.02em; margin-left:1px; }
.takes .label { font-size:12px; line-height:17px; color:var(--plomo); margin-top:5px; max-width:22ch; }
.foot { margin-top:auto; padding-top:12px; }
.tight .why { display:none; }  /* a very full sheet drops the explanations before it drops a line of the footer */
.weighed { display:grid; grid-template-columns:112px minmax(0, 1fr); gap:3px 20px; padding:7px 0; border-top:1px solid var(--tinta); border-bottom:1px solid var(--niebla); font:500 10.5px/16px var(--mono); color:var(--grafito); }
.weighed b { font-weight:500; color:var(--plomo); }
.weighed span { display:block; overflow-wrap:anywhere; }
.last { display:flex; justify-content:space-between; align-items:flex-end; gap:36px; margin-top:10px; }
.note { font-size:10px; line-height:14px; color:var(--plomo); max-width:80ch; }
.motto { font-size:13px; line-height:16px; font-weight:500; letter-spacing:-0.02em; white-space:nowrap; }
.print { position:fixed; z-index:2; top:16px; right:16px; font:500 13px var(--sans); padding:12px 16px; border:0; cursor:pointer; border-radius:2px;
         background:linear-gradient(90deg, var(--cian), var(--celeste)); color:var(--tinta); box-shadow:0 0 0 1px var(--tinta); }
.print:focus-visible { outline:2px solid var(--tinta); outline-offset:3px; }

/* narrower than a sheet of paper: the page flows instead */
@media screen and (max-width: 860px) {
  main { width:auto; height:auto; margin:0; box-shadow:none; overflow:visible; }
  .ink { padding:28px 24px 36px; } .paper { padding:26px 24px 24px; }
  .who { max-width:none; margin-top:316px; } h1 { font-size:50px; line-height:49px; }
  .ink .huella { width:300px; height:300px; right:-56px; top:60px; }
  .readings { gap:28px; flex-wrap:wrap; }
  .weights li, .weighed { grid-template-columns:1fr; } .weights .art { margin:0 0 6px; } .weights .facts { display:block; }
  .head { display:block; } .head p { text-align:left; margin-top:4px; } .takes-row { flex-wrap:wrap; gap:20px 32px; }
  .last { flex-direction:column; align-items:flex-start; gap:12px; } .foot { padding-top:32px; }
  .print { position:static; display:block; width:100%; border-radius:0; box-shadow:none; }
}
@page { size: A4; margin: 0; }
@media print {
  body { background:#fff; } .print { display:none; } main { margin:0; box-shadow:none; }
  * { -webkit-print-color-adjust:exact; print-color-adjust:exact; }
}
"""


def _reading(value: str, unit: str, label: str) -> str:
    return f"<div><p class='value'>{value}<small>{unit}</small></p><p class='label'>{escape(label)}</p></div>"


def page(model_id: int, sealed: dict | None = None) -> str | None:
    """The sheet. `sealed` is the state of the model's seal (seal.state), printed so the reader can check the pack against it."""
    model = database.get_model(model_id)
    if not model:
        return None
    validation = database.latest_validation(model_id)
    monitoring = database.list_monitoring(model_id)
    v = verdict(model, validation, monitoring)
    high = model["risk_class"] == "high"
    today = datetime.strptime(database.now()[:10], "%Y-%m-%d").date()
    deadline = _long_date(aiact.HIGH_RISK_DATE)

    stamp = f"Verdict of {_long_date(today)}"
    under_seal = ""
    if sealed and sealed["state"] != "none":
        when = _long_date(datetime.strptime(sealed["sealed_at"][:10], "%Y-%m-%d").date())
        if sealed["state"] == "sealed":
            stamp += f"<span class='sealed'>Under seal since {when}</span>"
            under_seal = f"<b>Seal</b><div><span>{escape(sealed['seal'])}</span></div>"
        else:
            stamp += f"<span class='changed'>Changed since the seal of {when}</span>"

    counts = v["counts"]
    readings = [_reading(
        str(v["readiness"]), "%",
        f"of the evidence is ready: {counts['ready']} of the {len(aiact.REQUIREMENTS)} requirements" if high else "of the evidence is ready, kept as good practice",
    )]
    if high:
        days = v["days_left"]
        readings.append(
            _reading(f"{days:,}", "", f"{'day' if days == 1 else 'days'} until the high-risk rules apply, {deadline}") if days >= 0
            else _reading(f"{-days:,}", "", f"{'day' if days == -1 else 'days'} since the high-risk rules began to apply, {deadline}")
        )

    shown, rest = v["weights"][:SHOWN], len(v["weights"]) - SHOWN
    if shown:
        items = "".join(
            f"<li><div><span class='s {item['status']}'>{STATUS_WORD[item['status']]}</span>"
            f"<p class='art'>{escape(', '.join(item['articles']))}</p></div>"
            f"<div><h3>{escape(item['title'])}</h3><p class='facts'>{escape(item['facts'])}</p><p class='why'>{escape(item['why'])}</p></div></li>"
            for item in shown
        )
        more = f"<p>{_count(rest, 'more point is', 'more points are')} open: the technical file has them all.</p>" if rest > 0 else ""
        heavy = f"<div class='head'><h2>{'What weighs most' if high else 'What is open, as good practice'}</h2>{more}</div><ul class='weights'>{items}</ul>"
    else:
        heavy = "<h2>What weighs most</h2><p class='clear'>Nothing weighs against it today: the tests pass, the written answers exist and production matches the validation.</p>"

    if v["steps"]:
        row = [_reading(str(v["steps"]), "", "step left on the route" if v["steps"] == 1 else "steps left on the route")]
        if v["drafted"]:
            row.append(_reading(str(v["drafted"]), "", "written answer already drafted by Balanza" if v["drafted"] == 1 else "written answers already drafted by Balanza"))
        if v["reach"] is not None:
            row.append(_reading(str(v["reach"]), "%", "of the evidence ready once they are done"))
        how = "The steps are in Balanza, in order." + (" A draft is a start: a person completes it and signs it." if v["drafted"] else "")
        takes = f"<section class='takes'><div class='head'><h2>What it takes</h2><p>{how}</p></div><div class='takes-row'>{''.join(row)}</div></section>"
    else:
        takes = (
            "<section class='takes'><h2>What it takes</h2><p class='clear'>Nothing is open. Keep recording each month of "
            "production loans, and validate again whenever the model changes.</p></section>"
        )

    if validation:
        sha = escape(validation["dataset_sha256"])
        weighed = (
            f"<div class='weighed'><b>File weighed</b><div><span>{escape(validation['dataset_name'])}, {validation['n_rows']:,} loans, "
            f"validated {_long_date(datetime.strptime(validation['created_at'][:10], '%Y-%m-%d').date())}</span>"
            f"<span>SHA-256 {sha}</span></div>{under_seal}</div>"
        )
        seal = f"<figure class='huella' data-huella='{sha}' data-iris data-draw data-weight='0.6'></figure>"
    else:
        weighed = f"<div class='weighed'><b>File weighed</b><div><span>None yet. No scored file has been validated for this model.</span></div>{under_seal}</div>"
        seal = ""

    held = "High-risk under the EU AI Act. " + model["risk_basis"].split(":")[0] if high else aiact.RISK_LABELS[model["risk_class"]] + " under the EU AI Act"
    return "".join([
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'><link rel='icon' href='data:,'>",
        f"<title>Verdict: {escape(model['name'])}</title><style>{CSS}</style></head><body>",
        "<button class='print' onclick='window.print()'>Print or save as PDF</button><main>",
        f"<header class='ink'><div class='top'><div class='brand'>{FIEL}Balanza</div><p class='stamp'>{stamp}</p></div>",
        f"<p class='who'><b>{escape(model['name'])}</b><span>{escape(model['owner'])}</span><span>{escape(held)}</span></p>",
        f"<h1 class='{v['state']}'>{escape(v['statement'])}</h1>",
        "" if high else f"<p class='summary'>{escape(v['summary'])}</p>",  # for a high-risk model the readings say it
        f"<div class='readings'>{''.join(readings)}</div>{seal}</header>",
        f"<div class='paper'>{heavy}{takes}",
        f"<footer class='foot'>{weighed}<div class='last'><p class='note'>This page reports the state of the evidence held in Balanza {__version__} "
        "on the date shown. \"Ready\" means the tests pass and the written answers exist. It is not legal advice, a conformity assessment "
        "or a statement that the system complies with Regulation (EU) 2024/1689.</p><p class='motto'>Evidence that carries weight.</p></div></footer>",
        f"</div></main><script src='/static/huella.js?v={__version__}'></script>",
        "<script>(() => { const paper = document.querySelector('.paper'); if (paper.scrollHeight > paper.clientHeight + 1) document.body.classList.add('tight'); })();</script>",
        "</body></html>",
    ])
