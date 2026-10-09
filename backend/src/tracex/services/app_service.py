"""TRACE-X Application Services.
Orchestrates use cases:
  1. Complaint intake & exact seed transaction match resolution.
  2. Forward trace execution, persistence, and lookup.
  3. Recommendation drafting with upper-bound validation.
  4. Second-person supervisor review & approval.
"""
from datetime import datetime, timezone
from decimal import Decimal
import json
import uuid
import hashlib
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from tracex.repositories.db import (
    Complaint,
    Case,
    Transaction,
    Account,
    Institution,
    StoredTraceRun,
    RecommendationDraft,
    User,
)
from tracex.domain.models import (
    TraceParameters,
    TraceResult,
    UserRole,
)
from tracex.engine.trace_engine import (
    run_pure_trace,
    EngineAccount,
    EngineTransaction,
)
from tracex.audit.logger import record_audit_event


def create_complaint_and_case(
    db: Session,
    victim_account: str,
    disputed_transaction_ref: str,
    disputed_amount: Decimal,
    channel: str,
    actor: User,
) -> Dict[str, Any]:
    # 1. Exact match resolution against ledger
    tx = db.query(Transaction).filter(
        Transaction.transaction_id == disputed_transaction_ref
    ).first()

    match_status = "matched" if tx is not None else "unresolved"
    matched_tx_id = tx.transaction_id if tx else None

    complaint_id = f"CMP-{uuid.uuid4().hex[:8].upper()}"
    complaint = Complaint(
        id=complaint_id,
        victim_account=victim_account,
        disputed_transaction_ref=disputed_transaction_ref,
        disputed_amount=disputed_amount,
        reported_time=datetime.now(timezone.utc),
        channel=channel,
        match_status=match_status,
        matched_transaction_id=matched_tx_id,
        assigned_analyst_id=actor.id,
    )
    db.add(complaint)

    case_id = f"CASE-{uuid.uuid4().hex[:8].upper()}"
    case = Case(
        id=case_id,
        complaint_id=complaint_id,
        status="open",
        disposition="under_investigation",
    )
    db.add(case)
    db.commit()

    record_audit_event(
        db=db,
        actor_user_id=actor.id,
        actor_role=actor.role,
        action="COMPLAINT_INTAKE",
        target_type="complaint",
        target_id=complaint.id,
        case_id=case.id,
        details={
            "disputed_ref": disputed_transaction_ref,
            "match_status": match_status,
            "amount": str(disputed_amount),
        },
    )

    return {
        "complaint_id": complaint.id,
        "case_id": case.id,
        "match_status": match_status,
        "matched_transaction_id": matched_tx_id,
    }


