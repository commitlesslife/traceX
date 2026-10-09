"""Integration test for TRACE-X end-to-end API workflow.
Tests:
  1. Login as Analyst
  2. Load Complaints
  3. Run Proportional Trace (checking conservation and values)
  4. Analyst submits Recommendation Draft
  5. Analyst attempts to self-approve -> MUST BE REJECTED (403 Separation of Duties)
  6. Login as Supervisor
  7. Supervisor approves recommendation with reason
  8. Fetch approved document
  9. Export JSON case pack with content hash
"""
import pytest
from decimal import Decimal
from fastapi.testclient import TestClient
import json

from tracex.main import app
from tracex.seed_demo import seed_database

client = TestClient(app)


def test_end_to_end_mvp_workflow():
    # 0. Seed database to clean golden state
    seed_database()

    # 1. Login as Analyst Priya
    resp_login_analyst = client.post(
        "/api/v1/auth/login",
        data={"username": "analyst_priya", "password": "analyst123"}
    )
    assert resp_login_analyst.status_code == 200
    analyst_token = resp_login_analyst.json()["access_token"]
    analyst_headers = {"Authorization": f"Bearer {analyst_token}"}

    # 2. Get complaints queue
    resp_complaints = client.get("/api/v1/complaints", headers=analyst_headers)
    assert resp_complaints.status_code == 200
    complaints = resp_complaints.json()["complaints"]
    assert len(complaints) > 0
    complaint_id = complaints[0]["id"]

    # 3. Run Trace
    resp_trace = client.post(
        f"/api/v1/complaints/{complaint_id}/traces",
        headers=analyst_headers,
        json={"max_hops": 6, "horizon_hours": 72, "min_amount": "100.00"}
    )
    assert resp_trace.status_code == 200
    trace_data = resp_trace.json()
    trace_id = trace_data["trace_id"]
    assert trace_data["complete"] is True
    assert Decimal(str(trace_data["seed_amount"])) == Decimal("100000.00")

    # Verify money conservation: total_unmoved + crossed_boundary == seed_amount
    total_unmoved = Decimal(str(trace_data["total_unmoved_value"]))
    crossed_boundary = Decimal(str(trace_data["crossed_boundary_value"]))
    assert total_unmoved + crossed_boundary == Decimal("100000.00")

    # 4. Analyst drafts recommendation for Account A (freezable estimate is 44800.00 after 3 outgoing transfers)
    resp_draft = client.post(
        "/api/v1/cases/CASE-2026-0891/recommendations",
        headers=analyst_headers,
        json={
            "trace_id": trace_id,
            "selected_accounts": [
                {"account_id": "ACC-A-101", "amount": "44800.00", "basis": "freezable_estimate"}
            ],
            "justification": "Victim funds retained at Mule A after downstream transfers"
        }
    )
    assert resp_draft.status_code == 200
    rec_id = resp_draft.json()["recommendation_id"]

    # 5. Analyst attempts to self-approve -> MUST FAIL (403 Forbidden)
    resp_self_approve = client.post(
        f"/api/v1/recommendations/{rec_id}/decision",
        headers=analyst_headers,
        json={"decision": "approved", "reason": "Self approving my own recommendation"}
    )
    # Blocked by role check (analyst cannot call decision) or self-approval check
    assert resp_self_approve.status_code == 403

    # 6. Login as Supervisor Rajesh
    resp_login_sup = client.post(
        "/api/v1/auth/login",
        data={"username": "supervisor_rajesh", "password": "supervisor123"}
    )
    assert resp_login_sup.status_code == 200
    sup_token = resp_login_sup.json()["access_token"]
    sup_headers = {"Authorization": f"Bearer {sup_token}"}

    # 7. Supervisor approves recommendation
    resp_approve = client.post(
        f"/api/v1/recommendations/{rec_id}/decision",
        headers=sup_headers,
        json={
            "decision": "approved",
            "reason": "Verified against ledger timestamps and attribution fractions. Approved."
        }
    )
    assert resp_approve.status_code == 200
    assert resp_approve.json()["status"] == "approved"
    assert resp_approve.json()["document_hash"] is not None

    # 8. Fetch generated approved document
    resp_doc = client.get(f"/api/v1/recommendations/{rec_id}/document", headers=sup_headers)
    assert resp_doc.status_code == 200
    doc_data = resp_doc.json()
    assert doc_data["recommendation_id"] == rec_id
    assert "No direct banking or freeze action" in doc_data["notice"]

    # 9. Export Case Pack
    resp_export = client.post("/api/v1/cases/CASE-2026-0891/exports", headers=sup_headers)
    assert resp_export.status_code == 200
    export_json = resp_export.json()
    assert "content_hash" in export_json["export_metadata"]
    assert export_json["recommendation"]["status"] == "approved"
    print("\n[SUCCESS] TRACE-X Complete MVP Vertical Slice Verified End-to-End!")


if __name__ == "__main__":
    test_end_to_end_mvp_workflow()
