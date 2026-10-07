"""NahaTax domain models.

BankBook remains the underlying financial engine. NahaTax adds the accountant-practice
workflow, evidence ledger, human approval and SARS adapter boundary.
"""
from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class NahaTaxPractice(SQLModel, table=True):
    __tablename__ = "nahatax_practices"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    slug: str = Field(index=True, unique=True)
    status: str = "active"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class NahaTaxPracticeUser(SQLModel, table=True):
    __tablename__ = "nahatax_practice_users"
    id: Optional[int] = Field(default=None, primary_key=True)
    practice_id: int = Field(index=True, foreign_key="nahatax_practices.id")
    full_name: str
    email: str
    role: str = "accountant"
    active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)


class NahaTaxClient(SQLModel, table=True):
    __tablename__ = "nahatax_clients"
    id: Optional[int] = Field(default=None, primary_key=True)
    practice_id: int = Field(index=True, foreign_key="nahatax_practices.id")
    legal_name: str
    trading_name: Optional[str] = None
    registration_number: Optional[str] = None
    vat_number: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    whatsapp_number: Optional[str] = None
    tax_status: str = "active"
    readiness_score: float = 0.0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class NahaTaxEngagement(SQLModel, table=True):
    __tablename__ = "nahatax_engagements"
    id: Optional[int] = Field(default=None, primary_key=True)
    practice_id: int = Field(index=True, foreign_key="nahatax_practices.id")
    client_id: int = Field(index=True, foreign_key="nahatax_clients.id")
    service_type: str = "VAT"
    period_label: str
    status: str = "in_progress"
    due_date: Optional[date] = None
    readiness_score: float = 0.0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class NahaTaxObligation(SQLModel, table=True):
    __tablename__ = "nahatax_obligations"
    id: Optional[int] = Field(default=None, primary_key=True)
    practice_id: int = Field(index=True, foreign_key="nahatax_practices.id")
    client_id: int = Field(index=True, foreign_key="nahatax_clients.id")
    engagement_id: Optional[int] = Field(default=None, index=True)
    obligation_type: str = "VAT201"
    period_label: str
    due_date: Optional[date] = None
    status: str = "open"
    risk_level: str = "medium"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class NahaTaxDocument(SQLModel, table=True):
    __tablename__ = "nahatax_documents"
    id: Optional[int] = Field(default=None, primary_key=True)
    practice_id: int = Field(index=True, foreign_key="nahatax_practices.id")
    client_id: int = Field(index=True, foreign_key="nahatax_clients.id")
    engagement_id: Optional[int] = Field(default=None, index=True)
    filename: str
    document_type: str = "unknown"
    source: str = "browser"
    received_at: datetime = Field(default_factory=datetime.utcnow)
    checksum_sha256: Optional[str] = None
    extraction_status: str = "pending"
    review_status: str = "pending"
    extracted_reference: Optional[str] = None
    amount_excl_vat: Optional[float] = None
    vat_amount: Optional[float] = None
    amount_incl_vat: Optional[float] = None


class NahaTaxEvidence(SQLModel, table=True):
    __tablename__ = "nahatax_evidence"
    id: Optional[int] = Field(default=None, primary_key=True)
    practice_id: int = Field(index=True, foreign_key="nahatax_practices.id")
    client_id: int = Field(index=True, foreign_key="nahatax_clients.id")
    engagement_id: Optional[int] = Field(default=None, index=True)
    evidence_type: str
    fact_state: str = "OBSERVED"
    claim: str
    value_json: str
    source_document_id: Optional[int] = Field(default=None, index=True)
    confidence: float = 1.0
    provenance: str = "system"
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class NahaTaxException(SQLModel, table=True):
    __tablename__ = "nahatax_exceptions"
    id: Optional[int] = Field(default=None, primary_key=True)
    practice_id: int = Field(index=True, foreign_key="nahatax_practices.id")
    client_id: int = Field(index=True, foreign_key="nahatax_clients.id")
    engagement_id: Optional[int] = Field(default=None, index=True)
    title: str
    severity: str = "medium"
    category: str = "review"
    explanation: str
    recommended_action: str
    status: str = "open"
    evidence_ids: str = ""
    amount_at_risk: float = 0.0
    is_deterministic: bool = False
    confidence: float = 0.0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None


class NahaTaxWorkItem(SQLModel, table=True):
    __tablename__ = "nahatax_work_items"
    id: Optional[int] = Field(default=None, primary_key=True)
    practice_id: int = Field(index=True, foreign_key="nahatax_practices.id")
    client_id: Optional[int] = Field(default=None, index=True)
    engagement_id: Optional[int] = Field(default=None, index=True)
    employee_type: str
    title: str
    description: str
    priority: str = "normal"
    status: str = "queued"
    confidence: float = 0.0
    requires_human_approval: bool = True
    evidence_ids: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class NahaTaxApproval(SQLModel, table=True):
    __tablename__ = "nahatax_approvals"
    id: Optional[int] = Field(default=None, primary_key=True)
    practice_id: int = Field(index=True, foreign_key="nahatax_practices.id")
    client_id: Optional[int] = Field(default=None, index=True)
    entity_type: str
    entity_id: int
    decision: str
    reviewer: str
    comment: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class NahaTaxActionReceipt(SQLModel, table=True):
    __tablename__ = "nahatax_action_receipts"
    id: Optional[int] = Field(default=None, primary_key=True)
    practice_id: int = Field(index=True, foreign_key="nahatax_practices.id")
    client_id: Optional[int] = Field(default=None, index=True)
    action_type: str
    actor_type: str = "system"
    actor_name: Optional[str] = None
    target: Optional[str] = None
    status: str = "recorded"
    external_reference: Optional[str] = None
    result_json: str = "{}"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class NahaTaxAuditEvent(SQLModel, table=True):
    __tablename__ = "nahatax_audit_events"
    id: Optional[int] = Field(default=None, primary_key=True)
    practice_id: int = Field(index=True, foreign_key="nahatax_practices.id")
    client_id: Optional[int] = Field(default=None, index=True)
    event_type: str
    actor_type: str = "system"
    actor_name: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    detail: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


class NahaTaxClientRequirement(SQLModel, table=True):
    __tablename__ = "nahatax_client_requirements"
    id: Optional[int] = Field(default=None, primary_key=True)
    practice_id: int = Field(index=True, foreign_key="nahatax_practices.id")
    client_id: int = Field(index=True, foreign_key="nahatax_clients.id")
    engagement_id: Optional[int] = Field(default=None, index=True)
    requirement: str
    status: str = "missing"
    due_date: Optional[date] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class NahaTaxSarsSubmission(SQLModel, table=True):
    __tablename__ = "nahatax_sars_submissions"
    id: Optional[int] = Field(default=None, primary_key=True)
    practice_id: int = Field(index=True, foreign_key="nahatax_practices.id")
    client_id: int = Field(index=True, foreign_key="nahatax_clients.id")
    engagement_id: Optional[int] = Field(default=None, index=True)
    submission_type: str = "VAT201"
    mode: str = "sandbox"
    status: str = "draft"
    external_reference: Optional[str] = None
    payload_hash: Optional[str] = None
    submitted_at: Optional[datetime] = None
    response_json: str = "{}"
    created_at: datetime = Field(default_factory=datetime.utcnow)
