"""The seal: the evidence of a model, closed so that any later change shows.

A document has to be believed: nobody can tell whether a number was changed
after the tests were run. A sealed pack can be checked. Sealing puts
everything on record for a model (its written answers, the validation, the
monitoring months and the history) into one file, and takes the SHA-256
fingerprint of that content. That fingerprint is the seal. Change one
character afterwards and the content no longer gives the same seal.

What a seal shows, and what it does not:
- An intact seal shows that nothing in the pack changed after it was sealed.
- It does not show that the data was true to begin with.
- It does not show who sealed it. The method is open, so a changed pack can
  be sealed again and will carry a different seal. Whoever relies on a pack
  should hold its seal from the day it was made: it is printed on the
  verdict page for that reason.

A pack carries results and fingerprints. It never carries the loans.
"""
from __future__ import annotations

import hashlib
import json
import re

from . import __version__, aiact, database, verdict
from .validation import DatasetError, fingerprint, read_csv, run_validation

FORMAT = "balanza-seal/1"
SEALED = "evidence.sealed"  # the entry a seal leaves in the history; it is not part of what gets sealed
SEAL = re.compile(r"^[0-9a-f]{64}$")
MODEL_FIELDS = ("name", "owner", "use_case", "purpose", "model_type", "version", "risk_class", "risk_basis", "docs", "created_at")
LOCAL = ("id", "model_id")  # numbers that only mean something inside one database


class PackError(ValueError):
    """The file is not a pack this Balanza can read. The message is written for the user."""


def _plain(value):
    """The same content must give the same seal whichever program last saved the file.

    Some programs write 1.0 as 1. Whole numbers are therefore always sealed as whole numbers.
    """
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, float) and value.is_integer() and abs(value) < 1e15:
        return int(value)
    return value


