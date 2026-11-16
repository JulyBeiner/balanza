"""The seal: the evidence closed into a pack, and the pack checked by whoever receives it."""
import json
import re

import pytest
from fastapi.testclient import TestClient

from balanza import seal, seed


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    import os

    os.environ["BALANZA_DB"] = str(tmp_path_factory.mktemp("db") / "seal.db")
    from balanza.main import app

    with TestClient(app) as test_client:
        yield test_client
    del os.environ["BALANZA_DB"]


def verify(client, pack_text, data_text=None):
    files = {"pack": ("pack.json", pack_text, "application/json")}
    if data_text is not None:
        files["data"] = ("data.csv", data_text, "text/csv")
    return client.post("/api/packs/verify", files=files)


@pytest.fixture(scope="module")
def first(client):
    """The first seal of the demo model, with its pack as it is downloaded."""
    assert client.get("/api/models/1").json()["seal"] == {"state": "none", "seal": None, "sealed_at": None, "count": 0}
    made = client.post("/api/models/1/seals")
    assert made.status_code == 201
    made = made.json()
    download = client.get(f"/api/models/1/seals/{made['seal']}")
    assert download.status_code == 200 and made["file_name"] in download.headers["content-disposition"]
    return {**made, "pack": download.text}


def test_sealing_gives_a_seal_and_a_pack_that_carries_no_loans(client, first):
    assert re.fullmatch(r"[0-9a-f]{64}", first["seal"]) and first["previous_seal"] is None
    assert first["file_name"].startswith("balanza-seal-consumer-credit-scorecard-") and first["file_name"].endswith(f"-{first['seal'][:8]}.json")
    pack = json.loads(first["pack"])
    assert pack["seal"] == first["seal"] == seal.code(pack["content"])
    assert set(pack["content"]) == {"format", "made_with", "sealed_at", "previous_seal", "model", "validation", "validations", "monitoring", "history"}
    a_loan = seed.demo_dataset_csv().splitlines()[1]
    assert a_loan not in first["pack"]  # results and fingerprints, never the loans
    detail = client.get("/api/models/1").json()
    assert detail["seal"]["state"] == "sealed" and detail["seal"]["seal"] == first["seal"]
    assert detail["audit"][0]["action"] == "evidence.sealed"  # sealing is noted in the history, and does not break its own seal


def test_an_intact_pack_is_recognised_and_read(client, first):
    answer = verify(client, first["pack"]).json()
    assert answer["intact"] and answer["seal"] == answer["computed"] == first["seal"]
    assert answer["sealed_here"]["model_name"] == "Consumer Credit Scorecard"
    inside = answer["inside"]
    assert inside["statement"] == "Not ready for inspection." and inside["readiness"] == 50
    assert (inside["answers"], inside["answers_total"]) == (5, 8)
    assert inside["validation"]["dataset_name"] == seed.DEMO_DATASET_NAME and len(inside["months"]) == 12
    assert answer["reweigh"] is None


def test_one_changed_number_breaks_the_seal(client, first):
    changed = first["pack"].replace("(ratio 0.73)", "(ratio 0.83)")
    assert changed != first["pack"]
    answer = verify(client, changed).json()
    assert not answer["intact"] and answer["computed"] != answer["seal"]
    assert answer["inside"] is None and answer["sealed_here"] is None  # a broken pack is not read back to the user


def test_saving_the_file_with_another_program_does_not_break_it(client, first):
    resaved = json.dumps(json.loads(first["pack"]), separators=(",", ":"))  # other spacing, same content
    assert verify(client, resaved).json()["intact"]
    assert seal.code({"a": 2.0, "b": [1.0]}) == seal.code({"b": [1], "a": 2})  # some programs write 2.0 as 2
    assert seal.code({"a": 2.5}) != seal.code({"a": 2})


def test_the_data_file_weighs_the_same_again(client, first):
    again = verify(client, first["pack"], seed.demo_dataset_csv()).json()["reweigh"]
    assert again["same_file"] and again["checks"] == again["same"] == 17 and again["differences"] == []
    lines = seed.demo_dataset_csv().splitlines()
    other = verify(client, first["pack"], "\n".join(lines[:-1]) + "\n").json()["reweigh"]  # one loan removed
    assert not other["same_file"] and other["month"] is None


def test_a_change_shows_and_the_next_seal_keeps_the_old_one_inside(client, first):
    text = "The model is weaker for applicants under 25 and for thin credit files. It was not built for business loans."
    client.patch("/api/models/1/docs", json={"limitations": text})
    assert client.get("/api/models/1").json()["seal"]["state"] == "changed"
    assert "Changed since the seal of" in client.get("/models/1/verdict").text
    second = client.post("/api/models/1/seals").json()
    assert second["previous_seal"] == first["seal"] and second["seal"] != first["seal"]
    detail = client.get("/api/models/1").json()
    assert detail["seal"]["state"] == "sealed" and detail["seal"]["count"] == 2
    assert [item["seal"] for item in detail["seals"]] == [second["seal"], first["seal"]]
    assert verify(client, client.get(f"/api/models/1/seals/{second['seal']}").text).json()["previous_seal"] == first["seal"]
    assert verify(client, first["pack"]).json()["intact"]  # the earlier pack is still intact, and still on record


def test_the_seal_is_printed_on_the_verdict_and_in_the_technical_file(client, first):
    mark = client.get("/api/models/1").json()["seal"]["seal"]
    page = client.get("/models/1/verdict").text
    assert "Under seal since" in page and mark in page
    assert mark in client.get("/models/1/technical-file").text
    assert "Not sealed." in client.get("/models/2/technical-file").text and "Under seal" not in client.get("/models/2/verdict").text


def test_what_is_not_a_pack_is_refused_in_plain_words(client):
    assert client.post("/api/models/999/seals").status_code == 404
    assert client.get("/api/models/1/seals/" + "0" * 64).status_code == 404
    for text in (seed.demo_dataset_csv(), "{}", '{"seal": "abc", "content": {}}', "[1, 2]"):
        refused = verify(client, text)
        assert refused.status_code == 400 and "not a sealed pack" in refused.json()["detail"]
    newer = json.dumps({"seal": "a" * 64, "content": {"format": "balanza-seal/9"}})
    assert "format" in verify(client, newer).json()["detail"]
    hollow = {"format": seal.FORMAT, "model": {}}
    unreadable = verify(client, json.dumps({"seal": seal.code(hollow), "content": hollow}))
    assert unreadable.status_code == 400 and "cannot read" in unreadable.json()["detail"]
