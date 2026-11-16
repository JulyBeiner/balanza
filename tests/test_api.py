"""The API, from the outside, the way the page uses it."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    import os

    os.environ["BALANZA_DB"] = str(tmp_path_factory.mktemp("db") / "test.db")
    from balanza.main import app

    with TestClient(app) as test_client:  # runs startup: creates tables and demo data
        yield test_client
    del os.environ["BALANZA_DB"]


def test_page_and_meta(client):
    assert client.get("/").status_code == 200
    assert client.get("/").headers["cache-control"] == "no-cache"  # an update shows up without a hard reload
    for asset in ("app.css", "app.js", "huella.js", "fonts/Geist-Variable.woff2", "fonts/GeistMono-Variable.woff2"):
        response = client.get(f"/static/{asset}")
        assert response.status_code == 200, asset
        assert response.headers["cache-control"] == "no-cache", asset
    meta = client.get("/api/meta").json()
    assert meta["deadline"] == "2027-12-02"
    assert meta["use_cases"]["credit_scoring"]["risk_class"] == "high"


def test_demo_inventory(client):
    models = client.get("/api/models").json()
    assert [m["name"] for m in models] == ["Consumer Credit Scorecard", "Card Fraud Detector", "Customer Support Assistant"]
    credit = models[0]
    assert credit["risk_class"] == "high"
    assert credit["validation"] == "fail"
    assert credit["monitoring"] == "fail"
    assert models[1]["risk_class"] == "not_high"
    assert models[1]["validation"] is None


def test_demo_model_detail(client):
    detail = client.get("/api/models/1").json()
    assert len(detail["monitoring"]) == 12
    assert detail["validation"]["dataset_sha256"]
    states = {r["id"]: r["state"] for r in detail["evidence"]["requirements"]}
    assert states == {
        "art9": "gap",        # bias found and no risk plan written
        "art10": "gap",       # bias found
        "art11": "ready",
        "art12": "ready",
        "art13": "gap",       # limitations not written
        "art14": "ready",
        "art15": "ready",
        "art72": "gap",       # model is drifting and there is no monitoring plan
    }
    assert detail["evidence"]["readiness"] == 50
    assert any(entry["action"] == "validation.run" for entry in detail["audit"])


def test_register_validate_document_monitor(client):
    created = client.post(
        "/api/models",
        json={"name": "SME Loan Score", "owner": "Risk · Test", "use_case": "credit_scoring", "version": "0.3"},
    )
    assert created.status_code == 201
    model_id = created.json()["id"]
    assert created.json()["readiness"] == 0

    # monitoring before validation is refused
    batch = client.get("/api/demo/monitoring.csv").text
    early = client.post(f"/api/models/{model_id}/monitoring", data={"period": "2026-11"}, files={"file": ("m.csv", batch, "text/csv")})
    assert early.status_code == 409

    # validate with an uploaded file
    dataset = client.get("/api/demo/dataset.csv").text
    run = client.post(f"/api/models/{model_id}/validations", files={"file": ("book.csv", dataset, "text/csv")})
    assert run.status_code == 201
    assert run.json()["overall"] == "fail"

    # write one answer; the evidence moves
    answer = "A credit analyst reviews every rejection and can overrule the model, writing down the reason each time."
    assert client.patch(f"/api/models/{model_id}/docs", json={"human_oversight": answer}).status_code == 200
    states = {r["id"]: r["state"] for r in client.get(f"/api/models/{model_id}").json()["evidence"]["requirements"]}
    assert states["art14"] == "ready"
    assert states["art15"] == "ready"

    # record one month of production loans
    month = client.post(f"/api/models/{model_id}/monitoring", data={"period": "2026-11"}, files={"file": ("m.csv", batch, "text/csv")})
    assert month.status_code == 201
    assert month.json() == {"period": "2026-11", "overall": "fail"}

    detail = client.get(f"/api/models/{model_id}").json()
    assert [m["period"] for m in detail["monitoring"]] == ["2026-11"]
    assert [entry["action"] for entry in detail["audit"]][::-1] == ["model.registered", "validation.run", "docs.updated", "monitoring.recorded"]


def test_bad_requests_are_explained(client):
    assert client.get("/api/models/999").status_code == 404
    assert client.post("/api/models", json={"name": "X", "owner": "Y", "use_case": "credit_scoring"}).status_code == 422
    assert client.post("/api/models", json={"name": "Some model", "owner": "Team", "use_case": "nope"}).status_code == 400
    assert client.patch("/api/models/1/docs", json={"not_a_field": "x"}).status_code == 400

    bad = client.post("/api/models/1/validations", files={"file": ("x.csv", "score,outcome\n0.1,0\n", "text/csv")})
    assert bad.status_code == 400
    assert "'default' is missing" in bad.json()["detail"]

    period = client.post("/api/models/1/monitoring", data={"period": "November"}, files={"file": ("m.csv", "score,default\n", "text/csv")})
    assert period.status_code == 400


def test_technical_file(client):
    page = client.get("/models/1/technical-file")
    assert page.status_code == 200
    html = page.text
    assert "Annex IV" in html
    assert "TO BE COMPLETED BY THE PROVIDER" in html  # limitations were left empty in the demo
    assert "Similar approval rates by age band" in html
    assert "not legal advice" in html
    sha = client.get("/api/models/1").json()["validation"]["dataset_sha256"]
    assert f"data-huella='{sha}'" in html  # the engraving of the validated file is on the cover
    assert client.get("/models/999/technical-file").status_code == 404


def test_text_is_escaped_in_the_technical_file(client):
    created = client.post("/api/models", json={"name": "<script>alert(1)</script>", "owner": "Team <b>", "use_case": "other"}).json()
    html = client.get(f"/models/{created['id']}/technical-file").text
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_the_route_and_the_drafts_come_with_the_model(client):
    detail = client.get("/api/models/1").json()
    assert detail["route"]["readiness"] == detail["evidence"]["readiness"] == 50
    assert detail["route"]["steps"][0]["id"] == "write.limitations"
    assert "ratio 0.73" in detail["drafts"]["limitations"]
    assert len(detail["validation"]["what_if"]) == 50
    # a draft is only offered: nothing was written into the model's answers
    assert detail["model"]["docs"]["limitations"] == ""
    # saving the draft untouched does not close the gap
    assert client.patch("/api/models/1/docs", json={"limitations": detail["drafts"]["limitations"]}).status_code == 200
    again = client.get("/api/models/1").json()
    assert again["evidence"]["readiness"] == 50 and again["route"]["steps"][0]["action"] == "Finish the answer"
    assert client.patch("/api/models/1/docs", json={"limitations": ""}).status_code == 200


def test_verify_a_file_against_what_was_weighed(client):
    dataset = client.get("/api/demo/dataset.csv").text
    same = client.post("/api/models/1/verify", files={"file": ("copy.csv", dataset, "text/csv")}).json()
    assert same["sha256"] == same["validated"]["dataset_sha256"]
    assert [match["kind"] for match in same["matches"]] == ["validation"]
    assert same["matches"][0]["dataset_name"] == "demo_credit_scored.csv"

    lines = dataset.splitlines(keepends=True)
    lines[1] = lines[1].replace(",", ", ", 1)  # one cell changed, by one space
    changed = client.post("/api/models/1/verify", files={"file": ("copy.csv", "".join(lines), "text/csv")}).json()
    assert changed["matches"] == [] and changed["sha256"] != same["sha256"]
    assert changed["validated"]["dataset_sha256"] == same["sha256"]

    # nothing is stored or logged by a verification
    assert not any("verify" in entry["action"] for entry in client.get("/api/models/1").json()["audit"])
    assert client.post("/api/models/1/verify", files={"file": ("x.bin", b"\xff\xfe\x00", "application/octet-stream")}).status_code == 400
    assert client.post("/api/models/999/verify", files={"file": ("x.csv", "a", "text/csv")}).status_code == 404
