import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from sqlmodel import Session, select, SQLModel
from typing import Optional

from database import engine, get_session
from models import UserProfile, Property, Insurance, Reward, TaxRecord, BankBalance, DebitOrderRecord, SpendEntry
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


# --- SARS TAX ENVELOPE ---

class TaxRequest(BaseModel):
    whatsapp_id: str
    annual_income: float
    annual_expenses: float = 0.0
    rental_income: float = 0.0
    rental_expenses: float = 0.0
    age: int = 35
    medical_aid_dependants: int = 0
    income_type: str = "freelance"

@app.post("/tax-envelope")
def upsert_tax_envelope(req: TaxRequest, session: Session = Depends(get_session)):
    from tax import calculate_tax_envelope, format_tax_message
    from datetime import datetime as dt_type

    user = session.exec(select(UserProfile).where(UserProfile.whatsapp_id == req.whatsapp_id)).first()
    if not user:
        user = UserProfile(whatsapp_id=req.whatsapp_id, net_salary=req.annual_income / 12, total_debt=0.0)
        session.add(user)
        session.commit()

    envelope = calculate_tax_envelope(
        annual_income=req.annual_income,
        annual_expenses=req.annual_expenses,
        rental_income=req.rental_income,
        rental_expenses=req.rental_expenses,
        age=req.age,
        medical_aid_dependants=req.medical_aid_dependants,
        income_type=req.income_type,
    )

    existing = session.exec(select(TaxRecord).where(TaxRecord.whatsapp_id == req.whatsapp_id)).first()
    if existing:
        existing.income_type             = req.income_type
        existing.annual_income           = req.annual_income
        existing.annual_expenses         = req.annual_expenses
        existing.rental_income           = req.rental_income
        existing.rental_expenses         = req.rental_expenses
        existing.age                     = req.age
        existing.medical_aid_dependants  = req.medical_aid_dependants
        existing.annual_tax_payable      = envelope.annual_tax_payable
        existing.monthly_set_aside       = envelope.monthly_set_aside
        existing.provisional_period_1    = envelope.provisional_period_1
        existing.provisional_period_2    = envelope.provisional_period_2
        existing.updated_at              = dt_type.utcnow()
    else:
        session.add(TaxRecord(
            whatsapp_id=req.whatsapp_id,
            income_type=req.income_type,
            annual_income=req.annual_income,
            annual_expenses=req.annual_expenses,
            rental_income=req.rental_income,
            rental_expenses=req.rental_expenses,
            age=req.age,
            medical_aid_dependants=req.medical_aid_dependants,
            annual_tax_payable=envelope.annual_tax_payable,
            monthly_set_aside=envelope.monthly_set_aside,
            provisional_period_1=envelope.provisional_period_1,
            provisional_period_2=envelope.provisional_period_2,
        ))
    session.commit()

    return {
        **envelope.__dict__,
        "whatsapp_message": format_tax_message(envelope, user_name=user.full_name or "", income_type=req.income_type),
    }


@app.get("/tax-envelope/{whatsapp_id}")
def get_tax_envelope(whatsapp_id: str, session: Session = Depends(get_session)):
    from tax import calculate_tax_envelope, format_tax_message

    user   = session.exec(select(UserProfile).where(UserProfile.whatsapp_id == whatsapp_id)).first()
    record = session.exec(select(TaxRecord).where(TaxRecord.whatsapp_id == whatsapp_id)).first()

    if not record:
        raise HTTPException(status_code=404, detail="No tax profile found. Please set up your tax envelope first.")

    envelope = calculate_tax_envelope(
        annual_income=record.annual_income,
        annual_expenses=record.annual_expenses,
        rental_income=record.rental_income,
        rental_expenses=record.rental_expenses,
        age=record.age,
        medical_aid_dependants=record.medical_aid_dependants,
        income_type=record.income_type,
    )

    return {
        **envelope.__dict__,
        "income_type": record.income_type,
        "whatsapp_message": format_tax_message(envelope, user_name=(user.full_name or "") if user else "", income_type=record.income_type),
    }


# --- SAFE-TO-SPEND ---

