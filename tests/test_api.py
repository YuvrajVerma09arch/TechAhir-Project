"""API-level tests using FastAPI's TestClient and an isolated temporary DB."""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from app.api import get_service
from app.main import app
from app.services.triage_service import TriageService


def _sample_ticket(ticket_id: str = "T-API-1") -> dict:
    return {
        "id": ticket_id,
        "received_at": "2026-11-16 08:00",
        "customer": "API Test Customer",
        "subject": "Charged twice for my order",
        "body": "I was charged twice. Please refund the duplicate charge.",
    }


def _error(response):
    body = response.json()
    assert "error" in body, body
    return body["error"]


def _total(body: dict) -> int:
    pagination = body.get("pagination", {})
    for key in ("total", "total_count", "count"):
        if key in pagination:
            return int(pagination[key])
    raise AssertionError(f"No total count in pagination: {pagination}")


@pytest.fixture()
def service(tmp_path):
    svc = TriageService(db_path=str(tmp_path / "triage.db"))
    # Keep the report-writing side effect of the service inside the temp dir.
    svc.save_report = lambda path=None: str(tmp_path / "report.json")
    return svc


@pytest.fixture()
def client(service):
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_service] = lambda: service
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


# --- health -----------------------------------------------------------------
def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "app" in body and "version" in body


# --- batch: JSON -------------------------------------------------------------
def test_batch_json(client):
    response = client.post(
        "/api/triage/batch",
        json={"tickets": [_sample_ticket(), _sample_ticket("T-API-2")]},
    )
    assert response.status_code == 200, response.text
    assert isinstance(response.json(), dict)


def test_batch_csv_upload(client):
    csv_text = (
        "id,received_at,customer,subject,body\n"
        "T-CSV-1,2026-11-16 09:00,CSV Customer,Cannot log in,"
        "The password reset link does not work.\n"
    )
    response = client.post(
        "/api/triage/batch",
        files={"file": ("tickets.csv", io.BytesIO(csv_text.encode()), "text/csv")},
    )
    assert response.status_code == 200, response.text
    assert isinstance(response.json(), dict)


def test_batch_validation_error(client):
    response = client.post("/api/triage/batch", json={"tickets": [{"subject": "no id"}]})
    assert response.status_code == 422, response.text
    error = _error(response)
    assert error["code"] == "VALIDATION_ERROR"
    assert isinstance(error["details"], list)


def test_batch_empty(client):
    response = client.post("/api/triage/batch", json={"tickets": []})
    assert response.status_code == 400, response.text
    assert _error(response)["code"] == "EMPTY_BATCH"


def test_batch_missing_file(client):
    response = client.post(
        "/api/triage/batch",
        data={"note": "no file here"},
    )
    assert response.status_code == 400, response.text
    assert _error(response)["code"] == "BAD_REQUEST"


# --- seed -------------------------------------------------------------------
def test_seed(client):
    response = client.get("/api/triage/seed")
    assert response.status_code == 200, response.text
    listed = client.get("/api/tickets", params={"page_size": 1})
    assert listed.status_code == 200
    assert _total(listed.json()) >= 300


# --- listing / filtering / pagination ---------------------------------------
def test_list_pagination_and_filters(client):
    assert client.get("/api/triage/seed").status_code == 200
    response = client.get(
        "/api/tickets",
        params={"category": "Billing", "page": 1, "page_size": 10},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["data"]) <= 10
    assert body["pagination"].get("page", 1) == 1
    assert _total(body) >= 0
    for ticket in body["data"]:
        assert ticket["category"] == "Billing"


def test_list_invalid_filter(client):
    response = client.get("/api/tickets", params={"category": "NotACategory"})
    assert response.status_code == 422, response.text
    assert _error(response)["code"] == "VALIDATION_ERROR"


def test_list_invalid_pagination(client):
    response = client.get("/api/tickets", params={"page": 0, "page_size": 5})
    assert response.status_code == 422, response.text
    assert _error(response)["code"] == "VALIDATION_ERROR"