def code(content: dict) -> str:
    """The seal of a content: the SHA-256 of its one canonical spelling (keys in order, no spaces, UTF-8)."""
    spelled = json.dumps(_plain(content), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(spelled.encode("utf-8")).hexdigest()


def _without_local(record: dict) -> dict:
    return {key: value for key, value in record.items() if key not in LOCAL}


def content(model_id: int, sealed_at: str, previous_seal: str | None, made_with: str) -> dict | None:
    """Everything on record for a model, in the shape that gets sealed."""
    model = database.get_model(model_id)
    if not model:
        return None
    validation = database.latest_validation(model_id)
    return {
        "format": FORMAT,
        "made_with": made_with,
        "sealed_at": sealed_at,
        "previous_seal": previous_seal,  # each seal holds the one before it, so the seals of a model form a chain
        "model": {field: model[field] for field in MODEL_FIELDS},
        "validation": _without_local(validation) if validation else None,
        "validations": [_without_local(item) for item in database.list_validations(model_id)],
        "monitoring": database.list_monitoring(model_id),
        "history": database.full_audit(model_id, without=SEALED),
    }


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "model"


def file_name(model_name: str, sealed_at: str, seal: str) -> str:
    return f"balanza-seal-{_slug(model_name)}-{sealed_at[:10]}-{seal[:8]}.json"


def seal(model_id: int) -> dict | None:
    """Seal the evidence as it stands now, keep the pack and note it in the history."""
    seals = database.list_seals(model_id)
    previous = seals[0]["seal"] if seals else None
    sealed_at = database.now()
    sealed = content(model_id, sealed_at, previous, __version__)
    if sealed is None:
        return None
    mark = code(sealed)
    pack = {
        "seal": mark,
        "about": "Evidence sealed by Balanza. To check it, open Balanza and choose 'Verify a sealed pack'. Any change to 'content' breaks the seal.",
        "content": sealed,
    }
    database.add_seal(model_id, mark, sealed_at, previous, __version__, json.dumps(pack, ensure_ascii=False, indent=1))
    answers = sum(1 for field in aiact.DOC_FIELDS if aiact.is_written(sealed["model"]["docs"].get(field)))
    database.log(
        model_id, SEALED,
        f"Seal {mark[:12]}… over {answers} written answers, {len(sealed['validations'])} validation{'' if len(sealed['validations']) == 1 else 's'}"
        f" and {len(sealed['monitoring'])} monitoring month{'' if len(sealed['monitoring']) == 1 else 's'}.",
    )
    return {"seal": mark, "sealed_at": sealed_at, "previous_seal": previous, "file_name": file_name(sealed["model"]["name"], sealed_at, mark)}


def state(model_id: int) -> dict:
    """Is the evidence under seal, and is it still exactly what was sealed?"""
    seals = database.list_seals(model_id)
    if not seals:
        return {"state": "none", "seal": None, "sealed_at": None, "count": 0}
    last = seals[0]
    now = content(model_id, last["sealed_at"], last["previous_seal"], last["made_with"])
    unchanged = now is not None and code(now) == last["seal"]
    return {"state": "sealed" if unchanged else "changed", "seal": last["seal"], "sealed_at": last["sealed_at"], "count": len(seals)}


# ---------------------------------------------------------------- verifying a pack


def read(text: str) -> dict:
    """A pack from its file, or a PackError that says what is wrong."""
    try:
        pack = json.loads(text)
    except ValueError:
        raise PackError("This file is not a sealed pack: it is not the kind of file Balanza writes when it seals.") from None
    inside = pack.get("content") if isinstance(pack, dict) else None
    if not isinstance(inside, dict) or not isinstance(pack.get("seal"), str) or not SEAL.match(pack["seal"]):
        raise PackError("This file is not a sealed pack: it has no seal and content.")
    if inside.get("format") != FORMAT:
        raise PackError("This pack was sealed in a format this version of Balanza does not read. Update Balanza and try again.")
    return pack


def _inside(sealed: dict) -> dict:
    """What an intact pack holds, read by this Balanza from the sealed evidence itself."""
    model, validation, monitoring = sealed["model"], sealed["validation"], sealed["monitoring"]
    today = verdict.verdict(model, validation, monitoring)
    return {
        "model": {key: model[key] for key in ("name", "owner", "version")},
        "risk_label": aiact.RISK_LABELS[model["risk_class"]],
        "statement": today["statement"],
        "verdict_state": today["state"],
        "readiness": today["readiness"],
        "answers": sum(1 for field in aiact.DOC_FIELDS if aiact.is_written(model["docs"].get(field))),
        "answers_total": len(aiact.DOC_FIELDS),
        "validation": {key: validation[key] for key in ("dataset_name", "dataset_sha256", "created_at", "n_rows", "overall", "counts")} if validation else None,
        "validations": len(sealed["validations"]),
        "months": [{"period": month["period"], "overall": month["overall"]} for month in monitoring],
        "history": len(sealed["history"]),
    }


def _reweigh(sealed: dict, data_text: str) -> dict:
    """Weigh the file again and compare every check with the sealed one."""
    sha = fingerprint(data_text)
    validation = sealed["validation"]
    month = next((m["period"] for m in sealed["monitoring"] if m.get("dataset_sha256") == sha), None)
    if not validation or sha != validation["dataset_sha256"]:
        return {"sha256": sha, "same_file": False, "month": month}
    again = {check["id"]: check for check in run_validation(read_csv(data_text))["checks"]}
    differences = []
    for check in validation["checks"]:
        now = again.get(check["id"])
        if not now or (now["status"], now["display"]) != (check["status"], check["display"]):
            differences.append({"name": check["name"], "sealed": check["display"], "now": now["display"] if now else "not measured"})
    total = len(validation["checks"])
    return {"sha256": sha, "same_file": True, "month": None, "checks": total, "same": total - len(differences), "differences": differences}


def verify(pack_text: str, data_text: str | None = None) -> dict:
    """Is the pack intact, was it sealed here, what does it hold, and does the data file weigh the same?"""
    pack = read(pack_text)
    sealed = pack["content"]
    computed = code(sealed)
    intact = computed == pack["seal"]
    result = {
        "intact": intact,
        "seal": pack["seal"],
        "computed": computed,
        "sealed_at": sealed.get("sealed_at") if isinstance(sealed.get("sealed_at"), str) else None,
        "made_with": sealed.get("made_with") if isinstance(sealed.get("made_with"), str) else None,
        "previous_seal": sealed.get("previous_seal") if isinstance(sealed.get("previous_seal"), str) else None,
        "this_version": __version__,
        "sealed_here": database.find_seal(pack["seal"]) if intact else None,
        "inside": None,
        "reweigh": None,
    }
    if not intact:
        return result  # nothing a broken pack says about itself is worth repeating
    try:
        result["inside"] = _inside(sealed)
        if data_text is not None:
            result["reweigh"] = _reweigh(sealed, data_text)
    except DatasetError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, IndexError):
        raise PackError("The seal is intact, but this version of Balanza cannot read what the pack holds. Update Balanza and try again.") from None
    return result