def execute_trace_for_complaint(
    db: Session,
    complaint_id: str,
    parameters: TraceParameters,
    actor: User,
) -> TraceResult:
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found")

    if complaint.match_status != "matched" or not complaint.matched_transaction_id:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot trace complaint: transaction reference '{complaint.disputed_transaction_ref}' is unresolved.",
        )

    case = db.query(Case).filter(Case.complaint_id == complaint_id).first()
    case_id = case.id if case else "UNKNOWN_CASE"

    # Fetch seed transaction
    seed_tx = db.query(Transaction).filter(
        Transaction.transaction_id == complaint.matched_transaction_id
    ).first()
    if not seed_tx:
        raise HTTPException(status_code=404, detail="Seed transaction not found in ledger")

    # Load in-memory accounts and transactions for engine
    all_acc_rows = db.query(Account).all()
    inst_rows = {i.id: i for i in db.query(Institution).all()}
    all_tx_rows = db.query(Transaction).all()

    engine_accounts: Dict[str, EngineAccount] = {}
    for a in all_acc_rows:
        inst = inst_rows.get(a.institution_id)
        is_op = inst.is_operating_institution if inst else True
        
        # FR-48: Compute available balance only when history_complete is True
        avail_bal = None
        if a.history_complete and a.opening_balance is not None:
            # sum all credits and debits up to now
            credits = sum((t.amount for t in all_tx_rows if t.destination_account_id == a.id and t.status == "completed"), Decimal("0.00"))
            debits = sum((t.amount for t in all_tx_rows if t.source_account_id == a.id and t.status == "completed"), Decimal("0.00"))
            avail_bal = a.opening_balance + credits - debits

        engine_accounts[a.id] = EngineAccount(
            account_id=a.id,
            pseudonymous_key=a.pseudonymous_key,
            institution_id=a.institution_id,
            is_operating_institution=is_op,
            available_balance=avail_bal,
            history_complete=a.history_complete,
        )

    all_tx_rows = db.query(Transaction).all()
    engine_txs: List[EngineTransaction] = []
    for t in all_tx_rows:
        dest_inst = inst_rows.get(t.destination_institution_id)
        is_dest_ext = not dest_inst.is_operating_institution if dest_inst else False
        dest_inst_name = dest_inst.name if dest_inst else "Unknown Bank"
        dest_inst_code = dest_inst.code if dest_inst else "EXT"

        tx_time = t.timestamp_utc
        if tx_time and tx_time.tzinfo is None:
            tx_time = tx_time.replace(tzinfo=timezone.utc)

        engine_txs.append(EngineTransaction(
            transaction_id=t.transaction_id,
            source_account=t.source_account_id,
            destination_account=t.destination_account_id,
            amount=t.amount,
            timestamp_utc=tx_time,
            timestamp_str=tx_time.isoformat(),
            status=t.status,
            channel=t.channel,
            dest_is_external=is_dest_ext,
            dest_institution_code=dest_inst_code,
            dest_institution_name=dest_inst_name,
        ))

    seed_time = seed_tx.timestamp_utc
    if seed_time and seed_time.tzinfo is None:
        seed_time = seed_time.replace(tzinfo=timezone.utc)

    # Execute pure engine
    trace_result = run_pure_trace(
        seed_transaction_id=seed_tx.transaction_id,
        victim_account=seed_tx.source_account_id,
        first_recipient_account=seed_tx.destination_account_id,
        seed_amount=seed_tx.amount,
        seed_timestamp_utc=seed_time,
        parameters=parameters,
        all_transactions=engine_txs,
        accounts_metadata=engine_accounts,
        case_id=case_id,
        dataset_id=seed_tx.dataset_id,
    )

    # Persist immutable trace run
    stored_run = StoredTraceRun(
        id=trace_result.trace_id,
        case_id=case_id,
        seed_transaction_id=seed_tx.transaction_id,
        parameters_json=json.dumps(parameters.model_dump(mode="json")),
        result_json=json.dumps(trace_result.model_dump(mode="json"), default=str),
        result_hash=trace_result.result_hash,
        dataset_checksum=trace_result.dataset_checksum,
        created_at=datetime.now(timezone.utc),
    )
    db.add(stored_run)
    db.commit()

    record_audit_event(
        db=db,
        actor_user_id=actor.id,
        actor_role=actor.role,
        action="TRACE_EXECUTION",
        target_type="trace_run",
        target_id=trace_result.trace_id,
        case_id=case_id,
        details={
            "result_hash": trace_result.result_hash,
            "total_unmoved": str(trace_result.total_unmoved_value),
            "crossed_boundary": str(trace_result.crossed_boundary_value),
        },
    )

    return trace_result


