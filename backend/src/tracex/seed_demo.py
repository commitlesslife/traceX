"""Deterministic Seed and Reset Script for TRACE-X.
Seeds the required users, institutions, accounts, and the golden transaction fixture:
  - Operating Institution (Bank A) + External Institution (Bank B / Inter-bank)
  - Accounts with complete history vs incomplete history (testing balance known vs unknown)
  - Golden Fixture transactions:
      Victim -> A ₹1,00,000 (10:00)
      Unrelated -> A ₹50,000 (10:05)
      A -> B ₹60,000 (10:10)
      A -> C ₹30,000 (10:20)
      A -> ExtBank ₹15,000 (10:25) [Boundary test branch]
  - Pre-seeded Complaint & Case ready for instant demo.
"""
from decimal import Decimal
from datetime import datetime, timezone
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
)
from tracex.auth.security import hash_password


def seed_database():
    init_db()
    db = SessionLocal()

    # Clear existing demo state cleanly
    db.query(AuditEvent).delete()
    db.query(Complaint).delete()
    db.query(Case).delete()
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
    db.add(inst_operating)
    db.add(inst_external)

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
        name="VISTERA Golden Demonstration Fixture v1",
        source="Synthetic Deterministic Generator",
        checksum="sha256-golden-fixture-v1",
        is_synthetic=True,
        row_count=Decimal("5"),
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
        details_json='{"status": "ready", "fixture": "golden_v1"}',
    )
    db.add(audit)

    db.commit()
    db.close()
    print("[SEED] Successfully seeded TRACE-X MVP database with users, institutions, accounts, and golden fixture.")


if __name__ == "__main__":
    seed_database()
