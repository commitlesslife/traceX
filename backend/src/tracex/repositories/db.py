"""TRACE-X SQLAlchemy Database Models.
Covers core, app, and audit tables.
Compatible with SQLite (local hackathon zero-setup) and PostgreSQL.
Includes DB-level separation-of-duty check constraint between draft author and approver.
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    create_engine,
    Column,
    String,
    Numeric,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
    CheckConstraint,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from tracex.settings import settings

Base = declarative_base()


class Institution(Base):
    __tablename__ = "institutions"

    id = Column(String(64), primary_key=True)
    code = Column(String(32), unique=True, nullable=False)
    name = Column(String(128), nullable=False)
    is_operating_institution = Column(Boolean, default=False, nullable=False)


class Account(Base):
    __tablename__ = "accounts"

    id = Column(String(64), primary_key=True)
    pseudonymous_key = Column(String(64), unique=True, nullable=False)
    institution_id = Column(String(64), ForeignKey("institutions.id"), nullable=False)
    opening_balance = Column(Numeric(18, 2), nullable=True)
    opening_balance_at = Column(DateTime(timezone=True), nullable=True)
    history_complete = Column(Boolean, default=False, nullable=False)
    account_type = Column(String(32), default="savings", nullable=False)

    institution = relationship("Institution")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(String(64), primary_key=True)
    transaction_id = Column(String(64), unique=True, nullable=False)
    source_account_id = Column(String(64), ForeignKey("accounts.id"), nullable=False)
    destination_account_id = Column(String(64), ForeignKey("accounts.id"), nullable=False)
    amount = Column(Numeric(18, 2), nullable=False)
    currency = Column(String(3), default="INR", nullable=False)
    timestamp_utc = Column(DateTime(timezone=True), nullable=False)
    original_offset = Column(String(8), default="+05:30", nullable=False)
    status = Column(String(16), default="completed", nullable=False)
    channel = Column(String(16), default="IMPS", nullable=False)
    source_institution_id = Column(String(64), ForeignKey("institutions.id"), nullable=False)
    destination_institution_id = Column(String(64), ForeignKey("institutions.id"), nullable=False)
    dataset_id = Column(String(64), nullable=False)

    __table_args__ = (
        Index("idx_tx_src_time", "source_account_id", "timestamp_utc"),
        Index("idx_tx_dest_time", "destination_account_id", "timestamp_utc"),
    )


class Dataset(Base):
    __tablename__ = "datasets"

    id = Column(String(64), primary_key=True)
    name = Column(String(128), nullable=False)
    source = Column(String(128), nullable=False)
    checksum = Column(String(64), nullable=False)
    is_synthetic = Column(Boolean, default=True, nullable=False)
    row_count = Column(Numeric(10, 0), default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class User(Base):
    __tablename__ = "users"

    id = Column(String(64), primary_key=True)
    username = Column(String(64), unique=True, nullable=False)
    hashed_password = Column(String(128), nullable=False)
    display_name = Column(String(64), nullable=False)
    role = Column(String(16), nullable=False)  # analyst, supervisor, admin, auditor
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Complaint(Base):
    __tablename__ = "complaints"

    id = Column(String(64), primary_key=True)
    victim_account = Column(String(64), nullable=False)
    disputed_transaction_ref = Column(String(64), nullable=False)
    disputed_amount = Column(Numeric(18, 2), nullable=False)
    reported_time = Column(DateTime(timezone=True), nullable=False)
    channel = Column(String(32), default="NCRP_PORTAL", nullable=False)
    match_status = Column(String(16), default="matched", nullable=False)  # matched, unresolved
    matched_transaction_id = Column(String(64), ForeignKey("transactions.transaction_id"), nullable=True)
    assigned_analyst_id = Column(String(64), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Case(Base):
    __tablename__ = "cases"

    id = Column(String(64), primary_key=True)
    complaint_id = Column(String(64), ForeignKey("complaints.id"), unique=True, nullable=False)
    status = Column(String(32), default="open", nullable=False)  # open, draft_ready, closed
    disposition = Column(String(64), default="in_investigation", nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class StoredTraceRun(Base):
    __tablename__ = "trace_runs"

    id = Column(String(64), primary_key=True)
    case_id = Column(String(64), ForeignKey("cases.id"), nullable=False)
    seed_transaction_id = Column(String(64), nullable=False)
    parameters_json = Column(Text, nullable=False)
    result_json = Column(Text, nullable=False)
    result_hash = Column(String(64), nullable=False)
    dataset_checksum = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class RecommendationDraft(Base):
    __tablename__ = "recommendation_drafts"

    id = Column(String(64), primary_key=True)
    case_id = Column(String(64), ForeignKey("cases.id"), nullable=False)
    trace_id = Column(String(64), nullable=False)
    trace_result_hash = Column(String(64), nullable=False)
    selected_accounts_json = Column(Text, nullable=False)  # list of {account_id, amount, basis}
    total_recommended_amount = Column(Numeric(18, 2), nullable=False)
    justification = Column(Text, nullable=False)
    author_id = Column(String(64), ForeignKey("users.id"), nullable=False)
    status = Column(String(16), default="draft", nullable=False)  # draft, approved, rejected
    
    # Review details
    decided_by_id = Column(String(64), ForeignKey("users.id"), nullable=True)
    decision_reason = Column(Text, nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    document_hash = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Database level check constraint: author cannot be the decision maker
    __table_args__ = (
        CheckConstraint(
            "decided_by_id IS NULL OR author_id != decided_by_id",
            name="check_author_not_approver"
        ),
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(String(64), primary_key=True)
    occurred_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    actor_user_id = Column(String(64), nullable=False)
    actor_role = Column(String(16), nullable=False)
    action = Column(String(64), nullable=False)
    target_type = Column(String(64), nullable=False)
    target_id = Column(String(64), nullable=False)
    case_id = Column(String(64), nullable=True)
    request_id = Column(String(64), nullable=True)
    reason = Column(Text, nullable=True)
    details_json = Column(Text, nullable=True)


connect_args = {"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    Base.metadata.create_all(bind=engine)
