"""
BankBook SARS Tax Envelope — Provisional tax calculator for freelancers & property investors.
Calculates monthly "set-aside" amounts so users are never surprised by SARS.

Covers:
- Freelancers / sole traders (income tax + VAT threshold)
- Property investors (rental income tax)
- Side-hustle earners (above the R83,100 threshold for provisional tax)

Tax year: March 1 – February 28/29
Provisional tax deadlines: August 31 (1st period) & February 28 (2nd period)
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


# ─── 2024/2025 SARS Tax Tables (South Africa) ─────────────────────────────────

TAX_BRACKETS = [
    (237_100,    0.18, 0),
    (370_500,    0.26, 42_678),
    (512_800,    0.31, 77_362),
    (673_000,    0.36, 121_475),
    (857_900,    0.39, 179_147),
    (1_817_000,  0.41, 251_258),
    (float("inf"), 0.45, 644_489),
]

PRIMARY_REBATE      = 17_235     # Under 65
SECONDARY_REBATE    = 9_444      # 65–74
TERTIARY_REBATE     = 3_145      # 75+
TAX_THRESHOLD       = 95_750     # Below this: no income tax (under 65)
VAT_THRESHOLD       = 1_000_000  # Register for VAT above this annual turnover
PROVISIONAL_THRESHOLD = 30_000   # Must pay provisional tax if other income > R30,000

# UIF: 1% of gross (capped at R17,872/month earnings)
UIF_RATE      = 0.01
UIF_CAP_MONTH = 17_872

# Medical aid tax credits (2024/2025)
MEDICAL_CREDIT_MAIN        = 364   # Per month for principal member
MEDICAL_CREDIT_DEPENDANT_1 = 364   # Per month for first dependant
MEDICAL_CREDIT_ADDITIONAL  = 246   # Per month for each additional dependant


@dataclass
class TaxEnvelope:
    annual_taxable_income: float
    annual_tax_before_rebates: float
    annual_rebate: float
    annual_medical_credit: float
    annual_tax_payable: float
    effective_rate_pct: float
    monthly_set_aside: float          # What to put away each month
    provisional_period_1: float       # Due end August
    provisional_period_2: float       # Due end February
    vat_registration_required: bool
    uif_monthly: float
    total_monthly_obligation: float   # tax set-aside + UIF


def calculate_income_tax(taxable_income: float, age: int = 35) -> tuple[float, float]:
    """Returns (tax_before_rebates, rebate)."""
    if taxable_income <= 0:
        return 0.0, 0.0

    tax = 0.0
    prev_limit = 0.0
    for limit, rate, base in TAX_BRACKETS:
        if taxable_income <= limit:
            tax = base + (taxable_income - prev_limit) * rate
            break
        prev_limit = limit

    rebate = PRIMARY_REBATE
    if age >= 65:
        rebate += SECONDARY_REBATE
    if age >= 75:
        rebate += TERTIARY_REBATE

    return round(tax, 2), round(rebate, 2)


def calculate_tax_envelope(
    annual_income: float,
    annual_expenses: float = 0.0,          # Deductible business expenses
    rental_income: float = 0.0,            # Annual rental income
    rental_expenses: float = 0.0,          # Bond interest, levies, rates
    age: int = 35,
    medical_aid_dependants: int = 0,       # 0 = no medical aid
    income_type: str = "freelance",        # "freelance" | "salary_plus_rental" | "rental_only"
) -> TaxEnvelope:

    # Taxable income
    net_business   = max(0.0, annual_income - annual_expenses)
    net_rental     = max(0.0, rental_income - rental_expenses)
    taxable_income = net_business + net_rental

    tax_before_rebates, rebate = calculate_income_tax(taxable_income, age)

    # Medical aid credit
    med_credit = 0.0
    if medical_aid_dependants > 0:
        med_credit = (MEDICAL_CREDIT_MAIN * 12)
        if medical_aid_dependants >= 2:
            med_credit += (MEDICAL_CREDIT_DEPENDANT_1 * 12)
        if medical_aid_dependants > 2:
            med_credit += (MEDICAL_CREDIT_ADDITIONAL * 12 * (medical_aid_dependants - 2))

    tax_payable = max(0.0, tax_before_rebates - rebate - med_credit)
    eff_rate    = (tax_payable / taxable_income * 100) if taxable_income > 0 else 0.0

    monthly_set_aside = round(tax_payable / 12, 2)

    # Provisional tax: split roughly 50/50 across two periods
    prov_1 = round(tax_payable * 0.50, 2)   # First period (end August)
    prov_2 = round(tax_payable * 0.50, 2)   # Second period (end February)

    # UIF (freelancers must pay both employer + employee share = 2%)
    monthly_earnings = min(annual_income / 12, UIF_CAP_MONTH)
    uif_rate_total   = UIF_RATE * 2 if income_type == "freelance" else UIF_RATE
    uif_monthly      = round(monthly_earnings * uif_rate_total, 2)

    vat_required = (annual_income >= VAT_THRESHOLD)

    total_monthly = round(monthly_set_aside + uif_monthly, 2)

    return TaxEnvelope(
        annual_taxable_income=round(taxable_income, 2),
        annual_tax_before_rebates=round(tax_before_rebates, 2),
        annual_rebate=round(rebate, 2),
        annual_medical_credit=round(med_credit, 2),
        annual_tax_payable=round(tax_payable, 2),
        effective_rate_pct=round(eff_rate, 1),
        monthly_set_aside=monthly_set_aside,
        provisional_period_1=prov_1,
        provisional_period_2=prov_2,
        vat_registration_required=vat_required,
        uif_monthly=uif_monthly,
        total_monthly_obligation=total_monthly,
    )


def format_tax_message(envelope: TaxEnvelope, user_name: str = "", income_type: str = "freelance") -> str:
    first = user_name.split()[0] if user_name else None
    greeting = f"Hi {first}! " if first else ""

    def zar(n: float) -> str:
        return f"R{n:,.0f}"

    type_label = {
        "freelance":          "Freelancer / Sole Trader",
        "salary_plus_rental": "Salary + Rental Income",
        "rental_only":        "Property Investor",
    }.get(income_type, "Self-Employed")

    # Determine next provisional tax deadline
    today = date.today()
    month = today.month
    if month <= 8:
        next_deadline = f"31 August {today.year}"
        next_amount   = envelope.provisional_period_1
    else:
        next_deadline = f"28 February {today.year + 1}"
        next_amount   = envelope.provisional_period_2

    lines = [
        "🏦 *BankBook SARS Tax Envelope*",
        f"_{type_label}_",
        "",
        f"{greeting}Here's your provisional tax breakdown:",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "📊 *ANNUAL TAX SUMMARY*",
        f"  Taxable income:     *{zar(envelope.annual_taxable_income)}*",
        f"  Tax before rebates: *{zar(envelope.annual_tax_before_rebates)}*",
        f"  Primary rebate:    -{zar(envelope.annual_rebate)}",
    ]

    if envelope.annual_medical_credit > 0:
        lines.append(f"  Medical credits:   -{zar(envelope.annual_medical_credit)}")

    lines += [
        f"  ✅ Tax payable:     *{zar(envelope.annual_tax_payable)}*",
        f"  Effective rate:    *{envelope.effective_rate_pct}%*",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "💰 *WHAT TO SET ASIDE*",
        f"  Monthly tax:       *{zar(envelope.monthly_set_aside)}/mo*",
        f"  UIF:               *{zar(envelope.uif_monthly)}/mo*",
        f"  📌 Total monthly:  *{zar(envelope.total_monthly_obligation)}/mo*",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "📅 *PROVISIONAL TAX DEADLINES*",
        f"  Period 1 (31 Aug):  *{zar(envelope.provisional_period_1)}*",
        f"  Period 2 (28 Feb):  *{zar(envelope.provisional_period_2)}*",
        f"  ⏰ Next due:        *{zar(next_amount)} by {next_deadline}*",
    ]

    if envelope.vat_registration_required:
        lines += [
            "",
            "⚠️ *VAT REGISTRATION REQUIRED*",
            "  Your turnover exceeds R1M. You must register for VAT with SARS.",
        ]

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "_I've saved your Tax Envelope. I'll remind you 30 days before each deadline._",
        "_Reply 'Tax' anytime to view this summary._",
    ]

    return "\n".join(lines)
