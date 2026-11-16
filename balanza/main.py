"""The web server: a small API and the page that uses it.

Run it with:  python -m uvicorn balanza.main:app
"""
from __future__ import annotations

import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__, aiact, database, report, seed
from .validation import DatasetError, fingerprint, read_csv, run_monitoring, run_validation

STATIC = database.ROOT / "static"
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
PERIOD = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init()
    seed.seed()
    yield


class FreshStatic(StaticFiles):
    """Static files the browser must re-check on every visit.

    Without this, a browser can keep showing yesterday's page for a while
    after Balanza is updated. Re-checking is cheap: unchanged files are not
    sent again.
    """

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


app = FastAPI(title="Balanza", version=__version__, lifespan=lifespan)
app.mount("/static", FreshStatic(directory=STATIC), name="static")


class NewModel(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    owner: str = Field(min_length=2, max_length=120)
    use_case: str
    purpose: str = Field(default="", max_length=400)
    model_type: str = Field(default="", max_length=120)
    version: str = Field(default="", max_length=40)


# ---------------------------------------------------------------- helpers


def _model_or_404(model_id: int) -> dict:
    model = database.get_model(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found.")
    return model


def _summary(model: dict) -> dict:
    """One line of the inventory."""
    validation = database.latest_validation(model["id"])
    monitoring = database.list_monitoring(model["id"])
    status = aiact.evidence(model, validation, monitoring)
    return {
        **{key: model[key] for key in ("id", "name", "owner", "use_case", "purpose", "model_type", "version", "risk_class", "risk_basis", "created_at")},
        "use_case_label": aiact.USE_CASES[model["use_case"]]["label"],
        "risk_label": aiact.RISK_LABELS[model["risk_class"]],
        "validation": validation["overall"] if validation else None,
        "validated_at": validation["created_at"] if validation else None,
        "monitoring": monitoring[-1]["overall"] if monitoring else None,
        "monitoring_period": monitoring[-1]["period"] if monitoring else None,
        "readiness": status["readiness"],
        "evidence_counts": status["counts"],
    }


async def _read_csv_upload(file: UploadFile) -> tuple[str, dict]:
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="The file is larger than 25 MB.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="The file must be a CSV saved as UTF-8 text.") from None
    try:
        return text, read_csv(text)
    except DatasetError as error:
        raise HTTPException(status_code=400, detail=str(error)) from None


def _validate(model_id: int, name: str, text: str, table: dict) -> dict:
    try:
        result = run_validation(table)
    except DatasetError as error:
        raise HTTPException(status_code=400, detail=str(error)) from None
    database.add_validation(model_id, name, fingerprint(text), result)
    return {"overall": result["overall"], "counts": result["counts"]}


# ---------------------------------------------------------------- pages


@app.get("/", include_in_schema=False)
def home() -> FileResponse:
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/models/{model_id}/technical-file", response_class=HTMLResponse, include_in_schema=False)
def technical_file(model_id: int) -> str:
    html = report.technical_file(model_id)
    if html is None:
        raise HTTPException(status_code=404, detail="Model not found.")
    return html


# ---------------------------------------------------------------- API


@app.get("/api/meta")
def meta() -> dict:
    return {
        "version": __version__,
        "deadline": aiact.HIGH_RISK_DATE.isoformat(),
        "days_left": aiact.days_to_deadline(),
        "use_cases": {key: {"label": value["label"], "risk_class": value["risk_class"], "risk_label": aiact.RISK_LABELS[value["risk_class"]], "basis": value["basis"]} for key, value in aiact.USE_CASES.items()},
        "doc_fields": aiact.DOC_FIELDS,
    }


@app.get("/api/models")
def list_models() -> list[dict]:
    return [_summary(model) for model in database.list_models()]


@app.post("/api/models", status_code=201)
def register_model(new: NewModel) -> dict:
    if new.use_case not in aiact.USE_CASES:
        raise HTTPException(status_code=400, detail="Unknown use case.")
    use_case = aiact.USE_CASES[new.use_case]
    model_id = database.create_model(
        name=new.name.strip(),
        owner=new.owner.strip(),
        use_case=new.use_case,
        risk_class=use_case["risk_class"],
        risk_basis=use_case["basis"],
        purpose=new.purpose.strip(),
        model_type=new.model_type.strip(),
        version=new.version.strip(),
    )
    return _summary(database.get_model(model_id))


@app.get("/api/models/{model_id}")
def model_detail(model_id: int) -> dict:
    model = _model_or_404(model_id)
    validation = database.latest_validation(model_id)
    monitoring = database.list_monitoring(model_id)
    return {
        "model": {**_summary(model), "docs": model["docs"]},
        "evidence": aiact.evidence(model, validation, monitoring),
        "validation": validation,
        "validations": database.list_validations(model_id),
        "monitoring": monitoring,
        "audit": database.list_audit(model_id),
    }


@app.patch("/api/models/{model_id}/docs")
def update_docs(model_id: int, changes: dict[str, str]) -> dict:
    _model_or_404(model_id)
    unknown = set(changes) - set(aiact.DOC_FIELDS)
    if unknown:
        raise HTTPException(status_code=400, detail="Unknown field: " + ", ".join(sorted(unknown)))
    if any(len(text) > 6000 for text in changes.values()):
        raise HTTPException(status_code=400, detail="Each answer can have up to 6,000 characters.")
    return database.update_docs(model_id, {key: text.strip() for key, text in changes.items()})


@app.post("/api/models/{model_id}/validations", status_code=201)
async def validate_upload(model_id: int, file: UploadFile = File(...)) -> dict:
    _model_or_404(model_id)
    text, table = await _read_csv_upload(file)
    return _validate(model_id, file.filename or "upload.csv", text, table)


@app.post("/api/models/{model_id}/validations/demo", status_code=201)
def validate_demo(model_id: int) -> dict:
    _model_or_404(model_id)
    text = seed.demo_dataset_csv()
    return _validate(model_id, seed.DEMO_DATASET_NAME, text, read_csv(text))


@app.post("/api/models/{model_id}/monitoring", status_code=201)
async def record_monitoring(model_id: int, period: str = Form(...), file: UploadFile = File(...)) -> dict:
    _model_or_404(model_id)
    if not PERIOD.match(period):
        raise HTTPException(status_code=400, detail="The period must look like 2026-11 (year and month).")
    validation = database.latest_validation(model_id)
    if not validation:
        raise HTTPException(status_code=409, detail="Validate the model first: monitoring compares new loans with the validated model.")
    text, table = await _read_csv_upload(file)
    try:
        result = run_monitoring(table, validation["reference_profile"], validation["auc"], validation.get("auc_se", 0.0))
    except DatasetError as error:
        raise HTTPException(status_code=400, detail=str(error)) from None
    database.add_monitoring(model_id, period, fingerprint(text), result)
    return {"period": period, "overall": result["overall"]}


@app.get("/api/demo/dataset.csv", response_class=PlainTextResponse)
def demo_dataset() -> PlainTextResponse:
    return PlainTextResponse(
        seed.demo_dataset_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{seed.DEMO_DATASET_NAME}"'},
    )


@app.get("/api/demo/monitoring.csv", response_class=PlainTextResponse)
def demo_monitoring() -> PlainTextResponse:
    return PlainTextResponse(
        seed.demo_batch_csv(len(seed.SCENARIO)),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="demo_month_scored.csv"'},
    )
