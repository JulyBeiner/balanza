"""The technical file: one printable page that follows Annex IV of the AI Act.

It mixes what Balanza measured (validation, monitoring, history) with what
only the lender can write (purpose, oversight, risks). Anything not written
yet is shown as a clearly marked gap, never hidden.
"""
from __future__ import annotations

from html import escape

from . import __version__, aiact, database

STATUS_WORD = {"pass": "Pass", "warn": "Warning", "fail": "Fail", "na": "Not measured"}
CATEGORY_TITLE = {
    "data": "Data quality",
    "performance": "Accuracy",
    "calibration": "Calibration",
    "stability": "Stability",
    "fairness": "Bias",
}

CSS = """
@font-face { font-family: "Geist"; src: url("/static/fonts/Geist-Variable.woff2") format("woff2"); font-weight: 100 900; }
@font-face { font-family: "Geist Mono"; src: url("/static/fonts/GeistMono-Variable.woff2") format("woff2"); font-weight: 100 900; }
:root { --blanco:#ffffff; --hielo:#f5f6f8; --niebla:#e8ebef; --platino:#c5cad3; --plomo:#667080; --grafito:#39414e; --tinta:#0d1117;
        --bruma:#8d96a6; --cian:#22d8f0; --azul:#2f6bff; --celeste:#4d8dff;
        --pasa:#0e7f58; --aviso:#a35f00; --falla:#c22f1c; --falla-fondo:#fceeea;
        --sans:"Geist", system-ui, sans-serif; --mono:"Geist Mono", ui-monospace, monospace; }
* { box-sizing: border-box; }
body { margin:0; background:var(--hielo); color:var(--tinta); font:400 15px/1.65 var(--sans); -webkit-font-smoothing: antialiased; }
main { max-width: 900px; margin: 40px auto; background:var(--blanco); border:1px solid var(--niebla); }
.cover { position:relative; overflow:hidden; background:var(--tinta); color:var(--blanco); padding:48px 80px 0; min-height:440px;
         display:flex; flex-direction:column; --iris-a:var(--cian); --iris-b:var(--azul); }
.cover::after { content:""; display:block; height:4px; margin:56px -80px 0; background:linear-gradient(90deg, var(--cian), var(--azul)); }
.brand { display:flex; align-items:center; gap:10px; font-weight:500; font-size:18px; letter-spacing:-0.035em; }
.cover-text { max-width:56%; margin-top:auto; padding-top:72px; }
.kicker { font:500 12px/18px var(--mono); color:var(--platino); max-width:40ch; }
h1 { font-size:52px; line-height:52px; font-weight:300; letter-spacing:-0.045em; margin:18px 0 0; text-wrap:balance; }
.finger { font:500 10.5px/16px var(--mono); color:var(--bruma); margin:28px 0 0; }
.finger b { display:block; font-weight:500; color:var(--platino); }
.huella { position:absolute; margin:-250px 0 0; width:500px; height:500px; right:-120px; top:50%; }
.huella svg { width:100%; height:100%; }
.sheet { padding: 40px 80px 72px; }
h2 { display:grid; grid-template-columns:64px minmax(0, 1fr); align-items:baseline; font-size:24px; line-height:30px; font-weight:500; letter-spacing:-0.02em;
     margin:64px 0 2px; padding-top:24px; border-top:1px solid var(--tinta); }
h2 span { font:300 40px/40px var(--mono); letter-spacing:-0.05em; }
h2 + .ref { margin-left:64px; }
h3 { font-size:14.5px; font-weight:600; margin:24px 0 6px; }
p { margin: 0 0 10px; color:var(--grafito); }
.ref { font:500 12px/18px var(--mono); color:var(--plomo); margin: 0 0 14px; }
.meta { display:grid; grid-template-columns: 190px 1fr; gap:6px 20px; font-size:14px; margin:0; color:var(--grafito); }
.meta dt { font:500 12px/23px var(--mono); color:var(--plomo); } .meta dd { margin:0; }
table { width:100%; border-collapse:collapse; font-size:13.5px; margin:8px 0 16px; }
th { text-align:left; font:500 11.5px/16px var(--mono); color:var(--plomo); border-bottom:1px solid var(--tinta); padding:6px 10px 8px 0; }
td { border-bottom:1px solid var(--niebla); padding:8px 10px 8px 0; vertical-align:top; color:var(--grafito); }
td.num, th.num { text-align:right; font-family:var(--mono); font-size:12.5px; }
td.num + td:not(.num), th.num + th:not(.num) { padding-left:18px; }
.s { font-weight:500; white-space:nowrap; }
.s::before { content:""; display:inline-block; width:9px; height:9px; margin-right:8px; background:currentColor; }
.s.pass { color:var(--pasa); } .s.pass::before { border-radius:50%; }
.s.warn { color:var(--aviso); } .s.warn::before { clip-path: polygon(50% 0, 100% 100%, 0 100%); }
.s.fail { color:var(--falla); }
.s.na { color:var(--plomo); } .s.na::before { height:2px; vertical-align:4px; }
.gap { background:var(--falla-fondo); color:var(--falla); padding:12px 14px; font-size:13.5px; margin:6px 0 14px; border-radius:2px; }
.gap b { display:block; font:500 11.5px/18px var(--mono); }
.note { font-size:12.5px; line-height:19px; color:var(--plomo); border-top:1px solid var(--niebla); margin-top:56px; padding-top:16px; }
.print { position:fixed; z-index:2; top:16px; right:16px; font:500 13px var(--sans); padding:12px 16px; border:0; cursor:pointer; border-radius:2px;
         background:linear-gradient(90deg, var(--cian), var(--celeste)); color:var(--tinta); box-shadow:0 0 0 1px var(--tinta); }
@media (max-width: 760px) { .cover { padding-inline:28px; } .cover::after { margin-inline:-28px; } .cover-text { max-width:none; padding-top:300px; } .sheet { padding-inline:28px; }
                            .huella { width:320px; height:320px; margin:0; top:28px; right:-60px; } .meta { grid-template-columns:1fr; gap:0; } .meta dd { margin-bottom:8px; } table { display:block; overflow-x:auto; } }
@page { margin: 16mm 0; } @page :first { margin-top: 0; }  /* on paper the ink cover runs to the edges of the first page */
@media print { body { background:#fff; } main { border:0; margin:0; max-width:none; } .print { display:none; }
               .cover { padding-inline:18mm; } .cover::after { margin-inline:-18mm; } .sheet { padding:10mm 18mm 0; }
               h2 { break-after: avoid; } tr { break-inside: avoid; } * { -webkit-print-color-adjust: exact; print-color-adjust: exact; } }
"""

