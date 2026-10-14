"""Deterministic NahaTax workflow services."""
import json
from datetime import date, datetime
from sqlmodel import Session, select

from nahatax_models import (
    NahaTaxActionReceipt,
    NahaTaxAuditEvent,
    NahaTaxClient,
    NahaTaxClientRequirement,
    NahaTaxEngagement,
    NahaTaxException,
    NahaTaxPractice,
    NahaTaxSarsSubmission,
    NahaTaxWorkItem,
    NahaTaxEvidence,
)


def audit(session, practice_id, event_type, detail, client_id=None,
          actor_type="system", actor_name=None, entity_type=None, entity_id=None):
    event = NahaTaxAuditEvent(
        practice_id=practice_id, client_id=client_id, event_type=event_type,
        actor_type=actor_type, actor_name=actor_name,
        entity_type=entity_type, entity_id=entity_id, detail=detail,
    )
    session.add(event)
    session.flush()
    return event


def receipt(session, practice_id, action_type, status="recorded", client_id=None,
            actor_type="system", actor_name=None, target=None, result=None):
    item = NahaTaxActionReceipt(
        practice_id=practice_id, client_id=client_id, action_type=action_type,
        actor_type=actor_type, actor_name=actor_name, target=target,
        status=status, result_json=json.dumps(result or {}, default=str),
    )
    session.add(item)
    session.flush()
    return item


def calculate_readiness(session, practice_id, client_id, engagement_id=None):
    rq = select(NahaTaxClientRequirement).where(
        NahaTaxClientRequirement.practice_id == practice_id,
        NahaTaxClientRequirement.client_id == client_id,
    )
    if engagement_id is not None:
        rq = rq.where(NahaTaxClientRequirement.engagement_id == engagement_id)
    requirements = session.exec(rq).all()

    eq = select(NahaTaxException).where(
        NahaTaxException.practice_id == practice_id,
        NahaTaxException.client_id == client_id,
        NahaTaxException.status == "open",
    )
    if engagement_id is not None:
        eq = eq.where(NahaTaxException.engagement_id == engagement_id)
    exceptions = session.exec(eq).all()

    total = len(requirements)
    received = sum(1 for item in requirements if item.status in {"received", "waived"})
    missing = [item.requirement for item in requirements if item.status == "missing"]
    base = 100.0 if total == 0 else (received / total) * 100.0
    score = max(0.0, round(base - min(40.0, len(exceptions) * 10.0), 1))
    blockers = len(missing) + len(exceptions)
    status = "ready" if blockers == 0 else ("at_risk" if score >= 70 else "blocked")

    return {
        "score": score,
        "status": status,
        "requirements_total": total,
        "requirements_received": received,
        "missing_requirements": missing,
        "open_exceptions": len(exceptions),
        "blockers": blockers,
    }


def refresh_client_readiness(session, practice_id, client, engagement_id=None):
    result = calculate_readiness(session, practice_id, client.id, engagement_id)
    client.readiness_score = result["score"]
    client.updated_at = datetime.utcnow()
    session.add(client)

    if engagement_id:
        engagement = session.get(NahaTaxEngagement, engagement_id)
        if engagement:
            engagement.readiness_score = result["score"]
            engagement.updated_at = datetime.utcnow()
            session.add(engagement)
    return result


