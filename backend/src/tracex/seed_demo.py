"""Deterministic Seed and Reset Script for TRACE-X.
Seeds demo users, institutions, the original golden fixture, and three
longer trails for exercising the graph, map, and timeline views:
  - Operating Institution (Bank A) + External Institution (Bank B / Inter-bank)
  - Accounts with complete history vs incomplete history (testing balance known vs unknown)
  - Golden Fixture transactions:
      Victim -> A ₹1,00,000 (10:00)
      Unrelated -> A ₹50,000 (10:05)
      A -> B ₹60,000 (10:10)
      A -> C ₹30,000 (10:20)
      A -> ExtBank ₹15,000 (10:25) [Boundary test branch]
  - CASE-2026-0891: original compact proportional-attribution example.
  - CASE-2026-0888: 19-account, six-hop branching trail with a boundary edge.
  - CASE-2026-0877: eight-hop ladder with a synthetic international boundary.
  - CASE-2026-0866: seven-hop trail with domestic and international boundaries.
"""
from decimal import Decimal
from datetime import datetime, timezone, timedelta
import uuid

from tracex.repositories.db import (
    SessionLocal,
    init_db,
    Institution,
    Account,
    Transaction,
    Dataset,
    User,
    Complaint,
    Case,
    AuditEvent,
    StoredTraceRun,
    RecommendationDraft,
)
from tracex.auth.security import hash_password


def add_extended_case(db, dataset_id, *, suffix, prefix, seed_amount, start, transfers, international_keys=()):
    """Add one isolated synthetic trail with its own victim and account set."""
    keys = {"VIC", "A"}
    for source, destination, _, _, _ in transfers:
        keys.update((source, destination))

    accounts = {}
    for key in sorted(keys):
        external = key.startswith("EXT")
        complete = key == "VIC" or (not external and key not in {"E", "H", "N"})
        accounts[key] = Account(
            id=f"ACC-{prefix}-{key}",
            pseudonymous_key=f"PSEUDO-{prefix}-{key}",
            institution_id="INST-INTL-03" if key in international_keys else "INST-EXT-02" if external else "INST-OP-01",
            opening_balance=Decimal(seed_amount) if key == "VIC" else Decimal("0.00") if complete else None,
            opening_balance_at=datetime(2026, 10, 1, tzinfo=timezone.utc) if complete else None,
            history_complete=complete,
            account_type="savings" if key == "VIC" else "current",
        )
    db.add_all(accounts.values())

    rows = [("VIC", "A", seed_amount, 0, "UPI"), *transfers]
    for source, destination, amount, minute, channel in rows:
        db.add(Transaction(
            id=str(uuid.uuid4()),
            transaction_id=f"TX-{prefix}-{source}-{destination}",
            source_account_id=accounts[source].id,
            destination_account_id=accounts[destination].id,
            amount=Decimal(amount),
            currency="INR",
            timestamp_utc=start + timedelta(minutes=minute),
            original_offset="+05:30",
            status="completed",
            channel=channel,
            source_institution_id=accounts[source].institution_id,
            destination_institution_id=accounts[destination].institution_id,
            dataset_id=dataset_id,
        ))

    complaint = Complaint(
        id=f"CMP-2026-{suffix}",
        victim_account=accounts["VIC"].pseudonymous_key,
        disputed_transaction_ref=f"TX-{prefix}-VIC-A",
        disputed_amount=Decimal(seed_amount),
        reported_time=start + timedelta(minutes=120),
        channel="CYBER_CRIME_NCRP",
        match_status="matched",
        matched_transaction_id=f"TX-{prefix}-VIC-A",
        assigned_analyst_id="USR-ANALYST-01",
    )
    db.add(complaint)
    db.add(Case(
        id=f"CASE-2026-{suffix}",
        complaint_id=complaint.id,
        status="open",
        disposition="under_investigation",
    ))