class BalanceRequest(BaseModel):
    whatsapp_id: str
    balance: float

class DebitRequest(BaseModel):
    whatsapp_id: str
    description: str
    amount: float
    due_day: int = 1

class RemoveDebitRequest(BaseModel):
    whatsapp_id: str
    description: str

@app.post("/safe-to-spend/balance")
def update_balance(req: BalanceRequest, session: Session = Depends(get_session)):
    from stitch import calculate_safe_to_spend, format_safe_to_spend_message
    from datetime import datetime as dt_type

    user = session.exec(select(UserProfile).where(UserProfile.whatsapp_id == req.whatsapp_id)).first()
    if not user:
        user = UserProfile(whatsapp_id=req.whatsapp_id, net_salary=0.0, total_debt=0.0)
        session.add(user)
        session.commit()

    existing = session.exec(select(BankBalance).where(BankBalance.whatsapp_id == req.whatsapp_id)).first()
    if existing:
        existing.balance    = req.balance
        existing.updated_at = dt_type.utcnow()
    else:
        session.add(BankBalance(whatsapp_id=req.whatsapp_id, balance=req.balance, data_source="manual"))
    session.commit()

    debits = session.exec(
        select(DebitOrderRecord).where(DebitOrderRecord.whatsapp_id == req.whatsapp_id, DebitOrderRecord.is_active == True)
    ).all()
    result = calculate_safe_to_spend(req.balance, [{"description": d.description, "amount": d.amount, "due_day": d.due_day} for d in debits])
    result.data_source = "manual"
    return {"status": "balance_updated", "whatsapp_message": format_safe_to_spend_message(result, user_name=user.full_name or "")}


@app.post("/safe-to-spend/debit")
def add_debit(req: DebitRequest, session: Session = Depends(get_session)):
    user = session.exec(select(UserProfile).where(UserProfile.whatsapp_id == req.whatsapp_id)).first()
    if not user:
        user = UserProfile(whatsapp_id=req.whatsapp_id, net_salary=0.0, total_debt=0.0)
        session.add(user)
        session.commit()

    existing = session.exec(
        select(DebitOrderRecord).where(
            DebitOrderRecord.whatsapp_id == req.whatsapp_id,
            DebitOrderRecord.description == req.description,
        )
    ).first()
    if existing:
        existing.amount  = req.amount
        existing.due_day = req.due_day
    else:
        session.add(DebitOrderRecord(whatsapp_id=req.whatsapp_id, description=req.description, amount=req.amount, due_day=req.due_day))
    session.commit()

    all_debits = session.exec(
        select(DebitOrderRecord).where(DebitOrderRecord.whatsapp_id == req.whatsapp_id, DebitOrderRecord.is_active == True)
    ).all()
    total = sum(d.amount for d in all_debits)
    msg = (
        f"🏦 *BankBook*\n\n"
        f"✅ Debit order saved: *{req.description}* — R{req.amount:,.0f} on the {req.due_day}th\n\n"
        f"You now have *{len(all_debits)} debit order{'s' if len(all_debits) > 1 else ''}* totalling *R{total:,.0f}/month*.\n\n"
        f"Reply 'Safe to spend?' to see your updated balance."
    )
    return {"status": "debit_saved", "whatsapp_message": msg}


@app.post("/safe-to-spend/debit/remove")
def remove_debit(req: RemoveDebitRequest, session: Session = Depends(get_session)):
    record = session.exec(
        select(DebitOrderRecord).where(
            DebitOrderRecord.whatsapp_id == req.whatsapp_id,
            DebitOrderRecord.description.ilike(f"%{req.description}%"),
        )
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail=f"No debit order matching '{req.description}' found.")
    record.is_active = False
    session.commit()
    msg = f"🏦 *BankBook*\n\n✅ Debit order *{record.description}* (R{record.amount:,.0f}) removed from your BankBook."
    return {"status": "debit_removed", "whatsapp_message": msg}


