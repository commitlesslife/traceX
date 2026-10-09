"""Pure TRACE-X Tracing Engine.
Zero imports from DB, ORM, API, Celery, or external network.
Implements proportional-pooled-inflow with shared sibling budgets,
causality ordering, paise-safe Decimal math, and institutional boundaries.
"""
from decimal import Decimal, ROUND_FLOOR
from typing import Dict, List, Optional, Tuple, Set, Any
from datetime import datetime, timezone, timedelta
import hashlib
import json
import uuid

from tracex.domain.models import (
    TraceParameters,
    TraceResult,
    TraceNode,
    TraceEdge,
    TraceBoundary,
    TerminationReason,
    AttributionRuleInfo,
)


def floor_to_paise(amount: Decimal) -> Decimal:
    """Rounds down to two decimal places (paise) to preserve exact conservation."""
    return amount.quantize(Decimal("0.01"), rounding=ROUND_FLOOR)


def attribute(
    edge_amount: Decimal, remaining: Decimal, pool_inflow: Decimal
) -> Tuple[Decimal, Decimal]:
    """Pure proportional pooled inflow attribution calculation.
    
    Formula:
      fraction = min(1.0, remaining / pool_inflow)
      attributed = min(remaining, edge_amount * fraction)
    """
    if pool_inflow <= Decimal("0") or remaining <= Decimal("0"):
        return Decimal("0.00"), Decimal("0")
    
    fraction = min(Decimal("1"), remaining / pool_inflow)
    attributed = min(remaining, edge_amount * fraction)
    return floor_to_paise(attributed), fraction


def parse_iso_utc(ts_str: str) -> datetime:
    """Safely parse ISO string with offset or Z into UTC datetime."""
    clean = ts_str.replace("Z", "+00:00")
    dt = datetime.fromisoformat(clean)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class EngineAccount:
    """Internal lightweight structure for account state in memory during trace."""
    def __init__(
        self,
        account_id: str,
        pseudonymous_key: str,
        institution_id: str,
        is_operating_institution: bool,
        available_balance: Optional[Decimal] = None,
        history_complete: bool = False,
    ):
        self.account_id = account_id
        self.pseudonymous_key = pseudonymous_key
        self.institution_id = institution_id
        self.is_operating_institution = is_operating_institution
        self.available_balance = available_balance
        self.history_complete = history_complete


class EngineTransaction:
    """Internal lightweight transaction item."""
    def __init__(
        self,
        transaction_id: str,
        source_account: str,
        destination_account: str,
        amount: Decimal,
        timestamp_utc: datetime,
        timestamp_str: str,
        status: str,
        channel: str,
        dest_is_external: bool = False,
        dest_institution_code: str = "SELF",
        dest_institution_name: str = "Operating Institution",
    ):
        self.transaction_id = transaction_id
        self.source_account = source_account
        self.destination_account = destination_account
        self.amount = amount
        self.timestamp_utc = timestamp_utc
        self.timestamp_str = timestamp_str
        self.status = status
        self.channel = channel
        self.dest_is_external = dest_is_external
        self.dest_institution_code = dest_institution_code
        self.dest_institution_name = dest_institution_name