def seed_database():
    init_db()
    db = SessionLocal()

    # Clear existing demo state cleanly
    db.query(AuditEvent).delete()
    db.query(RecommendationDraft).delete()
    db.query(StoredTraceRun).delete()
    db.query(Case).delete()
    db.query(Complaint).delete()
    db.query(Transaction).delete()
    db.query(Account).delete()
    db.query(Institution).delete()
    db.query(Dataset).delete()
    db.query(User).delete()
    db.commit()

    print("[SEED] Cleared prior demo state.")

    # 1. Seed Users (Roles: Analyst, Supervisor, Admin, Auditor)
    users = [
        User(
            id="USR-ANALYST-01",
            username="analyst_priya",
            display_name="Priya Sharma (Fraud Analyst)",
            hashed_password=hash_password("analyst123"),
            role="analyst",
        ),
        User(
            id="USR-SUPERVISOR-01",
            username="supervisor_rajesh",
            display_name="Rajesh Verma (Chief Supervisor)",
            hashed_password=hash_password("supervisor123"),
            role="supervisor",
        ),
        User(
            id="USR-ADMIN-01",
            username="admin_user",
            display_name="Admin Ops",
            hashed_password=hash_password("admin123"),
            role="admin",
        ),
        User(
            id="USR-AUDITOR-01",
            username="auditor_user",
            display_name="Audit Cell Lead",
            hashed_password=hash_password("auditor123"),
            role="auditor",
        ),
    ]
    for u in users:
        db.add(u)

    # 2. Seed Institutions
    inst_operating = Institution(
        id="INST-OP-01",
        code="SBI_OPS",
        name="Operating Bank (State Bank Ledger)",
        is_operating_institution=True,
    )
    inst_external = Institution(
        id="INST-EXT-02",
        code="HDFC_EXT",
        name="External Partner Bank (HDFC Bank)",
        is_operating_institution=False,
    )
    inst_international = Institution(
        id="INST-INTL-03",
        code="SYNTH_INTL",
        name="Synthetic International Transfer Processor",
        is_operating_institution=False,
    )
    db.add(inst_operating)
    db.add(inst_external)
    db.add(inst_international)

    # 3. Seed Accounts
    # Account A: complete history known, opening balance ₹0
    acc_victim = Account(
        id="ACC-VICTIM-99",
        pseudonymous_key="PSEUDO-VIC-9821",
        institution_id="INST-OP-01",
        opening_balance=Decimal("150000.00"),
        opening_balance_at=datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc),
        history_complete=True,
        account_type="savings",
    )
    acc_a = Account(
        id="ACC-A-101",
        pseudonymous_key="PSEUDO-MULE-A",
        institution_id="INST-OP-01",
        opening_balance=Decimal("0.00"),
        opening_balance_at=datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc),
        history_complete=True,  # Complete history -> balance known
        account_type="savings",
    )
    acc_b = Account(
        id="ACC-B-202",
        pseudonymous_key="PSEUDO-MULE-B",
        institution_id="INST-OP-01",
        opening_balance=None,
        opening_balance_at=None,
        history_complete=False,  # Incomplete history -> "balance unknown"
        account_type="current",
    )
    acc_c = Account(
        id="ACC-C-303",
        pseudonymous_key="PSEUDO-MULE-C",
        institution_id="INST-OP-01",
        opening_balance=Decimal("5000.00"),
        opening_balance_at=datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc),
        history_complete=True,
        account_type="savings",
    )
    acc_ext_target = Account(
        id="ACC-EXT-404",
        pseudonymous_key="PSEUDO-EXT-INTERBANK-D",
        institution_id="INST-EXT-02",  # External institution
        opening_balance=None,
        opening_balance_at=None,
        history_complete=False,
        account_type="savings",
    )
    acc_pool_sender = Account(
        id="ACC-OTHER-POOL",
        pseudonymous_key="PSEUDO-LEGIT-BIZ",
        institution_id="INST-OP-01",
        opening_balance=Decimal("200000.00"),
        opening_balance_at=datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc),
        history_complete=True,
        account_type="current",
    )

    db.add_all([acc_victim, acc_a, acc_b, acc_c, acc_ext_target, acc_pool_sender])

    # 4. Seed Dataset
    dataset = Dataset(
        id="DATASET-SYNTHETIC-GOLDEN-01",
        name="VISTERA Synthetic Demo Fixtures v3",
        source="Synthetic Deterministic Generator",
        checksum="sha256-synthetic-demo-fixtures-v3",
        is_synthetic=True,
        row_count=Decimal("24"),
    )
    db.add(dataset)

    # 5. Transactions
    txs = [
        # Seed fraud tx: Victim -> A ₹100,000 (10:00 UTC)
        Transaction(
            id=str(uuid.uuid4()),
            transaction_id="TX-SEED-100K",
            source_account_id=acc_victim.id,
            destination_account_id=acc_a.id,
            amount=Decimal("100000.00"),
            currency="INR",
            timestamp_utc=datetime(2026, 10, 8, 10, 0, 0, tzinfo=timezone.utc),
            original_offset="+05:30",
            status="completed",
            channel="UPI",
            source_institution_id="INST-OP-01",
            destination_institution_id="INST-OP-01",
            dataset_id=dataset.id,
        ),
        # Unrelated pool credit: Other -> A ₹50,000 (10:05 UTC)
        Transaction(
            id=str(uuid.uuid4()),
            transaction_id="TX-POOL-50K",
            source_account_id=acc_pool_sender.id,
            destination_account_id=acc_a.id,
            amount=Decimal("50000.00"),
            currency="INR",
            timestamp_utc=datetime(2026, 10, 8, 10, 5, 0, tzinfo=timezone.utc),
            original_offset="+05:30",
            status="completed",
            channel="NEFT",
            source_institution_id="INST-OP-01",
            destination_institution_id="INST-OP-01",
            dataset_id=dataset.id,
        ),
        # Outgoing A -> B ₹60,000 (10:10 UTC)
        Transaction(
            id=str(uuid.uuid4()),
            transaction_id="TX-A-TO-B-60K",
            source_account_id=acc_a.id,
            destination_account_id=acc_b.id,
            amount=Decimal("60000.00"),
            currency="INR",
            timestamp_utc=datetime(2026, 10, 8, 10, 10, 0, tzinfo=timezone.utc),
            original_offset="+05:30",
            status="completed",
            channel="IMPS",
            source_institution_id="INST-OP-01",
            destination_institution_id="INST-OP-01",
            dataset_id=dataset.id,
        ),
        # Outgoing A -> C ₹30,000 (10:20 UTC)
        Transaction(
            id=str(uuid.uuid4()),
            transaction_id="TX-A-TO-C-30K",
            source_account_id=acc_a.id,
            destination_account_id=acc_c.id,
            amount=Decimal("30000.00"),
            currency="INR",
            timestamp_utc=datetime(2026, 10, 8, 10, 20, 0, tzinfo=timezone.utc),
            original_offset="+05:30",
            status="completed",
            channel="IMPS",
            source_institution_id="INST-OP-01",
            destination_institution_id="INST-OP-01",
            dataset_id=dataset.id,
        ),
        # Boundary outgoing A -> ExtBank ₹10,000 (10:25 UTC)
        Transaction(
            id=str(uuid.uuid4()),
            transaction_id="TX-A-TO-EXT-10K",
            source_account_id=acc_a.id,
            destination_account_id=acc_ext_target.id,
            amount=Decimal("10000.00"),
            currency="INR",
            timestamp_utc=datetime(2026, 10, 8, 10, 25, 0, tzinfo=timezone.utc),
            original_offset="+05:30",
            status="completed",
            channel="RTGS",
            source_institution_id="INST-OP-01",
            destination_institution_id="INST-EXT-02",
            dataset_id=dataset.id,
        ),
    ]
    db.add_all(txs)

    # 5b. Deeper branching fixture for graph and hop-timeline demonstrations.
    # Keep the original case unchanged so the simple golden workflow remains
    # available as the default case. This second synthetic case exercises six
    # traced hops, branches, an unknown-balance account, and a ledger boundary.
    deep_accounts = {
        key: Account(
            id=f"ACC-DEEP-{key}",
            pseudonymous_key=f"PSEUDO-DEEP-{key}",
            institution_id="INST-OP-01",
            opening_balance=Decimal("0.00") if key in {"A", "D", "H", "N", "S"} else None,
            opening_balance_at=datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc) if key in {"A", "D", "H", "N", "S"} else None,
            history_complete=key in {"A", "D", "H", "N", "S"},
            account_type="savings" if key in {"A", "D", "H", "N", "S"} else "current",
        )
        for key in "ABCDEFGHIJKLMNOPQRS"
    }
    deep_external = Account(
        id="ACC-DEEP-EXT",
        pseudonymous_key="PSEUDO-DEEP-EXT-BOUNDARY",
        institution_id="INST-EXT-02",
        opening_balance=None,
        opening_balance_at=None,
        history_complete=False,
        account_type="savings",
    )
    db.add_all([*deep_accounts.values(), deep_external])

    deep_start = datetime(2026, 10, 7, 8, 0, 0, tzinfo=timezone.utc)
    deep_transfers = [
        # Seed and first split: 100,000 -> 60,000 + 40,000.
        ("TX-DEEP-SEED-100K", acc_victim.id, "A", "100000.00", 0, "UPI", False),
        ("TX-DEEP-A-B-60K", "A", "B", "60000.00", 5, "IMPS", False),
        ("TX-DEEP-A-C-40K", "A", "C", "40000.00", 8, "IMPS", False),
        # Hop two branches.
        ("TX-DEEP-B-D-40K", "B", "D", "40000.00", 12, "IMPS", False),
        ("TX-DEEP-B-E-20K", "B", "E", "20000.00", 14, "UPI", False),
        ("TX-DEEP-C-F-25K", "C", "F", "25000.00", 16, "IMPS", False),
        ("TX-DEEP-C-G-15K", "C", "G", "15000.00", 18, "NEFT", False),
        # Hop three: one transfer crosses to an external institution.
        ("TX-DEEP-D-H-25K", "D", "H", "25000.00", 22, "IMPS", False),
        ("TX-DEEP-D-I-15K", "D", "I", "15000.00", 24, "UPI", False),
        ("TX-DEEP-E-EXT-20K", "E", "EXT", "20000.00", 26, "RTGS", True),
        ("TX-DEEP-F-K-15K", "F", "K", "15000.00", 28, "IMPS", False),
        ("TX-DEEP-F-L-10K", "F", "L", "10000.00", 30, "UPI", False),
        ("TX-DEEP-G-M-15K", "G", "M", "15000.00", 32, "NEFT", False),
        # Hop four and five continue the long branch.
        ("TX-DEEP-H-N-15K", "H", "N", "15000.00", 36, "IMPS", False),
        ("TX-DEEP-H-O-10K", "H", "O", "10000.00", 38, "UPI", False),
        ("TX-DEEP-M-P-15K", "M", "P", "15000.00", 42, "IMPS", False),
        ("TX-DEEP-P-Q-12K", "P", "Q", "12000.00", 48, "UPI", False),
        ("TX-DEEP-P-R-3K", "P", "R", "3000.00", 50, "IMPS", False),
        # Sixth hop terminates at a new account, giving the graph a clear tail.
        ("TX-DEEP-Q-S-12K", "Q", "S", "12000.00", 56, "IMPS", False),
    ]
    deep_rows = []
    for tx_id, source, destination, amount, minute, channel, external in deep_transfers:
        source_id = acc_victim.id if source == acc_victim.id else deep_accounts[source].id
        destination_id = deep_external.id if destination == "EXT" else deep_accounts[destination].id
        source_inst = "INST-OP-01"
        destination_inst = "INST-EXT-02" if external else "INST-OP-01"
        tx_time = deep_start + timedelta(minutes=minute)
        deep_rows.append(Transaction(
            id=str(uuid.uuid4()),
            transaction_id=tx_id,
            source_account_id=source_id,
            destination_account_id=destination_id,
            amount=Decimal(amount),
            currency="INR",
            timestamp_utc=tx_time,
            original_offset="+05:30",
            status="completed",
            channel=channel,
            source_institution_id=source_inst,
            destination_institution_id=destination_inst,
            dataset_id=dataset.id,
        ))
    db.add_all(deep_rows)

    # 6. Pre-seeded Complaint & Case
    complaint = Complaint(
        id="CMP-2026-0891",
        victim_account=acc_victim.pseudonymous_key,
        disputed_transaction_ref="TX-SEED-100K",
        disputed_amount=Decimal("100000.00"),
        reported_time=datetime(2026, 10, 8, 10, 30, 0, tzinfo=timezone.utc),
        channel="CYBER_CRIME_NCRP",
        match_status="matched",
        matched_transaction_id="TX-SEED-100K",
        assigned_analyst_id="USR-ANALYST-01",
    )
    db.add(complaint)

    case = Case(
        id="CASE-2026-0891",
        complaint_id=complaint.id,
        status="open",
        disposition="under_investigation",
    )
    db.add(case)

    deep_complaint = Complaint(
        id="CMP-2026-0888",
        victim_account=acc_victim.pseudonymous_key,
        disputed_transaction_ref="TX-DEEP-SEED-100K",
        disputed_amount=Decimal("100000.00"),
        reported_time=datetime(2026, 10, 7, 9, 0, 0, tzinfo=timezone.utc),
        channel="CYBER_CRIME_NCRP",
        match_status="matched",
        matched_transaction_id="TX-DEEP-SEED-100K",
        assigned_analyst_id="USR-ANALYST-01",
    )
    db.add(deep_complaint)
    db.add(Case(
        id="CASE-2026-0888",
        complaint_id=deep_complaint.id,
        status="open",
        disposition="under_investigation",
    ))

    # Eight-hop split-and-ladder trail: a domestic account ladder and one external
    # institution boundary. Account IDs never overlap another fixture.
    add_extended_case(
        db, dataset.id, suffix="0877", prefix="LADDER",
        seed_amount="180000.00",
        international_keys=("EXT",),
        start=datetime(2026, 10, 6, 8, 0, tzinfo=timezone.utc),
        transfers=[
            ("A", "B", "100000.00", 4, "IMPS"), ("A", "C", "50000.00", 6, "NEFT"),
            ("B", "D", "80000.00", 11, "IMPS"), ("B", "E", "20000.00", 13, "UPI"), ("C", "F", "50000.00", 15, "IMPS"),
            ("D", "G", "60000.00", 20, "IMPS"), ("D", "H", "20000.00", 22, "UPI"), ("E", "EXT", "20000.00", 24, "SWIFT"), ("F", "I", "50000.00", 26, "NEFT"),
            ("G", "J", "50000.00", 32, "IMPS"), ("H", "K", "20000.00", 34, "UPI"), ("I", "L", "40000.00", 36, "IMPS"),
            ("J", "M", "40000.00", 43, "IMPS"), ("L", "N", "30000.00", 45, "NEFT"),
            ("M", "O", "30000.00", 52, "IMPS"), ("N", "P", "20000.00", 54, "UPI"),
            ("O", "Q", "20000.00", 62, "IMPS"), ("P", "R", "10000.00", 64, "NEFT"),
            ("Q", "S", "10000.00", 72, "UPI"), ("R", "T", "5000.00", 74, "IMPS"),
        ],
    )

    # Seven-hop trail with independent visibility boundaries at hops two and
    # seven, for comparing recoverable value with money that left the ledger.
    add_extended_case(
        db, dataset.id, suffix="0866", prefix="BOUNDARY",
        seed_amount="125000.00",
        international_keys=("EXT2",),
        start=datetime(2026, 10, 5, 7, 30, tzinfo=timezone.utc),
        transfers=[
            ("A", "B", "70000.00", 4, "IMPS"), ("A", "C", "40000.00", 6, "UPI"),
            ("B", "D", "50000.00", 12, "IMPS"), ("B", "EXT1", "20000.00", 14, "RTGS"), ("C", "E", "30000.00", 16, "NEFT"),
            ("D", "F", "40000.00", 23, "IMPS"), ("E", "G", "20000.00", 25, "UPI"),
            ("F", "H", "30000.00", 32, "IMPS"), ("G", "I", "15000.00", 34, "NEFT"),
            ("H", "J", "20000.00", 42, "IMPS"), ("I", "K", "10000.00", 44, "UPI"),
            ("J", "L", "15000.00", 53, "IMPS"), ("K", "M", "8000.00", 55, "NEFT"),
            ("L", "N", "10000.00", 64, "IMPS"), ("M", "EXT2", "8000.00", 66, "SWIFT"),
        ],
    )

    # Keep dataset metadata aligned with every transaction inserted above.
    db.flush()
    dataset.row_count = Decimal(db.query(Transaction).count())

    # 7. Audit log initialization
    audit = AuditEvent(
        id=str(uuid.uuid4()),
        occurred_at=datetime.now(timezone.utc),
        actor_user_id="SYSTEM",
        actor_role="admin",
        action="DEMO_RESET_SEED",
        target_type="system",
        target_id="all",
        reason="Initial seed and demo state reset",
        details_json='{"status": "ready", "fixture": "four_cases_v3"}',
    )
    db.add(audit)

    db.commit()
    db.close()
    print("[SEED] Successfully seeded TRACE-X demo database with four isolated case fixtures.")


if __name__ == "__main__":
    seed_database()
