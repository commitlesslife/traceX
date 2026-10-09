"""TRACE-X API v1 Endpoints.
Covers:
  - Auth (/auth/login, /auth/me)
  - Complaints (/complaints, /complaints/{id})
  - Traces (/complaints/{id}/traces, /traces/{id})
  - Accounts (/accounts/{id})
  - Transactions (/transactions/{id})
  - Recommendations (/cases/{id}/recommendations, /recommendations, /recommendations/{id}/decision, /recommendations/{id}/document)
  - Exports (/cases/{id}/exports)
  - Audit (/audit)
  - Demo Reset (/demo/reset)
"""
from decimal import Decimal
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import json
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from tracex.repositories.db import (
    SessionLocal,
    Complaint,
    Case,
    StoredTraceRun,
    RecommendationDraft,
    AuditEvent,
    User,
    Account,
    Transaction,
    Institution,
)
from tracex.auth.security import (
    get_db,
    get_current_user,
    require_role,
    verify_password,
    create_access_token,
)
from tracex.domain.models import (
    UserRole,
    TraceParameters,
    TraceResult,
)
from tracex.services.app_service import (
    create_complaint_and_case,
    execute_trace_for_complaint,
    draft_recommendation,
    decide_recommendation,
)
from tracex.exports.case_pack import generate_case_export
from tracex.seed_demo import seed_database

router = APIRouter()


# --- Pydantic Schemas for API ---

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    username: str
    role: str
    display_name: str


class ComplaintCreateRequest(BaseModel):
    victim_account: str
    disputed_transaction_ref: str
    disputed_amount: Decimal
    channel: str = "CYBER_CRIME_NCRP"


class RecommendationCreateRequest(BaseModel):
    trace_id: str
    selected_accounts: List[Dict[str, Any]]
    justification: str


class RecommendationDecisionRequest(BaseModel):
    decision: str  # "approved" or "rejected"
    reason: str


# --- 1. Auth Endpoints ---

@router.post("/auth/login", response_model=LoginResponse, tags=["Authentication"])
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(data={"sub": user.username, "role": user.role})
    return LoginResponse(
        access_token=token,
        user_id=user.id,
        username=user.username,
        role=user.role,
        display_name=user.display_name,
    )


@router.get("/auth/me", tags=["Authentication"])
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "role": current_user.role,
        "display_name": current_user.display_name,
    }


# --- 2. Complaints & Queue ---

