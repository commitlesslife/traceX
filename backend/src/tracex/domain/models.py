"""TRACE-X Core Domain Models and Enums.
Strictly decoupled from DB/ORM.
"""
from enum import Enum
from decimal import Decimal
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class UserRole(str, Enum):
    ANALYST = "analyst"
    SUPERVISOR = "supervisor"
    ADMIN = "admin"
    AUDITOR = "auditor"


class TransactionStatus(str, Enum):
    COMPLETED = "completed"
    PENDING = "pending"
    REVERSED = "reversed"
    FAILED = "failed"


class TerminationReason(str, Enum):
    NATURAL_END = "natural_end"
    EXTERNAL_INSTITUTION_BOUNDARY = "external_institution_boundary"
    ATM_TERMINAL = "atm_terminal"
    MAX_HOPS_REACHED = "max_hops_reached"
    TIME_HORIZON_EXCEEDED = "time_horizon_exceeded"
    MIN_AMOUNT_THRESHOLD = "min_amount_threshold"
    WORK_BUDGET_EXCEEDED = "work_budget_exceeded"
    UNRESOLVED_LEDGER = "unresolved_ledger"


class RecommendationStatus(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"


class AttributionRuleInfo(BaseModel):
    id: str = "proportional-pooled-inflow"
    name: str = "Proportional Pooled Inflow"
    assumption: str = "Account is treated as a pool; attributed transfers are upper bounds on victim funds."
    version: str = "1.0.0"


class TraceParameters(BaseModel):
    max_hops: int = 6
    horizon_hours: int = 72
    min_amount: Decimal = Decimal("1000.00")
    work_budget_edges: int = 50000


class TraceEdge(BaseModel):
    transaction_id: str
    source_account: str
    destination_account: str
    timestamp_utc: str
    raw_amount: Decimal
    attributed_amount: Decimal
    fraction: Decimal
    confidence: Decimal
    hop: int
    channel: str = "IMPS"
    is_terminal: bool = False
    evidence_id: str


class TraceNode(BaseModel):
    account_id: str
    pseudonymous_key: str
    institution_id: str
    is_operating_institution: bool
    traced_in: Decimal
    traced_out: Decimal
    unmoved_traced_value: Decimal
    available_balance: Optional[Decimal] = None
    balance_status: str = "unknown"  # "known" or "unknown"
    freezable_estimate: Optional[Decimal] = None
    confidence: Decimal
    min_hop: int
    is_terminal: bool = False
    termination_reason: Optional[TerminationReason] = None
    evidence_ids: List[str] = Field(default_factory=list)


class TraceBoundary(BaseModel):
    boundary_account: str
    institution_name: str
    institution_code: str
    crossed_amount: Decimal
    last_transaction_id: str
    timestamp_utc: str
    reason: str = "Crossed operating institution boundary into external entity"


class TraceResult(BaseModel):
    trace_id: str
    case_id: str
    dataset_id: str
    dataset_checksum: str
    engine_version: str = "1.0.0"
    attribution_rule: AttributionRuleInfo = Field(default_factory=AttributionRuleInfo)
    parameters: TraceParameters
    seed_transaction_id: str
    seed_amount: Decimal
    victim_account: str
    nodes: List[TraceNode]
    edges: List[TraceEdge]
    boundaries: List[TraceBoundary]
    stopping_reasons: List[Dict[str, Any]]
    complete: bool
    crossed_boundary_value: Decimal
    total_unmoved_value: Decimal
    result_hash: str
    is_synthetic: bool = True