# --- detail -----------------------------------------------------------------
def test_detail_and_404(client):
    assert client.get("/api/triage/seed").status_code == 200
    found = client.get("/api/tickets/T-0001")
    assert found.status_code == 200, found.text
    missing = client.get("/api/tickets/DOES-NOT-EXIST")
    assert missing.status_code == 404, missing.text
    assert _error(missing)["code"] == "NOT_FOUND"


# --- review queue + submission ----------------------------------------------
def test_review_queue(client):
    assert client.get("/api/triage/seed").status_code == 200
    response = client.get("/api/review-queue", params={"page": 1, "page_size": 5})
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body["data"], list)
    assert "pagination" in body


def test_submit_review(client):
    assert client.get("/api/triage/seed").status_code == 200
    queue = client.get("/api/review-queue", params={"page_size": 5}).json()["data"]
    ticket_id = queue[0].get("id") or queue[0].get("ticket_id")
    response = client.post(
        f"/api/review/{ticket_id}",
        json={"category": "Technical", "priority": "High", "reviewer": "tester"},
    )
    assert response.status_code == 200, response.text
    assert isinstance(response.json(), dict)


def test_submit_review_validation_error(client):
    response = client.post(
        "/api/review/T-0001",
        json={"category": "Bogus", "priority": "High"},
    )
    assert response.status_code == 422, response.text
    assert _error(response)["code"] == "VALIDATION_ERROR"


def test_submit_review_not_found(client):
    response = client.post(
        "/api/review/NO-SUCH-TICKET",
        json={"category": "Billing", "priority": "Low"},
    )
    assert response.status_code == 404, response.text
    assert _error(response)["code"] == "NOT_FOUND"


# --- report -----------------------------------------------------------------
def test_report(client):
    assert client.get("/api/triage/seed").status_code == 200
    response = client.get("/api/report")
    assert response.status_code == 200, response.text
    assert isinstance(response.json(), dict)


# --- repeat review regression ------------------------------------------------
def test_repeat_review_returns_409_conflict(client):
    # Arrange — seed, then pick a ticket that genuinely needs review.
    assert client.get("/api/triage/seed").status_code == 200
    queue = client.get("/api/review-queue", params={"page_size": 5}).json()["data"]
    ticket_id = queue[0].get("id") or queue[0].get("ticket_id")
    payload = {"category": "Technical", "priority": "High", "reviewer": "tester"}

    # Act — first review succeeds, second review of the same ticket is attempted.
    first = client.post(f"/api/review/{ticket_id}", json=payload)
    second = client.post(f"/api/review/{ticket_id}", json=payload)

    # Assert — a ticket can be reviewed only once; the repeat is a conflict.
    assert first.status_code == 200, first.text
    assert second.status_code == 409, second.text
    # A structured error envelope must accompany the conflict.
    assert _error(second)["code"]


# --- single-ticket intake ---------------------------------------------------
def test_create_ticket_generates_id_and_returns_decision(client):
    # Act — create one ticket without supplying an id.
    response = client.post(
        "/api/triage/ticket",
        json={
            "customer": "New Raise",
            "subject": "Invoice copy",
            "body": "Could you send my last invoice for expenses?",
        },
    )
    # Assert — a stable id and a full persisted decision come back.
    assert response.status_code == 200, response.text
    body = response.json()
    assert str(body.get("ticket_id", body.get("id", ""))).startswith("T-")
    assert body.get("status") in {
        "auto_classified",
        "pending_review",
        "human_reviewed",
        "failed",
    }
    assert body.get("category") in {
        "Billing",
        "Technical",
        "Account",
        "Shipping",
        "Other",
        None,
    }


def test_create_ticket_access_loss_forces_review(client):
    response = client.post(
        "/api/triage/ticket",
        json={
            "subject": "My phone was stolen",
            "body": (
                "My phone was stolen and it had my authenticator app. "
                "I can no longer receive login codes and will be locked out "
                "when the session ends."
            ),
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["needs_review"] is True


def test_create_ticket_rejects_empty_text(client):
    response = client.post(
        "/api/triage/ticket",
        json={"subject": "   ", "body": ""},
    )
    assert response.status_code == 422, response.text
    assert _error(response)["code"] == "VALIDATION_ERROR"