FIEL = (
    "<svg viewBox='0 0 64 60' width='30' height='28' aria-hidden='true' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round'>"
    "<path d='M12.7 23l2.3 2.7M17.7 19.6l1.3 2.3M22.6 17.3l1.2 3.2M27.3 16l.6 3.4M32 16v7M36.7 16l-.6 3.4M41.4 17.3l-1.2 3.2M46.3 19.6l-1.3 2.3M51.3 23l-2.3 2.7'/>"
    "<path d='M32 46V19.5M9 46h46M9 46v4.4M55 46v4.4M4.2 51.4a4.8 4.8 0 0 0 9.6 0M50.2 51.4a4.8 4.8 0 0 0 9.6 0'/>"
    "<circle cx='32' cy='46' r='3.1' fill='currentColor' stroke='none'/></svg>"
)


def _answer(docs: dict, field: str) -> str:
    text = (docs.get(field) or "").strip()
    label = aiact.DOC_FIELDS[field]["label"]
    if aiact.is_written(text):
        paragraphs = "".join(f"<p>{escape(line)}</p>" for line in text.splitlines() if line.strip())
        return f"<h3>{escape(label)}</h3>{paragraphs}"
    return (
        f"<h3>{escape(label)}</h3>"
        f'<div class="gap"><b>TO BE COMPLETED BY THE PROVIDER</b>{escape(aiact.DOC_FIELDS[field]["help"])}</div>'
    )


def _seal(validation: dict | None) -> str:
    """La huella: the engraving drawn from the validated file's fingerprint (static/huella.js),
    printed on the cover in the two brand inks, with the fingerprint it comes from."""
    if not validation:
        return ""
    sha = escape(validation["dataset_sha256"])
    return (
        f"<p class='finger'><b>Fingerprint of the validated file (SHA-256)</b>{sha[:32]}<br>{sha[32:]}</p>"
        f"<figure class='huella' data-huella='{sha}' data-iris data-draw data-weight='0.6'></figure>"
    )


def _status(status: str) -> str:
    return f'<span class="s {escape(status)}">{STATUS_WORD.get(status, escape(status))}</span>'


def _checks_table(checks: list[dict]) -> str:
    html = []
    for category, title in CATEGORY_TITLE.items():
        rows = [c for c in checks if c["category"] == category]
        if not rows:
            continue
        html.append(f"<h3>{title}</h3><table><tr><th>Check</th><th>Result</th><th>Rule applied</th><th>Status</th></tr>")
        for c in rows:
            html.append(
                f"<tr><td>{escape(c['name'])}</td><td>{escape(c['display'])}</td>"
                f"<td>{escape(c['rule'])}</td><td>{_status(c['status'])}</td></tr>"
            )
        html.append("</table>")
    return "".join(html)


