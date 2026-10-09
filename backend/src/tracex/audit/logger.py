"""TRACE-X Audit Logger.
Logs critical actor events (intake, trace, review, decisions, exports) into the append-only audit table.
"""
from datetime import datetime, timezone
import json
import uuid
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

from tracex.repositories.db import AuditEvent


def record_audit_event(
    db: Session,
    actor_user_id: str,
    actor_role: str,
    action: str,
    target_type: str,
    target_id: str,
    case_id: Optional[str] = None,
    request_id: Optional[str] = None,
    reason: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> AuditEvent:
    event = AuditEvent(
        id=f"AUDIT-{uuid.uuid4().hex[:12].upper()}",
        occurred_at=datetime.now(timezone.utc),
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action=action,
        target_type=target_type,
        target_id=target_id,
        case_id=case_id,
        request_id=request_id,
        reason=reason,
        details_json=json.dumps(details or {}, default=str),
    )
    db.add(event)
    db.commit()
    return event