@app.get("/safe-to-spend/{whatsapp_id}")
def get_safe_to_spend(whatsapp_id: str, session: Session = Depends(get_session)):
    from stitch import calculate_safe_to_spend, format_safe_to_spend_message, get_account_balances

    user    = session.exec(select(UserProfile).where(UserProfile.whatsapp_id == whatsapp_id)).first()
    balance = session.exec(select(BankBalance).where(BankBalance.whatsapp_id == whatsapp_id)).first()
    debits  = session.exec(
        select(DebitOrderRecord).where(DebitOrderRecord.whatsapp_id == whatsapp_id, DebitOrderRecord.is_active == True)
    ).all()

    if not balance:
        raise HTTPException(status_code=404, detail="No balance on file.")

    current_balance = balance.balance
    source          = balance.data_source

    # If Stitch token available, fetch live balance
    if balance.stitch_user_token:
        try:
            accounts = get_account_balances(balance.stitch_user_token)
            if accounts:
                current_balance = sum(a["available_balance"] for a in accounts)
                source = "stitch"
        except Exception:
            pass  # Fall back to stored balance

    result = calculate_safe_to_spend(
        current_balance,
        [{"description": d.description, "amount": d.amount, "due_day": d.due_day} for d in debits],
    )
    result.data_source = source
    return {
        "safe_to_spend": result.safe_to_spend,
        "bank_balance":  result.bank_balance,
        "upcoming_debits": result.total_upcoming_debits,
        "whatsapp_message": format_safe_to_spend_message(result, user_name=(user.full_name or "") if user else ""),
    }


@app.get("/safe-to-spend/stitch-link")
def stitch_link(whatsapp_id: str, redirect_uri: str):
    from stitch import build_stitch_link_url, STITCH_CLIENT_ID
    if not STITCH_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Stitch integration not configured.")
    link_url = build_stitch_link_url(redirect_uri=redirect_uri, state=whatsapp_id)
    return {"link_url": link_url, "whatsapp_id": whatsapp_id}


# --- BUDGET COACH ---

class BudgetLogRequest(BaseModel):
    whatsapp_id: str
    text: str

@app.post("/budget/log")
def log_spend(req: BudgetLogRequest, session: Session = Depends(get_session)):
    from budget import parse_spend_message, categorise, format_spend_confirm
    from datetime import date as date_type

    parsed = parse_spend_message(req.text)
    if not parsed:
        return {"status": "parse_failed"}

    user = session.exec(select(UserProfile).where(UserProfile.whatsapp_id == req.whatsapp_id)).first()
    if not user:
        user = UserProfile(whatsapp_id=req.whatsapp_id, net_salary=0.0, total_debt=0.0)
        session.add(user)
        session.commit()

    category = categorise(parsed["description"])
    entry = SpendEntry(
        whatsapp_id=req.whatsapp_id,
        description=parsed["description"],
        amount=parsed["amount"],
        category=category,
        entry_date=date_type.today(),
        raw_text=req.text,
    )
    session.add(entry)
    session.commit()

    return {
        "status": "logged",
        "amount": parsed["amount"],
        "description": parsed["description"],
        "category": category,
        "whatsapp_message": format_spend_confirm(parsed["description"], parsed["amount"], category),
    }


@app.get("/budget/summary/{whatsapp_id}")
def budget_summary(whatsapp_id: str, session: Session = Depends(get_session)):
    from budget import build_budget_summary, format_budget_summary
    from datetime import date as date_type

    user  = session.exec(select(UserProfile).where(UserProfile.whatsapp_id == whatsapp_id)).first()
    today = date_type.today()
    month_start = date_type(today.year, today.month, 1)

    entries = session.exec(
        select(SpendEntry).where(
            SpendEntry.whatsapp_id == whatsapp_id,
            SpendEntry.entry_date >= month_start,
        )
    ).all()

    if not entries:
        raise HTTPException(status_code=404, detail="No spending logged this month.")

    month_label = today.strftime("%B %Y")
    summary = build_budget_summary(
        entries=[{"category": e.category, "amount": e.amount} for e in entries],
        net_salary=user.net_salary if user else 0.0,
        month_label=month_label,
    )
    return {
        "month": month_label,
        "total_spent": summary.total_spent,
        "by_category": summary.by_category,
        "over_budget": summary.over_budget,
        "whatsapp_message": format_budget_summary(summary),
    }
