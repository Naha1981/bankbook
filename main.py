import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from sqlmodel import Session, select, SQLModel
from typing import Optional

from database import engine, get_session
from models import UserProfile, Property, Insurance
from calculations import calculate_affordability, insurance_savings_estimate


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
