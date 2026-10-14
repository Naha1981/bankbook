"""NahaTax HTTP API.

SARS production access is deliberately blocked behind an explicit sandbox adapter.
"""
import hashlib
import json
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from database import get_session
from nahatax_models import (
    NahaTaxActionReceipt, NahaTaxAuditEvent, NahaTaxClient,
    NahaTaxClientRequirement, NahaTaxDocument, NahaTaxEvidence,
    NahaTaxException, NahaTaxPractice, NahaTaxSarsSubmission,
    NahaTaxWorkItem,
)
from nahatax_service import (
    audit, dashboard_summary, receipt, refresh_client_readiness, seed_demo,
)

router = APIRouter(prefix="/api/v1/nahatax", tags=["NahaTax"])


def practice_context(
    x_practice_id: Optional[int] = Header(default=1, alias="X-Practice-Id"),
) -> int:
    return x_practice_id or 1


class ClientCreate(BaseModel):
    legal_name: str
    trading_name: Optional[str] = None
    vat_number: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    whatsapp_number: Optional[str] = None


class RequirementCreate(BaseModel):
    requirement: str
    engagement_id: Optional[int] = None
    due_date: Optional[date] = None


class DocumentCreate(BaseModel):
    filename: str
    document_type: str = "unknown"
    source: str = "browser"
    engagement_id: Optional[int] = None
    checksum_sha256: Optional[str] = None


class ExceptionDecision(BaseModel):
    decision: str = Field(pattern="^(approved|rejected|request_more_info)$")
    reviewer: str
    comment: Optional[str] = None


class SandboxSubmission(BaseModel):
    client_id: int
    engagement_id: Optional[int] = None
    submission_type: str = "VAT201"
    payload: dict = {}
    approved_by: Optional[str] = None


@router.get("/health")
def health():
    return {
        "service": "NahaTax",
        "status": "online",
        "sars_mode": "sandbox",
        "repo": "Naha1981/bankbook",
    }


@router.post("/demo/seed")
def seed_demo_data(
    session: Session = Depends(get_session),
    practice_id: int = Depends(practice_context),
):
    practice = session.get(NahaTaxPractice, practice_id)
    if not practice:
        practice = NahaTaxPractice(
            id=practice_id,
            name="NahaLabs Demo Accounting Practice",
            slug=f"demo-{practice_id}",
        )
        session.add(practice)
        session.commit()
    return seed_demo(session, practice_id)


@router.get("/overview")
def overview(
    session: Session = Depends(get_session),
    practice_id: int = Depends(practice_context),
):
    practice = session.get(NahaTaxPractice, practice_id)
    if not practice:
        raise HTTPException(status_code=404, detail="Practice not found")
    return {"practice": practice, "summary": dashboard_summary(session, practice_id)}


@router.post("/clients")
def create_client(
    payload: ClientCreate,
    session: Session = Depends(get_session),
    practice_id: int = Depends(practice_context),
):
    practice = session.get(NahaTaxPractice, practice_id)
    if not practice:
        practice = NahaTaxPractice(
            id=practice_id,
            name=f"NahaTax Practice {practice_id}",
            slug=f"practice-{practice_id}",
        )
        session.add(practice)
        session.flush()

    client = NahaTaxClient(practice_id=practice_id, **payload.model_dump())
    session.add(client)
    session.flush()

    audit(session, practice_id, "CLIENT_CREATED", client.legal_name,
          client_id=client.id, entity_type="client", entity_id=client.id)
    receipt(session, practice_id, "client_created",
            client_id=client.id, target=f"client:{client.id}")
    session.commit()
    session.refresh(client)
    return client


@router.get("/clients")
def list_clients(
    session: Session = Depends(get_session),
    practice_id: int = Depends(practice_context),
):
    return session.exec(select(NahaTaxClient).where(
        NahaTaxClient.practice_id == practice_id
    )).all()


@router.get("/clients/{client_id}")
def get_client(
    client_id: int,
    session: Session = Depends(get_session),
    practice_id: int = Depends(practice_context),
):
    client = session.exec(select(NahaTaxClient).where(
        NahaTaxClient.id == client_id,
        NahaTaxClient.practice_id == practice_id,
    )).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    readiness = refresh_client_readiness(session, practice_id, client)
    session.commit()
    return {"client": client, "readiness": readiness}


