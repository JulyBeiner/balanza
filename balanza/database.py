"""Storage: one SQLite file. Simple on purpose, easy to replace later."""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SCHEMA = """
CREATE TABLE IF NOT EXISTS models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    owner TEXT NOT NULL,
    use_case TEXT NOT NULL,
    purpose TEXT NOT NULL DEFAULT '',
    model_type TEXT NOT NULL DEFAULT '',
    version TEXT NOT NULL DEFAULT '',
    risk_class TEXT NOT NULL,
    risk_basis TEXT NOT NULL,
    docs TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS validations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id INTEGER NOT NULL REFERENCES models(id),
    created_at TEXT NOT NULL,
    dataset_name TEXT NOT NULL,
    dataset_sha256 TEXT NOT NULL,
    overall TEXT NOT NULL,
    result TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS monitoring (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id INTEGER NOT NULL REFERENCES models(id),
    period TEXT NOT NULL,
    created_at TEXT NOT NULL,
    dataset_sha256 TEXT NOT NULL,
    overall TEXT NOT NULL,
    result TEXT NOT NULL,
    UNIQUE (model_id, period)
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id INTEGER REFERENCES models(id),
    at TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT NOT NULL
);
"""


def db_path() -> Path:
    return Path(os.environ.get("BALANZA_DB", ROOT / "balanza.db"))


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@contextmanager
def connect():
    connection = sqlite3.connect(db_path())
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def init() -> None:
    with connect() as db:
        db.executescript(SCHEMA)


# ---------------------------------------------------------------- models


def _model(row: sqlite3.Row) -> dict:
    model = dict(row)
    model["docs"] = json.loads(model["docs"])
    return model


def create_model(name, owner, use_case, risk_class, risk_basis, purpose="", model_type="", version="", docs=None) -> int:
    with connect() as db:
        cursor = db.execute(
            "INSERT INTO models (name, owner, use_case, purpose, model_type, version, risk_class, risk_basis, docs, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (name, owner, use_case, purpose, model_type, version, risk_class, risk_basis, json.dumps(docs or {}), now()),
        )
        model_id = cursor.lastrowid
    log(model_id, "model.registered", f"{name} registered as '{risk_class}'.")
    return model_id


def list_models() -> list[dict]:
    with connect() as db:
        return [_model(row) for row in db.execute("SELECT * FROM models ORDER BY id")]


def get_model(model_id: int) -> dict | None:
    with connect() as db:
        row = db.execute("SELECT * FROM models WHERE id = ?", (model_id,)).fetchone()
    return _model(row) if row else None


def update_docs(model_id: int, changes: dict) -> dict:
    model = get_model(model_id)
    docs = {**model["docs"], **changes}
    with connect() as db:
        db.execute("UPDATE models SET docs = ? WHERE id = ?", (json.dumps(docs), model_id))
    log(model_id, "docs.updated", "Updated: " + ", ".join(sorted(changes)) + ".")
    return docs


def count_models() -> int:
    with connect() as db:
        return db.execute("SELECT COUNT(*) FROM models").fetchone()[0]


# ---------------------------------------------------------------- validations


def _validation(row: sqlite3.Row) -> dict:
    record = dict(row)
    record.update(json.loads(record.pop("result")))
    return record


def add_validation(model_id: int, dataset_name: str, dataset_sha256: str, result: dict) -> int:
    with connect() as db:
        cursor = db.execute(
            "INSERT INTO validations (model_id, created_at, dataset_name, dataset_sha256, overall, result)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (model_id, now(), dataset_name, dataset_sha256, result["overall"], json.dumps(result)),
        )
        validation_id = cursor.lastrowid
    counts = result["counts"]
    log(
        model_id,
        "validation.run",
        f"{dataset_name} (sha256 {dataset_sha256[:12]}…): {result['overall']},"
        f" {counts['pass']} pass, {counts['warn']} warning{'' if counts['warn'] == 1 else 's'}, {counts['fail']} failed.",
    )
    return validation_id


def latest_validation(model_id: int) -> dict | None:
    with connect() as db:
        row = db.execute(
            "SELECT * FROM validations WHERE model_id = ? ORDER BY id DESC LIMIT 1", (model_id,)
        ).fetchone()
    return _validation(row) if row else None


def list_validations(model_id: int) -> list[dict]:
    with connect() as db:
        rows = db.execute(
            "SELECT id, created_at, dataset_name, dataset_sha256, overall FROM validations"
            " WHERE model_id = ? ORDER BY id DESC",
            (model_id,),
        ).fetchall()
    return [dict(row) for row in rows]


# ---------------------------------------------------------------- monitoring


def add_monitoring(model_id: int, period: str, dataset_sha256: str, result: dict) -> None:
    with connect() as db:
        db.execute(
            "INSERT INTO monitoring (model_id, period, created_at, dataset_sha256, overall, result)"
            " VALUES (?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (model_id, period) DO UPDATE SET created_at = excluded.created_at,"
            " dataset_sha256 = excluded.dataset_sha256, overall = excluded.overall, result = excluded.result",
            (model_id, period, now(), dataset_sha256, result["overall"], json.dumps(result)),
        )
    log(
        model_id,
        "monitoring.recorded",
        f"{period} (sha256 {dataset_sha256[:12]}…): {result['overall']}. "
        + ", ".join(signal["display"] for signal in result["signals"])
        + ".",
    )


def list_monitoring(model_id: int) -> list[dict]:
    with connect() as db:
        rows = db.execute(
            "SELECT period, created_at, dataset_sha256, result FROM monitoring WHERE model_id = ? ORDER BY period",
            (model_id,),
        ).fetchall()
    records = []
    for row in rows:
        record = dict(row)
        record.update(json.loads(record.pop("result")))
        records.append(record)
    return records


# ---------------------------------------------------------------- audit trail


def log(model_id: int | None, action: str, detail: str) -> None:
    with connect() as db:
        db.execute(
            "INSERT INTO audit_log (model_id, at, action, detail) VALUES (?, ?, ?, ?)",
            (model_id, now(), action, detail),
        )


def list_audit(model_id: int, limit: int = 200) -> list[dict]:
    with connect() as db:
        rows = db.execute(
            "SELECT at, action, detail FROM audit_log WHERE model_id = ? ORDER BY id DESC LIMIT ?",
            (model_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]