def run_pure_trace(
    seed_transaction_id: str,
    victim_account: str,
    first_recipient_account: str,
    seed_amount: Decimal,
    seed_timestamp_utc: datetime,
    parameters: TraceParameters,
    all_transactions: List[EngineTransaction],
    accounts_metadata: Dict[str, EngineAccount],
    case_id: str = "CASE-DEMO-001",
    dataset_id: str = "DATASET-GOLDEN-001",
    dataset_checksum: str = "sha256-golden-fixture",
) -> TraceResult:
    """Executes a pure, deterministic forward trace.
    
    Invariants enforced:
      1. Causality: credits must arrive at or before outgoing debit.
      2. Shared sibling budget: parent remaining pool budget decreases as transfers occur.
      3. No money amplification: total unmoved + crossed <= seed_amount.
      4. Paise rounding: residue stays with parent unmoved budget.
      5. Confidence decay: confidence = parent_confidence * fraction, strictly <= 1.0.
      6. Hard bounds: max hops, time horizon, min amount, work budget.
      7. Institutional boundary: transfers out of operating institution terminate.
    """
    trace_id = f"TRACE-{uuid.uuid4().hex[:8].upper()}"
    horizon_limit = seed_timestamp_utc + timedelta(hours=parameters.horizon_hours)

    # Node tracking: account_id -> dict of totals and lineage
    nodes_state: Dict[str, Dict[str, Any]] = {}
    
    # Initialize first recipient
    nodes_state[first_recipient_account] = {
        "traced_in": seed_amount,
        "traced_out": Decimal("0.00"),
        "confidence": Decimal("1.00"),
        "min_hop": 1,
        "is_terminal": False,
        "termination_reason": None,
        "evidence_ids": [seed_transaction_id],
        "arrival_times": [seed_timestamp_utc],
    }

    # Edges, boundaries, stopping reasons
    recorded_edges: List[TraceEdge] = []
    recorded_boundaries: List[TraceBoundary] = []
    stopping_reasons: List[Dict[str, Any]] = []
    
    edges_examined = 0
    work_budget_reached = False
    
    # Active frontier of accounts to process
    # Each frontier entry: (account_id, current_hop, incoming_confidence)
    frontier: List[Tuple[str, int, Decimal]] = [(first_recipient_account, 1, Decimal("1.00"))]
    visited_accounts: Set[str] = set()

    while frontier and not work_budget_reached:
        current_account_id, current_hop, parent_conf = frontier.pop(0)
        
        # Check max hops bound
        if current_hop > parameters.max_hops:
            stopping_reasons.append({
                "account_id": current_account_id,
                "reason": TerminationReason.MAX_HOPS_REACHED.value,
                "detail": f"Reached max configured hops ({parameters.max_hops})"
            })
            nodes_state[current_account_id]["is_terminal"] = True
            nodes_state[current_account_id]["termination_reason"] = TerminationReason.MAX_HOPS_REACHED
            continue

        acc_state = nodes_state[current_account_id]
        acc_meta = accounts_metadata.get(current_account_id)
        
        # If this account itself is an external institution, boundary terminal reached
        if acc_meta and not acc_meta.is_operating_institution:
            nodes_state[current_account_id]["is_terminal"] = True
            nodes_state[current_account_id]["termination_reason"] = TerminationReason.EXTERNAL_INSTITUTION_BOUNDARY
            continue

        # Remaining budget for this account
        remaining_budget = acc_state["traced_in"] - acc_state["traced_out"]
        if remaining_budget < parameters.min_amount:
            if remaining_budget > Decimal("0"):
                stopping_reasons.append({
                    "account_id": current_account_id,
                    "reason": TerminationReason.MIN_AMOUNT_THRESHOLD.value,
                    "detail": f"Remaining budget ₹{remaining_budget} is below min threshold ₹{parameters.min_amount}"
                })
            continue

        # Earliest arrival time of traced funds into this account
        earliest_arrival = min(acc_state["arrival_times"]) if acc_state["arrival_times"] else seed_timestamp_utc

        # Gather outgoing completed transactions from current_account after funds arrived
        outgoing = [
            tx for tx in all_transactions
            if tx.source_account == current_account_id
            and tx.status == "completed"
            and tx.timestamp_utc >= earliest_arrival
            and tx.timestamp_utc <= horizon_limit
        ]
        
        # Deterministic sort: timestamp UTC, then transaction ID
        outgoing.sort(key=lambda x: (x.timestamp_utc, x.transaction_id))

        if not outgoing:
            # Natural terminal node: funds stopped here
            acc_state["is_terminal"] = True
            acc_state["termination_reason"] = TerminationReason.NATURAL_END
            continue

        # Group and process each outgoing transfer
        for tx in outgoing:
            edges_examined += 1
            if edges_examined >= parameters.work_budget_edges:
                work_budget_reached = True
                stopping_reasons.append({
                    "account_id": current_account_id,
                    "reason": TerminationReason.WORK_BUDGET_EXCEEDED.value,
                    "detail": f"Exceeded work budget of {parameters.work_budget_edges} edges"
                })
                break

            if remaining_budget < parameters.min_amount:
                break

            # Calculate total pooled inflow arrived at or before this outgoing transfer
            # Sum of all credits to current_account up to tx.timestamp_utc
            all_credits_to_acc = [
                t.amount for t in all_transactions
                if t.destination_account == current_account_id
                and t.status == "completed"
                and t.timestamp_utc <= tx.timestamp_utc
            ]
            pool_inflow = sum(all_credits_to_acc, Decimal("0.00"))
            
            # If pool_inflow is 0, default to remaining budget
            if pool_inflow <= Decimal("0"):
                pool_inflow = remaining_budget

            attributed_amt, fraction = attribute(
                edge_amount=tx.amount,
                remaining=remaining_budget,
                pool_inflow=pool_inflow
            )

            if attributed_amt <= Decimal("0.00"):
                continue

            # Edge confidence
            edge_conf = round(parent_conf * fraction, 4)

            # Update parent account state and remaining shared budget
            acc_state["traced_out"] += attributed_amt
            remaining_budget -= attributed_amt
            
            # Destination account handling
            dest_acc_id = tx.destination_account
            dest_meta = accounts_metadata.get(dest_acc_id)
            is_dest_external = tx.dest_is_external or (dest_meta and not dest_meta.is_operating_institution)

            # Record Edge
            edge = TraceEdge(
                transaction_id=tx.transaction_id,
                source_account=current_account_id,
                destination_account=dest_acc_id,
                timestamp_utc=tx.timestamp_str,
                raw_amount=tx.amount,
                attributed_amount=attributed_amt,
                fraction=round(fraction, 4),
                confidence=edge_conf,
                hop=current_hop,
                channel=tx.channel,
                is_terminal=is_dest_external,
                evidence_id=tx.transaction_id,
            )
            recorded_edges.append(edge)

            # Handle Institutional Boundary Terminal
            if is_dest_external:
                recorded_boundaries.append(TraceBoundary(
                    boundary_account=dest_acc_id,
                    institution_name=tx.dest_institution_name,
                    institution_code=tx.dest_institution_code,
                    crossed_amount=attributed_amt,
                    last_transaction_id=tx.transaction_id,
                    timestamp_utc=tx.timestamp_str,
                    reason=f"Crossed operating institution into {tx.dest_institution_name}"
                ))
                # Add terminal node for external institution
                if dest_acc_id not in nodes_state:
                    nodes_state[dest_acc_id] = {
                        "traced_in": Decimal("0.00"),
                        "traced_out": Decimal("0.00"),
                        "confidence": edge_conf,
                        "min_hop": current_hop + 1,
                        "is_terminal": True,
                        "termination_reason": TerminationReason.EXTERNAL_INSTITUTION_BOUNDARY,
                        "evidence_ids": [tx.transaction_id],
                        "arrival_times": [tx.timestamp_utc],
                    }
                nodes_state[dest_acc_id]["traced_in"] += attributed_amt
                continue

            # Destination is internal
            if dest_acc_id not in nodes_state:
                nodes_state[dest_acc_id] = {
                    "traced_in": Decimal("0.00"),
                    "traced_out": Decimal("0.00"),
                    "confidence": edge_conf,
                    "min_hop": current_hop + 1,
                    "is_terminal": False,
                    "termination_reason": None,
                    "evidence_ids": [],
                    "arrival_times": [],
                }
                frontier.append((dest_acc_id, current_hop + 1, edge_conf))

            nodes_state[dest_acc_id]["traced_in"] += attributed_amt
            nodes_state[dest_acc_id]["evidence_ids"].append(tx.transaction_id)
            nodes_state[dest_acc_id]["arrival_times"].append(tx.timestamp_utc)
            # Confidence minimum or path-based
            if edge_conf < nodes_state[dest_acc_id]["confidence"]:
                nodes_state[dest_acc_id]["confidence"] = edge_conf

    # Convert nodes_state to TraceNode objects
    trace_nodes: List[TraceNode] = []
    total_unmoved = Decimal("0.00")

    for acc_id, state in nodes_state.items():
        meta = accounts_metadata.get(acc_id)
        pseudonymous_key = meta.pseudonymous_key if meta else f"ACC-PSEUDO-{acc_id[-4:]}"
        inst_id = meta.institution_id if meta else "INST-001"
        is_operating = meta.is_operating_institution if meta else True
        
        traced_in = state["traced_in"]
        traced_out = state["traced_out"]
        unmoved = max(Decimal("0.00"), traced_in - traced_out)
        
        # Check balance completeness
        avail_bal = meta.available_balance if (meta and meta.history_complete) else None
        bal_status = "known" if (meta and meta.history_complete and avail_bal is not None) else "unknown"
        
        freezable_est = min(unmoved, avail_bal) if (avail_bal is not None) else None
        
        # Only accounts inside operating institution contribute to unmoved traced value in our ledger.
        # External accounts are accounted for under crossed_boundary_val.
        if is_operating and unmoved > Decimal("0.00"):
            total_unmoved += unmoved

        trace_nodes.append(TraceNode(
            account_id=acc_id,
            pseudonymous_key=pseudonymous_key,
            institution_id=inst_id,
            is_operating_institution=is_operating,
            traced_in=traced_in,
            traced_out=traced_out,
            unmoved_traced_value=unmoved,
            available_balance=avail_bal,
            balance_status=bal_status,
            freezable_estimate=freezable_est,
            confidence=state["confidence"],
            min_hop=state["min_hop"],
            is_terminal=state["is_terminal"],
            termination_reason=state["termination_reason"],
            evidence_ids=list(set(state["evidence_ids"])),
        ))

    # Crossed boundary value
    crossed_boundary_val = sum((b.crossed_amount for b in recorded_boundaries), Decimal("0.00"))

    # Canonical result hash
    hasher = hashlib.sha256()
    hash_payload = {
        "seed_tx": seed_transaction_id,
        "seed_amount": str(seed_amount),
        "params": parameters.model_dump(mode="json"),
        "edges": [e.model_dump(mode="json") for e in recorded_edges],
        "nodes": [n.model_dump(mode="json") for n in trace_nodes],
    }
    hasher.update(json.dumps(hash_payload, sort_keys=True, default=str).encode("utf-8"))
    result_hash = hasher.hexdigest()

    return TraceResult(
        trace_id=trace_id,
        case_id=case_id,
        dataset_id=dataset_id,
        dataset_checksum=dataset_checksum,
        engine_version="1.0.0",
        attribution_rule=AttributionRuleInfo(),
        parameters=parameters,
        seed_transaction_id=seed_transaction_id,
        seed_amount=seed_amount,
        victim_account=victim_account,
        nodes=trace_nodes,
        edges=recorded_edges,
        boundaries=recorded_boundaries,
        stopping_reasons=stopping_reasons,
        complete=(not work_budget_reached),
        crossed_boundary_value=crossed_boundary_val,
        total_unmoved_value=total_unmoved,
        result_hash=result_hash,
        is_synthetic=True,
    )
