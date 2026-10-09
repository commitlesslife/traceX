"""Unit test for TRACE-X Golden Fixture.
Verifies the exact invariants specified in Requirements4 and Hackathon Plan:
- Victim sends ₹1,00,000 to Account A at 10:00
- A receives ₹50,000 unrelated funds at 10:05 (pool = ₹1,50,000)
- A sends ₹60,000 to B at 10:10 -> attribute ₹40,000 (fraction 2/3)
- Shared remaining budget at A becomes ₹60,000
- A sends ₹30,000 to C at 10:20 -> attribute ₹12,000
- Remaining unmoved at A is ₹48,000
- Exact conservation: ₹40,000 + ₹12,000 + ₹48,000 == ₹1,00,000
"""
from decimal import Decimal
from datetime import datetime, timezone

from tracex.domain.models import TraceParameters
from tracex.engine.trace_engine import (
    run_pure_trace,
    EngineAccount,
    EngineTransaction,
)


def test_golden_fixture_attribution():
    t_10_00 = datetime(2026, 10, 8, 10, 0, 0, tzinfo=timezone.utc)
    t_10_05 = datetime(2026, 10, 8, 10, 5, 0, tzinfo=timezone.utc)
    t_10_10 = datetime(2026, 10, 8, 10, 10, 0, tzinfo=timezone.utc)
    t_10_20 = datetime(2026, 10, 8, 10, 20, 0, tzinfo=timezone.utc)

    # Accounts
    accounts = {
        "ACC-VICTIM": EngineAccount("ACC-VICTIM", "KEY-VIC", "INST-INTERNAL", True),
        "ACC-A": EngineAccount("ACC-A", "KEY-A", "INST-INTERNAL", True, available_balance=Decimal("48000.00"), history_complete=True),
        "ACC-B": EngineAccount("ACC-B", "KEY-B", "INST-INTERNAL", True, available_balance=None, history_complete=False),
        "ACC-C": EngineAccount("ACC-C", "KEY-C", "INST-INTERNAL", True, available_balance=Decimal("20000.00"), history_complete=True),
    }

    # Transactions
    txs = [
        # Seed tx: Victim -> A ₹100,000
        EngineTransaction("TX-SEED", "ACC-VICTIM", "ACC-A", Decimal("100000.00"), t_10_00, "2026-10-08T10:00:00Z", "completed", "UPI"),
        # Unrelated pool inflow: Other -> A ₹50,000
        EngineTransaction("TX-POOL", "ACC-OTHER", "ACC-A", Decimal("50000.00"), t_10_05, "2026-10-08T10:05:00Z", "completed", "NEFT"),
        # Outgoing A -> B ₹60,000
        EngineTransaction("TX-A-B", "ACC-A", "ACC-B", Decimal("60000.00"), t_10_10, "2026-10-08T10:10:00Z", "completed", "IMPS"),
        # Outgoing A -> C ₹30,000
        EngineTransaction("TX-A-C", "ACC-A", "ACC-C", Decimal("30000.00"), t_10_20, "2026-10-08T10:20:00Z", "completed", "IMPS"),
    ]

    params = TraceParameters(max_hops=6, horizon_hours=72, min_amount=Decimal("100.00"))

    result = run_pure_trace(
        seed_transaction_id="TX-SEED",
        victim_account="ACC-VICTIM",
        first_recipient_account="ACC-A",
        seed_amount=Decimal("100000.00"),
        seed_timestamp_utc=t_10_00,
        parameters=params,
        all_transactions=txs,
        accounts_metadata=accounts,
    )

    # Check edges
    edge_map = {e.destination_account: e for e in result.edges}
    assert "ACC-B" in edge_map
    assert "ACC-C" in edge_map
    assert edge_map["ACC-B"].attributed_amount == Decimal("40000.00")
    assert edge_map["ACC-C"].attributed_amount == Decimal("12000.00")

    # Check nodes
    node_map = {n.account_id: n for n in result.nodes}
    assert node_map["ACC-A"].unmoved_traced_value == Decimal("48000.00")
    assert node_map["ACC-B"].unmoved_traced_value == Decimal("40000.00")
    assert node_map["ACC-C"].unmoved_traced_value == Decimal("12000.00")

    # Check balance and freezable estimates
    assert node_map["ACC-A"].balance_status == "known"
    assert node_map["ACC-A"].freezable_estimate == Decimal("48000.00")
    assert node_map["ACC-B"].balance_status == "unknown"
    assert node_map["ACC-B"].available_balance is None
    assert node_map["ACC-B"].freezable_estimate is None

    # Exact money conservation
    total = (
        node_map["ACC-A"].unmoved_traced_value
        + node_map["ACC-B"].unmoved_traced_value
        + node_map["ACC-C"].unmoved_traced_value
    )
    assert total == Decimal("100000.00")
    print("\n[SUCCESS] Golden Fixture strictly verified: 40k + 12k + 48k == 100k!")


if __name__ == "__main__":
    test_golden_fixture_attribution()