def _groups_table(fairness: dict) -> str:
    html = []
    for attribute, rows in fairness.items():
        html.append(
            f"<h3>Outcomes by {escape(attribute.replace('_', ' '))}</h3><table><tr><th>Group</th>"
            '<th class="num">Loans</th><th class="num">Approved</th><th class="num">Good payers approved</th>'
            '<th class="num">Defaults</th><th class="num">AUC</th></tr>'
        )
        for row in rows:
            good = "–" if row["good_approval_rate"] is None else f"{100 * row['good_approval_rate']:.1f}%"
            auc = "–" if row["auc"] is None else f"{row['auc']:.3f}"
            html.append(
                f"<tr><td>{escape(str(row['group']))}</td><td class=\"num\">{row['n']:,}</td>"
                f"<td class=\"num\">{100 * row['approval_rate']:.1f}%</td><td class=\"num\">{good}</td>"
                f"<td class=\"num\">{100 * row['default_rate']:.1f}%</td><td class=\"num\">{auc}</td></tr>"
            )
        html.append("</table>")
    return "".join(html)


def _under_seal(sealed: dict | None) -> str:
    """Whether the evidence in this file is the evidence that was sealed (see seal.py)."""
    if not sealed or sealed["state"] == "none":
        return "Not sealed."
    when = escape(sealed["sealed_at"].replace("T", " ").replace("Z", " UTC"))
    if sealed["state"] == "sealed":
        return f"<span style='word-break:break-all'>{escape(sealed['seal'])}</span><br>Sealed {when}. The evidence on record has not changed since."
    return f"The evidence on record has changed since the seal of {when} ({escape(sealed['seal'][:12])}…)."


