# Balanza

An end-to-end platform to build, validate, monitor and document high-risk AI models in finance, ready for the EU AI Act.

Think of it as the roadworthiness test for a lender's AI models: register the model, inspect it, keep watching it, and come out with the paperwork the law asks for.

The first model inside Balanza is my own credit risk model: it estimates the probability that a loan will not be repaid, and explains why.

Built for De Sola Boutique (AI for finance, end to end).

## Run it

On Windows, double-click `start.bat`. The first time it prepares Python and installs the libraries; then it opens Balanza in the browser.

On any system:

```
python -m venv .venv
.venv\Scripts\activate        (Windows)   |   source .venv/bin/activate   (macOS, Linux)
pip install -r requirements.txt
python run.py
```

Balanza opens at http://127.0.0.1:8010 (or the next free port, if that one is busy) with a demo inventory. Everything in the demo is invented: the lender, the people and the loans.

## What version 0.4 does

- **Inventory.** Every AI model in use, classed under the AI Act (credit scoring of individuals is high-risk: Annex III, point 5(b)).
- **Validation.** Upload a scored file and Balanza runs 17 checks: data quality, accuracy (AUC, KS), calibration, stability (PSI) and bias by gender and age. Each check shows the number, the rule applied, what it means in plain words and the article it gives evidence for.
- **Requirements.** For Art. 9 to 15 and Art. 72, what evidence exists and what is missing.
- **Monitoring.** Record a month of production loans and Balanza compares it with the validated model: have the applicants changed, is it still accurate, does it still predict the right number of defaults.
- **Technical file.** One printable page that follows Annex IV, mixing the test results with the lender's own answers. Anything not written yet is shown as a gap.
- **History.** Every validation, month and change, with the SHA-256 fingerprint of the file used.
- **The route.** What to do next, in order, until the evidence is ready, and how far each step moves the reading. Balanza drafts the missing answers from the test results; a draft with parts still to complete does not count as written.
- **What if.** Move the approval cut-off and see what would change on the validated loans: approvals, defaults and the bias checks. It shows consequences; it does not recommend a cut-off.
- **Verify a file.** Choose a file and Balanza says whether it is the one that was weighed, with the two engravings side by side. One changed cell changes the fingerprint and the drawing.

### The scored file

A CSV with one loan per row. Balanza never needs the model itself, only its scores.

| Column | Needed | Meaning |
|---|---|---|
| `score` | yes | The model's probability of default, 0 to 1 |
| `default` | yes | 1 = not repaid, 0 = repaid |
| `approved` | no | 1 = approved. If missing, loans under 15% are treated as approved |
| `sample` | no | `development` or `validation`. Unlocks the stability checks |
| `gender`, `age` | no | Unlock the bias checks. They are tested, never given to the model |
| anything else | no | Model inputs. Checked for missing values and shifts |

Download an example from the Validation tab ("Download the demo file").

### Alarms that ignore chance

One month of loans is a small sample, so numbers move by luck. A fixed rule ("warn if AUC drops 0.03") raised a false alarm in about 1 month out of 5 on data where nothing had changed. Balanza measures how much each number can move by chance (Hanley and McNeil's standard error for the AUC) and only alarms for the part of a change that chance does not explain. On the same data that is about 1 false alarm in 100 months. See `tests/test_validation.py::test_monitoring_rarely_cries_wolf`.

## What it does not do yet

- It does not give legal advice and does not replace the conformity assessment. The words are "evidence ready" and "gap", never "compliant".
- The thresholds are industry conventions set as defaults, not legal limits.
- No login, no users, no roles. It runs on one computer with one SQLite file.
- No explainability or robustness tests yet (they need access to the model, not only its scores).
- The approval-rate and equal-opportunity checks do not yet allow for chance in very small groups.

## Code map

| File | What it is |
|---|---|
| `balanza/metrics.py` | The measurements (AUC, KS, PSI, calibration, groups), NumPy only |
| `balanza/validation.py` | The inspection: the checks, their rules and what they mean |
| `balanza/aiact.py` | The AI Act requirements and how evidence maps to them |
| `balanza/route.py` | The route to 100%: the next steps, and the drafts written from the evidence |
| `balanza/report.py` | The Annex IV technical file |
| `balanza/main.py`, `balanza/database.py` | The API (FastAPI) and storage (SQLite) |
| `balanza/synthetic.py`, `balanza/demo_model.py`, `balanza/seed.py` | Invented data, the demo credit model and the demo inventory |
| `static/` | The page (plain HTML, CSS and JavaScript, no libraries). `huella.js` draws the engraving from a file's fingerprint. `fonts/` holds Geist and Geist Mono (SIL Open Font License) |
| `tests/` | 49 tests. Run them with `pip install -r requirements-dev.txt` and `pytest` |

## What it will do
- Build credit risk models that are accurate and explainable
- Check models for bias, so no group is treated unfairly
- Monitor models in production and alert when they get worse
- Generate the technical documentation the EU AI Act requires
- Answer compliance questions with the exact source (RAG)
- AI agents that prepare model and loan reviews, always with a human making the final decision

## Roadmap
1. Full-stack software
2. Cloud & DevOps
3. Data engineering
4. Data analysis
5. Data science
6. Machine learning & deep learning
7. Computer vision, language & voice
8. MLOps
9. AI engineering (RAG, evals, fine-tuning)
10. Agentic AI (multi-agent systems)
11. Final research: interpretability of my own credit model

## Data
This repository only uses public or synthetic data. No real personal data is ever stored here.

Built by July Beiner, step by step, from the math up.
