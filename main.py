import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from sqlmodel import Session, select, SQLModel
from typing import Optional

from database import engine, get_session
from models import UserProfile, Property, Insurance, Reward
from calculations import calculate_affordability, insurance_savings_estimate
from anomaly import detect_anomalies, format_anomaly_alert
from simulator import simulate_payoffs, format_simulator_message


# --- LIFESPAN (replaces deprecated @app.on_event) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    SQLModel.metadata.create_all(engine)
    yield


app = FastAPI(
    title="BankBook AI OS",
    description="South Africa's AI Financial Operating System — Property, Insurance & Bond Calculations",
    version="1.0.0",
    lifespan=lifespan,
)


# --- REQUEST/RESPONSE MODELS ---

class ProfileRequest(BaseModel):
    whatsapp_id: str
    full_name: Optional[str] = None
    net_salary: float
    total_debt: float = 0.0

class AffordabilityRequest(BaseModel):
    whatsapp_id: str
    property_price: float

class PropertyRequest(BaseModel):
    whatsapp_id: str
    address: str
    estimated_value: float
    bond_balance: float = 0.0
    rental_income: float = 0.0

class InsuranceRequest(BaseModel):
    whatsapp_id: str
    provider: str
    premium_amount: float


# --- HEALTH CHECK ---

@app.get("/")
def health():
    return {"status": "online", "service": "BankBook Brain"}


# --- PROFILE MANAGEMENT ---

@app.post("/profile")
def upsert_profile(req: ProfileRequest, session: Session = Depends(get_session)):
    user = session.exec(select(UserProfile).where(UserProfile.whatsapp_id == req.whatsapp_id)).first()
    if not user:
        user = UserProfile(
            whatsapp_id=req.whatsapp_id,
            full_name=req.full_name,
            net_salary=req.net_salary,
            total_debt=req.total_debt,
            onboarding_completed=True,
        )
    else:
        if req.full_name:
            user.full_name = req.full_name
        user.net_salary = req.net_salary
        user.total_debt = req.total_debt
        user.onboarding_completed = True

    session.add(user)
    session.commit()
    session.refresh(user)
    return {"status": "profile_updated", "whatsapp_id": user.whatsapp_id}


@app.get("/profile/{whatsapp_id}")
def get_profile(whatsapp_id: str, session: Session = Depends(get_session)):
    user = session.exec(select(UserProfile).where(UserProfile.whatsapp_id == whatsapp_id)).first()
    if not user:
        raise HTTPException(status_code=404, detail="Profile not found. Please set up your BankBook first.")
    return user


# --- CORE LOGIC: BOND AFFORDABILITY ---

@app.post("/calculate-affordability")
def affordability(req: AffordabilityRequest, session: Session = Depends(get_session)):
    user = session.exec(select(UserProfile).where(UserProfile.whatsapp_id == req.whatsapp_id)).first()

    if not user or user.net_salary == 0:
        return {
            "status": "missing_data",
            "message": "I don't have your salary on record yet. Please update your BankBook profile first.",
        }

    result = calculate_affordability(
        salary=user.net_salary,
        debt=user.total_debt,
        price=req.property_price,
    )
    result["status"] = "success"
    result["whatsapp_id"] = req.whatsapp_id
    result["property_price"] = req.property_price
    return result


# --- PROPERTY MANAGEMENT ---