def seed_demo(session, practice_id):
    practice = session.get(NahaTaxPractice, practice_id)
    if not practice:
        raise ValueError("Practice not found")

    existing = session.exec(
        select(NahaTaxClient).where(NahaTaxClient.practice_id == practice_id)
    ).all()
    if existing:
        return {"seeded": False, "reason": "demo data already exists", "clients": len(existing)}

    rows = [
        {
            "name": "Mzansi Civils (Pty) Ltd", "vat": "VAT-SYNTH-001",
            "requirements": ["Supplier invoices — September", "Bank statement — September", "Fuel receipts — September"],
            "exceptions": [("Input VAT evidence gap", "high",
                            "3 supplier transactions have no supporting tax invoice.",
                            "Request supplier invoices before approval.", 18450.0, True, 0.96)]
        },
        {
            "name": "Thoko's Dental Studio (Pty) Ltd", "vat": "VAT-SYNTH-002",
            "requirements": ["Supplier invoices — September", "Merchant settlement report", "Bank statement — September"],
            "exceptions": [("Possible duplicate invoice", "medium",
                            "Invoice INV-1048 appears twice with the same supplier reference and amount.",
                            "Review duplicate before VAT return preparation.", 7200.0, True, 0.99)]
        },
        {
            "name": "Kopano Logistics CC", "vat": "VAT-SYNTH-003",
            "requirements": ["Supplier invoices — September", "Bank statement — September"],
            "exceptions": [
                ("VAT treatment inconsistency", "medium",
                 "A transaction was tagged as zero-rated while the source document indicates standard-rated VAT.",
                 "Accountant to verify tax treatment against source document.", 3120.0, False, 0.91),
                ("Deadline risk", "high",
                 "Return is approaching deadline and review remains incomplete.",
                 "Prioritise review and approval.", 0.0, True, 1.0),
            ]
        },
    ]

    for row in rows:
        client = NahaTaxClient(
            practice_id=practice_id, legal_name=row["name"],
            trading_name=row["name"].split(" (")[0],
            vat_number=row["vat"], email="demo@example.invalid",
            phone="+27000000000", whatsapp_number="+27000000000",
        )
        session.add(client)
        session.flush()

        engagement = NahaTaxEngagement(
            practice_id=practice_id, client_id=client.id,
            service_type="VAT", period_label="2026-09",
            due_date=date(2026, 10, 25),
        )
        session.add(engagement)
        session.flush()

        for requirement in row["requirements"]:
            session.add(NahaTaxClientRequirement(
                practice_id=practice_id, client_id=client.id,
                engagement_id=engagement.id, requirement=requirement,
                status="received" if "Bank statement" not in requirement else "missing",
                due_date=date(2026, 10, 25),
            ))

        for title, severity, explanation, action, amount, deterministic, confidence in row["exceptions"]:
            exception = NahaTaxException(
                practice_id=practice_id, client_id=client.id,
                engagement_id=engagement.id, title=title,
                severity=severity, category="VAT",
                explanation=explanation, recommended_action=action,
                amount_at_risk=amount, is_deterministic=deterministic,
                confidence=confidence,
            )
            session.add(exception)
            session.flush()

            evidence = NahaTaxEvidence(
                practice_id=practice_id, client_id=client.id,
                engagement_id=engagement.id, evidence_type="demo_source",
                fact_state="OBSERVED", claim=explanation,
                value_json=json.dumps({"synthetic": True, "exception_id": exception.id}),
                confidence=confidence, provenance="synthetic-demo",
            )
            session.add(evidence)
            session.flush()
            exception.evidence_ids = str(evidence.id)
            session.add(exception)

            session.add(NahaTaxWorkItem(
                practice_id=practice_id, client_id=client.id,
                engagement_id=engagement.id,
                employee_type="VAT Analyst" if "VAT" in title else "Compliance Monitor",
                title=title, description=explanation,
                priority="high" if severity == "high" else "normal",
                status="waiting_review", confidence=confidence,
                requires_human_approval=True, evidence_ids=str(evidence.id),
            ))

        readiness = refresh_client_readiness(session, practice_id, client, engagement.id)
        engagement.status = readiness["status"]
        session.add(engagement)

    audit(session, practice_id, "DEMO_DATA_SEEDED",
          "Synthetic NahaTax demonstration data created.", actor_name="NahaTax")
    receipt(session, practice_id, "demo_seed",
            target=f"practice:{practice_id}", result={"synthetic": True})
    session.commit()
    return {"seeded": True, "clients": len(rows)}


def dashboard_summary(session, practice_id):
    clients = session.exec(select(NahaTaxClient).where(
        NahaTaxClient.practice_id == practice_id)).all()
    exceptions = session.exec(select(NahaTaxException).where(
        NahaTaxException.practice_id == practice_id,
        NahaTaxException.status == "open")).all()
    work = session.exec(select(NahaTaxWorkItem).where(
        NahaTaxWorkItem.practice_id == practice_id,
        NahaTaxWorkItem.status.in_([ "queued", "waiting_review", "blocked" ])
    )).all()
    missing = session.exec(select(NahaTaxClientRequirement).where(
        NahaTaxClientRequirement.practice_id == practice_id,
        NahaTaxClientRequirement.status == "missing")).all()

    return {
        "clients": len(clients),
        "clients_at_risk": sum(1 for c in clients if c.readiness_score < 70),
        "open_exceptions": len(exceptions),
        "missing_documents": len(missing),
        "work_waiting": len(work),
        "money_at_risk_estimate": round(sum(e.amount_at_risk for e in exceptions), 2),
    }