@router.post("/clients/{client_id}/requirements")
def add_requirement(
    client_id: int,
    payload: RequirementCreate,
    session: Session = Depends(get_session),
    practice_id: int = Depends(practice_context),
):
    client = session.exec(select(NahaTaxClient).where(
        NahaTaxClient.id == client_id,
        NahaTaxClient.practice_id == practice_id,
    )).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    req = NahaTaxClientRequirement(
        practice_id=practice_id, client_id=client_id,
        requirement=payload.requirement, engagement_id=payload.engagement_id,
        due_date=payload.due_date,
    )
    session.add(req)
    audit(session, practice_id, "DOCUMENT_REQUIREMENT_CREATED",
          payload.requirement, client_id=client_id, entity_type="requirement")
    session.commit()
    return req


@router.post("/clients/{client_id}/documents")
def add_document(
    client_id: int,
    payload: DocumentCreate,
    session: Session = Depends(get_session),
    practice_id: int = Depends(practice_context),
):
    client = session.exec(select(NahaTaxClient).where(
        NahaTaxClient.id == client_id,
        NahaTaxClient.practice_id == practice_id,
    )).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    doc = NahaTaxDocument(
        practice_id=practice_id, client_id=client_id,
        filename=payload.filename, document_type=payload.document_type,
        source=payload.source, engagement_id=payload.engagement_id,
        checksum_sha256=payload.checksum_sha256,
    )
    session.add(doc)
    session.flush()

    audit(session, practice_id, "DOCUMENT_RECEIVED", payload.filename,
          client_id=client_id, entity_type="document", entity_id=doc.id)
    receipt(session, practice_id, "document_received",
            client_id=client_id, target=f"document:{doc.id}")
    session.commit()
    session.refresh(doc)
    return doc


@router.get("/clients/{client_id}/evidence")
def client_evidence(
    client_id: int,
    session: Session = Depends(get_session),
    practice_id: int = Depends(practice_context),
):
    return session.exec(select(NahaTaxEvidence).where(
        NahaTaxEvidence.client_id == client_id,
        NahaTaxEvidence.practice_id == practice_id,
    )).all()


@router.get("/work")
def work_queue(
    status: Optional[str] = None,
    employee_type: Optional[str] = None,
    session: Session = Depends(get_session),
    practice_id: int = Depends(practice_context),
):
    query = select(NahaTaxWorkItem).where(
        NahaTaxWorkItem.practice_id == practice_id
    )
    if status:
        query = query.where(NahaTaxWorkItem.status == status)
    if employee_type:
        query = query.where(NahaTaxWorkItem.employee_type == employee_type)
    return session.exec(query.order_by(NahaTaxWorkItem.created_at.desc())).all()


@router.get("/exceptions")
def exceptions(
    status: Optional[str] = "open",
    session: Session = Depends(get_session),
    practice_id: int = Depends(practice_context),
):
    query = select(NahaTaxException).where(
        NahaTaxException.practice_id == practice_id
    )
    if status:
        query = query.where(NahaTaxException.status == status)
    return session.exec(query.order_by(
        NahaTaxException.created_at.desc()
    )).all()


@router.post("/exceptions/{exception_id}/decision")
def decide_exception(
    exception_id: int,
    payload: ExceptionDecision,
    session: Session = Depends(get_session),
    practice_id: int = Depends(practice_context),
):
    exception = session.exec(select(NahaTaxException).where(
        NahaTaxException.id == exception_id,
        NahaTaxException.practice_id == practice_id,
    )).first()
    if not exception:
        raise HTTPException(status_code=404, detail="Exception not found")

    exception.status = {
        "approved": "approved",
        "rejected": "rejected",
        "request_more_info": "awaiting_client",
    }[payload.decision]
    exception.resolved_at = (
        datetime.utcnow() if payload.decision != "request_more_info" else None
    )
    session.add(exception)

    audit(
        session, practice_id, "EXCEPTION_DECISION",
        f"{payload.decision}: {exception.title}",
        client_id=exception.client_id, actor_type="human",
        actor_name=payload.reviewer, entity_type="exception",
        entity_id=exception.id,
    )
    receipt(
        session, practice_id, "exception_decision",
        client_id=exception.client_id, actor_type="human",
        actor_name=payload.reviewer, target=f"exception:{exception.id}",
        result={"decision": payload.decision, "comment": payload.comment},
    )
    session.commit()
    return exception