@router.get("/complaints", tags=["Complaints"])
def list_complaints(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    complaints = db.query(Complaint).order_by(Complaint.reported_time.desc()).all()
    results = []
    now = datetime.now(timezone.utc)
    for c in complaints:
        rep_time = c.reported_time
        if rep_time and rep_time.tzinfo is None:
            rep_time = rep_time.replace(tzinfo=timezone.utc)
        elapsed = (now - rep_time).total_seconds() if rep_time else 0
        results.append({
            "id": c.id,
            "victim_account": c.victim_account,
            "disputed_transaction_ref": c.disputed_transaction_ref,
            "disputed_amount": str(c.disputed_amount),
            "reported_time": rep_time.isoformat() if rep_time else None,
            "elapsed_seconds": int(elapsed),
            "channel": c.channel,
            "match_status": c.match_status,
            "matched_transaction_id": c.matched_transaction_id,
        })
    return {"complaints": results, "server_as_of": now.isoformat()}


@router.get("/cases", tags=["Cases"])
def list_cases(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Return case summaries for the investigation workspace."""
    rows = db.query(Case, Complaint).join(Complaint, Complaint.id == Case.complaint_id).order_by(Case.created_at.desc()).all()
    cases = []
    for case, complaint in rows:
        latest_trace = db.query(StoredTraceRun).filter(StoredTraceRun.case_id == case.id).order_by(StoredTraceRun.created_at.desc()).first()
        cases.append({
            "case_id": case.id,
            "complaint_id": complaint.id,
            "status": case.status,
            "disposition": case.disposition,
            "created_at": case.created_at.isoformat() if case.created_at else None,
            "victim_account": complaint.victim_account,
            "disputed_transaction_ref": complaint.disputed_transaction_ref,
            "disputed_amount": str(complaint.disputed_amount),
            "reported_time": complaint.reported_time.isoformat() if complaint.reported_time else None,
            "match_status": complaint.match_status,
            "latest_trace_id": latest_trace.id if latest_trace else None,
        })
    return {"cases": cases}


@router.get("/cases/{id}", tags=["Cases"])
def get_case(id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    case = db.query(Case).filter(Case.id == id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    complaint = db.query(Complaint).filter(Complaint.id == case.complaint_id).first()
    latest_trace = db.query(StoredTraceRun).filter(StoredTraceRun.case_id == id).order_by(StoredTraceRun.created_at.desc()).first()
    recommendations = db.query(RecommendationDraft).filter(RecommendationDraft.case_id == id).order_by(RecommendationDraft.created_at.desc()).all()
    return {
        "case_id": case.id,
        "complaint_id": complaint.id if complaint else None,
        "status": case.status,
        "disposition": case.disposition,
        "created_at": case.created_at.isoformat() if case.created_at else None,
        "complaint": {
            "id": complaint.id,
            "victim_account": complaint.victim_account,
            "disputed_transaction_ref": complaint.disputed_transaction_ref,
            "disputed_amount": str(complaint.disputed_amount),
            "reported_time": complaint.reported_time.isoformat() if complaint.reported_time else None,
            "channel": complaint.channel,
            "match_status": complaint.match_status,
            "matched_transaction_id": complaint.matched_transaction_id,
        } if complaint else None,
        "latest_trace_id": latest_trace.id if latest_trace else None,
        "recommendation_ids": [r.id for r in recommendations],
    }


@router.get("/transactions/{id}", tags=["Evidence & Inspection"])
def get_transaction(id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    tx = db.query(Transaction).filter(Transaction.transaction_id == id).first()
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    src = db.query(Account).filter(Account.id == tx.source_account_id).first()
    dst = db.query(Account).filter(Account.id == tx.destination_account_id).first()
    return {
        "transaction_id": tx.transaction_id,
        "amount": str(tx.amount),
        "currency": tx.currency,
        "timestamp_utc": tx.timestamp_utc.isoformat(),
        "channel": tx.channel,
        "status": tx.status,
        "source_account_id": tx.source_account_id,
        "source_key": src.pseudonymous_key if src else tx.source_account_id,
        "destination_account_id": tx.destination_account_id,
        "destination_key": dst.pseudonymous_key if dst else tx.destination_account_id,
        "source_institution_id": tx.source_institution_id,
        "destination_institution_id": tx.destination_institution_id,
        "dataset_id": tx.dataset_id,
    }


@router.post("/complaints", tags=["Complaints"])
def intake_complaint(
    req: ComplaintCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ANALYST, UserRole.ADMIN])),
):
    return create_complaint_and_case(
        db=db,
        victim_account=req.victim_account,
        disputed_transaction_ref=req.disputed_transaction_ref,
        disputed_amount=req.disputed_amount,
        channel=req.channel,
        actor=current_user,
    )


@router.get("/complaints/{id}", tags=["Complaints"])
def get_complaint(id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    complaint = db.query(Complaint).filter(Complaint.id == id).first()
    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found")
    case = db.query(Case).filter(Case.complaint_id == id).first()
    return {
        "complaint": {
            "id": complaint.id,
            "victim_account": complaint.victim_account,
            "disputed_transaction_ref": complaint.disputed_transaction_ref,
            "disputed_amount": str(complaint.disputed_amount),
            "reported_time": complaint.reported_time.isoformat() if complaint.reported_time else None,
            "channel": complaint.channel,
            "match_status": complaint.match_status,
            "matched_transaction_id": complaint.matched_transaction_id,
        },
        "case_id": case.id if case else None,
    }


# --- 3. Traces ---

@router.post("/complaints/{id}/traces", response_model=TraceResult, tags=["Tracing"])
def run_trace(
    id: str,
    parameters: Optional[TraceParameters] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ANALYST, UserRole.SUPERVISOR, UserRole.ADMIN])),
):
    params = parameters or TraceParameters()
    return execute_trace_for_complaint(
        db=db,
        complaint_id=id,
        parameters=params,
        actor=current_user,
    )


@router.get("/traces/{id}", tags=["Tracing"])
def get_stored_trace(id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    trace_run = db.query(StoredTraceRun).filter(StoredTraceRun.id == id).first()
    if not trace_run:
        raise HTTPException(status_code=404, detail="Trace run not found")
    return json.loads(trace_run.result_json)


# --- 4. Accounts & Transactions Inspection ---

@router.get("/accounts/{id}", tags=["Evidence & Inspection"])
def get_account_detail(id: str, trace_id: Optional[str] = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    acc = db.query(Account).filter(Account.id == id).first()
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")
    inst = db.query(Institution).filter(Institution.id == acc.institution_id).first()
    
    # Check trace context if provided
    trace_context = None
    if trace_id:
        trace_run = db.query(StoredTraceRun).filter(StoredTraceRun.id == trace_id).first()
        if trace_run:
            t_data = json.loads(trace_run.result_json)
            for n in t_data.get("nodes", []):
                if n["account_id"] == id:
                    trace_context = n
                    break

    recent_txs = db.query(Transaction).filter(
        (Transaction.source_account_id == id) | (Transaction.destination_account_id == id)
    ).order_by(Transaction.timestamp_utc.desc()).limit(10).all()

    return {
        "account_id": acc.id,
        "pseudonymous_key": acc.pseudonymous_key,
        "institution": {
            "id": inst.id if inst else None,
            "code": inst.code if inst else None,
            "name": inst.name if inst else None,
            "is_operating_institution": inst.is_operating_institution if inst else True,
        },
        "history_complete": acc.history_complete,
        "opening_balance": str(acc.opening_balance) if acc.opening_balance is not None else None,
        "trace_context": trace_context,
        "recent_transactions": [
            {
                "transaction_id": tx.transaction_id,
                "amount": str(tx.amount),
                "timestamp_utc": tx.timestamp_utc.isoformat(),
                "channel": tx.channel,
                "status": tx.status,
                "direction": "outflow" if tx.source_account_id == id else "inflow",
            }
            for tx in recent_txs
        ]
    }


# --- 5. Recommendations & Independent Review ---

@router.post("/cases/{id}/recommendations", tags=["Recommendations"])
def draft_rec(
    id: str,
    req: RecommendationCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ANALYST])),
):
    draft = draft_recommendation(
        db=db,
        case_id=id,
        trace_id=req.trace_id,
        selected_accounts=req.selected_accounts,
        justification=req.justification,
        author=current_user,
    )
    return {
        "recommendation_id": draft.id,
        "case_id": draft.case_id,
        "status": draft.status,
        "total_amount": str(draft.total_recommended_amount),
        "author_id": draft.author_id,
    }


@router.get("/recommendations", tags=["Recommendations"])
def list_recommendations(status_filter: Optional[str] = "draft", db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    query = db.query(RecommendationDraft)
    if status_filter:
        query = query.filter(RecommendationDraft.status == status_filter)
    drafts = query.order_by(RecommendationDraft.created_at.desc()).all()
    results = []
    for d in drafts:
        results.append({
            "id": d.id,
            "case_id": d.case_id,
            "trace_id": d.trace_id,
            "total_recommended_amount": str(d.total_recommended_amount),
            "status": d.status,
            "justification": d.justification,
            "author_id": d.author_id,
            "selected_accounts": json.loads(d.selected_accounts_json),
            "decided_by_id": d.decided_by_id,
            "decision_reason": d.decision_reason,
            "decided_at": d.decided_at.isoformat() if d.decided_at else None,
            "document_hash": d.document_hash,
        })
    return {"recommendations": results}


@router.post("/recommendations/{id}/decision", tags=["Recommendations"])
def decide_rec(
    id: str,
    req: RecommendationDecisionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPERVISOR])),
):
    draft = decide_recommendation(
        db=db,
        recommendation_id=id,
        decision=req.decision,
        reason=req.reason,
        supervisor=current_user,
    )
    return {
        "id": draft.id,
        "status": draft.status,
        "decided_by": current_user.display_name,
        "decision_reason": draft.decision_reason,
        "document_hash": draft.document_hash,
    }


@router.get("/recommendations/{id}/document", tags=["Recommendations"])
def get_recommendation_document(id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    draft = db.query(RecommendationDraft).filter(RecommendationDraft.id == id).first()
    if not draft:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    if draft.status != "approved":
        raise HTTPException(
            status_code=400,
            detail=f"Recommendation document is only accessible after independent supervisor approval. Current status: '{draft.status}'"
        )
    return {
        "document_id": f"DOC-{draft.id}",
        "recommendation_id": draft.id,
        "case_id": draft.case_id,
        "document_hash": draft.document_hash,
        "total_approved_amount": str(draft.total_recommended_amount),
        "justification": draft.justification,
        "supervisor_reason": draft.decision_reason,
        "approved_at": draft.decided_at.isoformat() if draft.decided_at else None,
        "notice": "Exportable recommendation document only. No direct banking or freeze action is executed."
    }


# --- 6. Case Export & Audit ---

@router.post("/cases/{id}/exports", tags=["Export & Audit"])
def export_case_pack(id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return generate_case_export(db=db, case_id=id, exporter=current_user)


@router.get("/audit", tags=["Export & Audit"])
def list_audit_events(limit: int = 50, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    events = db.query(AuditEvent).order_by(AuditEvent.occurred_at.desc()).limit(limit).all()
    return {
        "audit_events": [
            {
                "id": e.id,
                "occurred_at": e.occurred_at.isoformat() if e.occurred_at else None,
                "actor_user_id": e.actor_user_id,
                "actor_role": e.actor_role,
                "action": e.action,
                "target_type": e.target_type,
                "target_id": e.target_id,
                "case_id": e.case_id,
                "reason": e.reason,
                "details": json.loads(e.details_json) if e.details_json else {},
            }
            for e in events
        ]
    }


# --- 7. Deterministic Demo Reset ---

@router.post("/demo/reset", tags=["Demo Management"])
def reset_demo(db: Session = Depends(get_db), current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.SUPERVISOR]))):
    seed_database()
    return {"status": "ok", "message": "Demo fixture, accounts, and users successfully reset to golden state."}