def draft_recommendation(
    db: Session,
    case_id: str,
    trace_id: str,
    selected_accounts: List[Dict[str, Any]],
    justification: str,
    author: User,
) -> RecommendationDraft:
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    trace_run = db.query(StoredTraceRun).filter(StoredTraceRun.id == trace_id).first()
    if not trace_run:
        raise HTTPException(status_code=404, detail="Trace run not found")

    trace_data = json.loads(trace_run.result_json)
    nodes_by_acc = {n["account_id"]: n for n in trace_data.get("nodes", [])}

    # Validate accounts and amounts
    total_amount = Decimal("0.00")
    for item in selected_accounts:
        acc_id = item.get("account_id")
        req_amt = Decimal(str(item.get("amount", "0")))
        if acc_id not in nodes_by_acc:
            raise HTTPException(
                status_code=400,
                detail=f"Account {acc_id} is not part of trace {trace_id}"
            )
        
        node = nodes_by_acc[acc_id]
        unmoved_cap = Decimal(str(node["unmoved_traced_value"]))
        
        # If balance is known, enforce freezable_estimate cap
        if node.get("balance_status") == "known" and node.get("freezable_estimate") is not None:
            max_allowed = Decimal(str(node["freezable_estimate"]))
            if req_amt > max_allowed:
                raise HTTPException(
                    status_code=400,
                    detail=f"Requested amount ₹{req_amt} exceeds supported freezable estimate ₹{max_allowed} for account {acc_id}"
                )
        else:
            # Balance unknown: cannot exceed unmoved upper bound
            if req_amt > unmoved_cap:
                raise HTTPException(
                    status_code=400,
                    detail=f"Requested amount ₹{req_amt} exceeds unmoved traced value cap ₹{unmoved_cap} for account {acc_id}"
                )
        total_amount += req_amt

    draft_id = f"REC-{uuid.uuid4().hex[:8].upper()}"
    draft = RecommendationDraft(
        id=draft_id,
        case_id=case_id,
        trace_id=trace_id,
        trace_result_hash=trace_run.result_hash,
        selected_accounts_json=json.dumps(selected_accounts, default=str),
        total_recommended_amount=total_amount,
        justification=justification,
        author_id=author.id,
        status="draft",
    )
    db.add(draft)
    db.commit()

    record_audit_event(
        db=db,
        actor_user_id=author.id,
        actor_role=author.role,
        action="RECOMMENDATION_DRAFTED",
        target_type="recommendation_draft",
        target_id=draft.id,
        case_id=case_id,
        reason=justification,
        details={"total_amount": str(total_amount)},
    )
    return draft


def decide_recommendation(
    db: Session,
    recommendation_id: str,
    decision: str,  # "approved" or "rejected"
    reason: str,
    supervisor: User,
) -> RecommendationDraft:
    draft = db.query(RecommendationDraft).filter(RecommendationDraft.id == recommendation_id).first()
    if not draft:
        raise HTTPException(status_code=404, detail="Recommendation draft not found")

    if draft.status != "draft":
        raise HTTPException(status_code=400, detail=f"Recommendation is already {draft.status}")

    # Enforce separation of duties: author cannot approve own draft
    if draft.author_id == supervisor.id:
        raise HTTPException(
            status_code=403,
            detail="Separation of Duty Violation: The author of a recommendation cannot approve or reject it. A distinct supervisor is required."
        )

    if decision not in ["approved", "rejected"]:
        raise HTTPException(status_code=400, detail="Decision must be 'approved' or 'rejected'")

    # Calculate document hash upon approval
    doc_hash = None
    if decision == "approved":
        doc_bytes = f"{draft.id}:{draft.total_recommended_amount}:{supervisor.id}:{datetime.now(timezone.utc).isoformat()}".encode("utf-8")
        doc_hash = hashlib.sha256(doc_bytes).hexdigest()

    draft.status = decision
    draft.decided_by_id = supervisor.id
    draft.decision_reason = reason
    draft.decided_at = datetime.now(timezone.utc)
    draft.document_hash = doc_hash
    db.commit()

    record_audit_event(
        db=db,
        actor_user_id=supervisor.id,
        actor_role=supervisor.role,
        action=f"RECOMMENDATION_{decision.upper()}",
        target_type="recommendation_draft",
        target_id=draft.id,
        case_id=draft.case_id,
        reason=reason,
        details={"decision": decision, "document_hash": doc_hash},
    )
    return draft