def technical_file(model_id: int, sealed: dict | None = None) -> str | None:
    model = database.get_model(model_id)
    if not model:
        return None
    docs = model["docs"]
    validation = database.latest_validation(model_id)
    monitoring = database.list_monitoring(model_id)
    history = database.list_validations(model_id)
    status = aiact.evidence(model, validation, monitoring)
    counts = status["counts"]
    generated = database.now().replace("T", " ").replace("Z", " UTC")

    parts = [
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'><link rel='icon' href='data:,'>",
        f"<title>Technical documentation: {escape(model['name'])}</title><style>{CSS}</style></head><body>",
        "<button class='print' onclick='window.print()'>Print or save as PDF</button><main>",
        f"<header class='cover'><div class='brand'>{FIEL}Balanza</div><div class='cover-text'>",
        "<div class='kicker'>Technical documentation under Art. 11 and Annex IV of Regulation (EU) 2024/1689</div>",
        f"<h1>{escape(model['name'])}</h1>",
        _seal(validation),
        "</div></header><div class='sheet'>",
        "<dl class='meta'>",
        f"<dt>Provider</dt><dd>{escape(model['owner'])}</dd>",
        f"<dt>Version</dt><dd>{escape(model['version'] or '–')}</dd>",
        f"<dt>Classification</dt><dd>{escape(aiact.RISK_LABELS[model['risk_class']])}. {escape(model['risk_basis'])}</dd>",
        f"<dt>Evidence status</dt><dd>{counts['ready']} requirements with evidence ready, "
        f"{counts['attention']} needing attention, {counts['gap']} with gaps ({status['readiness']}% readiness)</dd>",
        f"<dt>Seal</dt><dd>{_under_seal(sealed)}</dd>",
        f"<dt>Generated</dt><dd>{generated}, with Balanza {__version__}</dd>",
        "</dl>",
        # 1
        "<h2><span>1</span>General description of the AI system</h2><p class='ref'>Annex IV, point 1</p>",
        f"<p>{escape(model['purpose'])}</p>" if model["purpose"] else "",
        _answer(docs, "intended_purpose"),
        # 2
        "<h2><span>2</span>Elements of the system and its development</h2><p class='ref'>Annex IV, point 2, and Art. 10</p>",
        f"<h3>Type of model</h3><p>{escape(model['model_type'] or 'Not stated.')}</p>",
        _answer(docs, "design_choices"),
        _answer(docs, "data_description"),
        # 3
        "<h2><span>3</span>Monitoring, functioning and control</h2><p class='ref'>Annex IV, point 3, and Art. 12, 13 and 14</p>",
        _answer(docs, "human_oversight"),
        _answer(docs, "limitations"),
        _answer(docs, "logging"),
        # 4
        "<h2><span>4</span>Performance: validation results</h2><p class='ref'>Annex IV, point 4, and Art. 10 and 15</p>",
    ]

    if validation:
        parts += [
            "<dl class='meta'>",
            f"<dt>Dataset</dt><dd>{escape(validation['dataset_name'])}</dd>",
            f"<dt>Fingerprint (SHA-256)</dt><dd style='word-break:break-all'>{escape(validation['dataset_sha256'])}</dd>",
            f"<dt>Run on</dt><dd>{escape(validation['created_at'])}</dd>",
            f"<dt>Loans</dt><dd>{validation['n_rows']:,} in the file, {validation['n_evaluated']:,} used to measure</dd>",
            f"<dt>Outcome</dt><dd>{validation['counts']['pass']} pass, {validation['counts']['warn']} warning{'' if validation['counts']['warn'] == 1 else 's'}, "
            f"{validation['counts']['fail']} failed</dd>",
            "</dl>",
            _checks_table(validation["checks"]),
            _groups_table(validation["charts"]["fairness"]),
            "<p class='ref'>Thresholds are industry conventions set as defaults in Balanza. They are not legal limits; "
            "the provider is responsible for reviewing and justifying them.</p>",
        ]
    else:
        parts.append("<div class='gap'><b>NO VALIDATION ON RECORD</b>Run a validation in Balanza to fill this section.</div>")

    # 5
    parts += ["<h2><span>5</span>Risk management system</h2><p class='ref'>Annex IV, point 5, and Art. 9</p>", _answer(docs, "risk_management")]
    open_findings = [c for c in (validation or {}).get("checks", []) if c["status"] in ("warn", "fail")]
    if open_findings:
        parts.append("<h3>Open findings from the latest validation</h3><table><tr><th>Finding</th><th>Result</th><th>Why it matters</th><th>Status</th></tr>")
        for c in open_findings:
            parts.append(
                f"<tr><td>{escape(c['name'])}</td><td>{escape(c['display'])}</td>"
                f"<td>{escape(c['meaning'])}</td><td>{_status(c['status'])}</td></tr>"
            )
        parts.append("</table>")

    # 6
    parts.append("<h2><span>6</span>Changes through the lifecycle</h2><p class='ref'>Annex IV, point 6</p>")
    if history:
        parts.append("<table><tr><th>Validation</th><th>Dataset</th><th>Fingerprint</th><th>Status</th></tr>")
        for item in history:
            parts.append(
                f"<tr><td>{escape(item['created_at'])}</td><td>{escape(item['dataset_name'])}</td>"
                f"<td>{escape(item['dataset_sha256'][:16])}…</td><td>{_status(item['overall'])}</td></tr>"
            )
        parts.append("</table>")
    else:
        parts.append("<p>No validations on record.</p>")

    # 7, 8
    parts += [
        "<h2><span>7</span>Standards applied</h2><p class='ref'>Annex IV, point 7</p>",
        "<div class='gap'><b>TO BE COMPLETED BY THE PROVIDER</b>List the harmonised standards or other specifications applied.</div>",
        "<h2><span>8</span>EU declaration of conformity</h2><p class='ref'>Annex IV, point 8, and Art. 47</p>",
        "<div class='gap'><b>TO BE ATTACHED BY THE PROVIDER</b>Balanza does not issue this declaration. Attach a copy once the conformity assessment is complete.</div>",
        # 9
        "<h2><span>9</span>Post-market monitoring</h2><p class='ref'>Annex IV, point 9, and Art. 72</p>",
        _answer(docs, "monitoring_plan"),
    ]
    if monitoring:
        parts.append(
            "<h3>Monitoring record</h3><table><tr><th>Period</th><th class='num'>Loans</th><th class='num'>PSI</th>"
            "<th class='num'>AUC</th><th class='num'>Predicted</th><th class='num'>Real defaults</th><th>Status</th></tr>"
        )
        for m in monitoring:
            parts.append(
                f"<tr><td>{escape(m['period'])}</td><td class='num'>{m['n_rows']:,}</td><td class='num'>{m['psi']:.3f}</td>"
                f"<td class='num'>{m['auc']:.3f}</td><td class='num'>{100 * m['predicted_rate']:.1f}%</td>"
                f"<td class='num'>{100 * m['default_rate']:.1f}%</td><td>{_status(m['overall'])}</td></tr>"
            )
        parts.append("</table>")

    parts.append(
        "<p class='note'>This document was assembled by Balanza from recorded tests and from the provider's own answers. "
        "It supports the preparation of technical documentation; it is not legal advice, a conformity assessment or a "
        "statement that the system complies with Regulation (EU) 2024/1689.</p></div></main>"
        f"<script src='/static/huella.js?v={__version__}'></script></body></html>"
    )
    return "".join(parts)