@app.post("/property")
def add_property(req: PropertyRequest, session: Session = Depends(get_session)):
    user = session.exec(select(UserProfile).where(UserProfile.whatsapp_id == req.whatsapp_id)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User profile not found.")

    prop = Property(
        whatsapp_id=req.whatsapp_id,
        address=req.address,
        estimated_value=req.estimated_value,
        bond_balance=req.bond_balance,
        rental_income=req.rental_income,
    )
    session.add(prop)
    session.commit()
    session.refresh(prop)

    equity = req.estimated_value - req.bond_balance
    return {
        "status": "property_saved",
        "property_id": prop.id,
        "address": prop.address,
        "estimated_value": prop.estimated_value,
        "equity": round(equity, 2),
    }


@app.get("/properties/{whatsapp_id}")
def list_properties(whatsapp_id: str, session: Session = Depends(get_session)):
    properties = session.exec(select(Property).where(Property.whatsapp_id == whatsapp_id)).all()
    return {"properties": properties}


# --- INSURANCE ---

@app.post("/insurance")
def add_insurance(req: InsuranceRequest, session: Session = Depends(get_session)):
    policy = Insurance(
        whatsapp_id=req.whatsapp_id,
        provider=req.provider,
        premium_amount=req.premium_amount,
    )
    session.add(policy)
    session.commit()
    session.refresh(policy)

    savings = insurance_savings_estimate(req.premium_amount)
    return {
        "status": "insurance_saved",
        "policy_id": policy.id,
        "provider": policy.provider,
        **savings,
    }


@app.get("/insurance/{whatsapp_id}")
def list_insurance(whatsapp_id: str, session: Session = Depends(get_session)):
    policies = session.exec(select(Insurance).where(Insurance.whatsapp_id == whatsapp_id)).all()
    return {"policies": policies}


# --- ALL USERS (for Morning Briefing scheduler) ---

@app.get("/users")
def list_users(session: Session = Depends(get_session)):
    users = session.exec(select(UserProfile)).all()
    return {"users": users}


# --- MORNING BRIEFING (on-demand or called by scheduler) ---

@app.get("/briefing/{whatsapp_id}")
def get_briefing(whatsapp_id: str, session: Session = Depends(get_session)):
    from briefing import build_briefing_message

    user = session.exec(select(UserProfile).where(UserProfile.whatsapp_id == whatsapp_id)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    properties = session.exec(select(Property).where(Property.whatsapp_id == whatsapp_id)).all()
    insurance  = session.exec(select(Insurance).where(Insurance.whatsapp_id == whatsapp_id)).all()

    message = build_briefing_message(
        user_name=user.full_name or "",
        net_salary=user.net_salary,
        total_debt=user.total_debt,
        properties=[p.model_dump() for p in properties],
        insurance_count=len(insurance),
    )
    return {"whatsapp_id": whatsapp_id, "message": message}


# --- ANOMALY CHECK ---

@app.get("/anomaly-check/{whatsapp_id}")
def anomaly_check(whatsapp_id: str, session: Session = Depends(get_session)):
    user = session.exec(select(UserProfile).where(UserProfile.whatsapp_id == whatsapp_id)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    properties = session.exec(select(Property).where(Property.whatsapp_id == whatsapp_id)).all()
    insurance  = session.exec(select(Insurance).where(Insurance.whatsapp_id == whatsapp_id)).all()

    report = detect_anomalies(
        whatsapp_id=whatsapp_id,
        net_salary=user.net_salary,
        total_debt=user.total_debt,
        properties=[p.model_dump() for p in properties],
        insurance_count=len(insurance),
    )
    message = format_anomaly_alert(report, user_name=user.full_name or "")

    return {
        "whatsapp_id": whatsapp_id,
        "anomaly_count": len(report.anomalies),
        "critical_count": report.critical_count,
        "anomalies": [
            {"code": a.code, "severity": a.severity, "message": a.message, "action": a.action}
            for a in report.anomalies
        ],
        "whatsapp_message": message,
    }


# --- PRE-APPROVAL SIMULATOR ---

class SimulatorRequest(BaseModel):
    whatsapp_id: str
    debts_to_simulate: list[dict]  # [{"label": "Car loan", "monthly_amount": 5000}]

@app.post("/pre-approval-simulator")
def pre_approval_simulator(req: SimulatorRequest, session: Session = Depends(get_session)):
    user = session.exec(select(UserProfile).where(UserProfile.whatsapp_id == req.whatsapp_id)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found. Please set up your BankBook profile first.")
    if user.net_salary == 0:
        raise HTTPException(status_code=400, detail="Salary not set. Please update your profile first.")

    result = simulate_payoffs(
        net_salary=user.net_salary,
        total_debt=user.total_debt,
        debts_to_simulate=req.debts_to_simulate,
    )
    result["whatsapp_message"] = format_simulator_message(result, user_name=user.full_name or "")
    return result


# --- REWARDS TRACKER ---

class RewardsRequest(BaseModel):
    whatsapp_id: str
    rewards: list[dict]  # [{"program": "eBucks", "balance": 5000, "expiry_date": "2025-06-30"}]

@app.post("/rewards")
def upsert_rewards(req: RewardsRequest, session: Session = Depends(get_session)):
    from datetime import date as date_type
    from rewards import evaluate_rewards, format_rewards_message

    user = session.exec(select(UserProfile).where(UserProfile.whatsapp_id == req.whatsapp_id)).first()
    if not user:
        user = UserProfile(whatsapp_id=req.whatsapp_id, net_salary=0.0, total_debt=0.0)
        session.add(user)
        session.commit()

    from datetime import datetime as dt_type
    for r in req.rewards:
        program = r.get("program", "")
        balance = float(r.get("balance", 0))
        exp_str = r.get("expiry_date")
        expiry  = date_type.fromisoformat(exp_str) if exp_str else None

        existing = session.exec(
            select(Reward).where(Reward.whatsapp_id == req.whatsapp_id, Reward.program == program)
        ).first()

        if existing:
            existing.balance      = balance
            existing.expiry_date  = expiry
            existing.updated_at   = dt_type.utcnow()
        else:
            session.add(Reward(whatsapp_id=req.whatsapp_id, program=program, balance=balance, expiry_date=expiry))

    session.commit()

    saved = session.exec(select(Reward).where(Reward.whatsapp_id == req.whatsapp_id)).all()
    report = evaluate_rewards(req.whatsapp_id, [
        {"program": rw.program, "balance": rw.balance,
         "expiry_date": rw.expiry_date.isoformat() if rw.expiry_date else None}
        for rw in saved
    ])
    return {
        "status": "rewards_saved",
        "total_rand_value": report.total_rand_value,
        "urgent_programs": report.urgent_programs,
        "whatsapp_message": format_rewards_message(report, user_name=user.full_name or ""),
    }


@app.get("/rewards/{whatsapp_id}")
def get_rewards(whatsapp_id: str, session: Session = Depends(get_session)):
    from rewards import evaluate_rewards, format_rewards_message

    user = session.exec(select(UserProfile).where(UserProfile.whatsapp_id == whatsapp_id)).first()
    saved = session.exec(select(Reward).where(Reward.whatsapp_id == whatsapp_id)).all()

    report = evaluate_rewards(whatsapp_id, [
        {"program": rw.program, "balance": rw.balance,
         "expiry_date": rw.expiry_date.isoformat() if rw.expiry_date else None}
        for rw in saved
    ])
    return {
        "rewards": [{"program": rw.program, "balance": rw.balance, "expiry_date": str(rw.expiry_date)} for rw in saved],
        "total_rand_value": report.total_rand_value,
        "urgent_programs": report.urgent_programs,
        "whatsapp_message": format_rewards_message(report, user_name=(user.full_name or "") if user else ""),
    }