@router.get("/audit")
def audit_log(
    limit: int = 100,
    session: Session = Depends(get_session),
    practice_id: int = Depends(practice_context),
):
    return session.exec(
        select(NahaTaxAuditEvent)
        .where(NahaTaxAuditEvent.practice_id == practice_id)
        .order_by(NahaTaxAuditEvent.created_at.desc())
        .limit(min(limit, 500))
    ).all()


@router.get("/receipts")
def action_receipts(
    limit: int = 100,
    session: Session = Depends(get_session),
    practice_id: int = Depends(practice_context),
):
    return session.exec(
        select(NahaTaxActionReceipt)
        .where(NahaTaxActionReceipt.practice_id == practice_id)
        .order_by(NahaTaxActionReceipt.created_at.desc())
        .limit(min(limit, 500))
    ).all()


@router.get("/sars/status")
def sars_status():
    return {
        "adapter": "sars",
        "mode": "sandbox",
        "production_enabled": False,
        "reason": "Production SARS access requires the appropriate authorised channel and credentials.",
        "supported_submission_types": ["VAT201", "PAYE"],
    }


@router.post("/sars/sandbox/prepare")
def prepare_sars_submission(
    payload: SandboxSubmission,
    session: Session = Depends(get_session),
    practice_id: int = Depends(practice_context),
):
    client = session.exec(select(NahaTaxClient).where(
        NahaTaxClient.id == payload.client_id,
        NahaTaxClient.practice_id == practice_id,
    )).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    serialised = json.dumps(
        payload.payload, sort_keys=True, separators=(",", ":")
    )
    payload_hash = hashlib.sha256(serialised.encode("utf-8")).hexdigest()

    submission = NahaTaxSarsSubmission(
        practice_id=practice_id, client_id=payload.client_id,
        engagement_id=payload.engagement_id,
        submission_type=payload.submission_type, mode="sandbox",
        status="ready" if payload.approved_by else "draft",
        payload_hash=payload_hash,
        response_json=json.dumps({"sandbox": True, "would_submit": True}),
    )
    session.add(submission)
    session.flush()

    audit(
        session, practice_id, "SARS_SANDBOX_PREPARED",
        f"{payload.submission_type} sandbox payload prepared.",
        client_id=payload.client_id,
        actor_type="human" if payload.approved_by else "system",
        actor_name=payload.approved_by,
        entity_type="sars_submission", entity_id=submission.id,
    )
    receipt(
        session, practice_id, "sars_submission_prepared",
        client_id=payload.client_id,
        actor_type="human" if payload.approved_by else "system",
        actor_name=payload.approved_by,
        target=f"sars_submission:{submission.id}",
        result={
            "mode": "sandbox", "payload_hash": payload_hash,
            "would_submit": True,
        },
    )
    session.commit()
    return submission


@router.get("/employees")
def employees():
    return [
        {"type": "Client Intake Employee", "purpose": "collect and chase client evidence"},
        {"type": "Document Clerk", "purpose": "classify and extract documents"},
        {"type": "VAT Analyst", "purpose": "review VAT evidence and exceptions"},
        {"type": "Reconciliation Clerk", "purpose": "reconcile accounting inputs"},
        {"type": "Compliance Monitor", "purpose": "monitor deadlines and blockers"},
        {"type": "Tax Researcher", "purpose": "prepare source-backed tax research"},
        {"type": "Review Assistant", "purpose": "prepare accountant review packs"},
        {"type": "Client Communicator", "purpose": "request and explain missing information"},
        {"type": "Evidence Clerk", "purpose": "maintain provenance and action receipts"},
    ]
