from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import date, datetime


class UserProfile(SQLModel, table=True):
    __tablename__ = "bankbook_profiles"

    whatsapp_id: str = Field(primary_key=True)
    full_name: Optional[str] = None
    net_salary: float = Field(default=0.0)
    total_debt: float = Field(default=0.0)
    credit_score: Optional[int] = None
    onboarding_completed: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Property(SQLModel, table=True):
    __tablename__ = "bankbook_properties"

    id: Optional[int] = Field(default=None, primary_key=True)
    whatsapp_id: str = Field(foreign_key="bankbook_profiles.whatsapp_id")
    address: str
    estimated_value: float
    bond_balance: float = Field(default=0.0)
    rental_income: float = Field(default=0.0)


class Insurance(SQLModel, table=True):
    __tablename__ = "bankbook_insurance"

    id: Optional[int] = Field(default=None, primary_key=True)
    whatsapp_id: str = Field(foreign_key="bankbook_profiles.whatsapp_id")
    provider: str
    premium_amount: float
    renewal_date: Optional[date] = None


class Reward(SQLModel, table=True):
    __tablename__ = "bankbook_rewards"

    id: Optional[int] = Field(default=None, primary_key=True)
    whatsapp_id: str = Field(foreign_key="bankbook_profiles.whatsapp_id")
    program: str               # "eBucks", "Discovery Miles", etc.
    balance: float = 0.0
    expiry_date: Optional[date] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class SpendEntry(SQLModel, table=True):
    __tablename__ = "bankbook_spend"

    id: Optional[int] = Field(default=None, primary_key=True)
    whatsapp_id: str = Field(foreign_key="bankbook_profiles.whatsapp_id")
    description: str
    amount: float
    category: str = "Other"
    entry_date: date = Field(default_factory=date.today)
    raw_text: str = ""


class BankBalance(SQLModel, table=True):
    __tablename__ = "bankbook_balances"

    id: Optional[int] = Field(default=None, primary_key=True)
    whatsapp_id: str = Field(foreign_key="bankbook_profiles.whatsapp_id")
    balance: float = 0.0
    data_source: str = "manual"      # "manual" | "stitch"
    stitch_user_token: Optional[str] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class DebitOrderRecord(SQLModel, table=True):
    __tablename__ = "bankbook_debit_orders"

    id: Optional[int] = Field(default=None, primary_key=True)
    whatsapp_id: str = Field(foreign_key="bankbook_profiles.whatsapp_id")
    description: str
    amount: float
    due_day: int = 1                 # Day of month
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TaxRecord(SQLModel, table=True):
    __tablename__ = "bankbook_tax"

    id: Optional[int] = Field(default=None, primary_key=True)
    whatsapp_id: str = Field(foreign_key="bankbook_profiles.whatsapp_id")
    income_type: str = "freelance"       # "freelance" | "salary_plus_rental" | "rental_only"
    annual_income: float = 0.0
    annual_expenses: float = 0.0
    rental_income: float = 0.0
    rental_expenses: float = 0.0
    age: int = 35
    medical_aid_dependants: int = 0
    # Calculated fields (stored for quick retrieval)
    annual_tax_payable: float = 0.0
    monthly_set_aside: float = 0.0
    provisional_period_1: float = 0.0
    provisional_period_2: float = 0.0
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class SavingsGoal(SQLModel, table=True):
    __tablename__ = "bankbook_goals"

    id: Optional[int] = Field(default=None, primary_key=True)
    whatsapp_id: str = Field(foreign_key="bankbook_profiles.whatsapp_id")
    label: str                           # e.g. "Car", "Holiday", "Emergency Fund"
    target_amount: float
    current_saved: float = Field(default=0.0)
    deadline: Optional[date] = None      # Target date to reach the goal
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class GoalDeposit(SQLModel, table=True):
    __tablename__ = "bankbook_goal_deposits"

    id: Optional[int] = Field(default=None, primary_key=True)
    goal_id: int = Field(foreign_key="bankbook_goals.id")
    whatsapp_id: str = Field(foreign_key="bankbook_profiles.whatsapp_id")
    amount: float
    note: Optional[str] = None
    deposit_date: date = Field(default_factory=date.today)
