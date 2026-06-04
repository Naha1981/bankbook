"""
BankBook Credit Score Simulator

Estimates a South African credit score (0–999 scale, TransUnion/Experian SA style)
based on Debt-to-Income ratio and simulates the impact of paying off specific debts.

DISCLAIMER: This is an illustrative simulation only — not an official credit check.
Actual scores consider payment history, credit age, enquiries, and bureau data.
"""

from dataclasses import dataclass, field
from typing import Optional


# ── Score bands (SA scale 0–999) ────────────────────────────────────────────

BANDS = [
    (800, 999, "Excellent",  "🟢", "You qualify for the best interest rates."),
    (700, 799, "Good",       "🔵", "Strong profile — most lenders will approve you."),
    (600, 699, "Fair",       "🟡", "Approvable but expect higher interest rates."),
    (500, 599, "Poor",       "🟠", "Limited options — some lenders may decline."),
    (0,   499, "Very Poor",  "🔴", "High risk profile — focus on debt reduction."),
]


def _band(score: int) -> tuple:
    for lo, hi, label, icon, tip in BANDS:
        if lo <= score <= hi:
            return label, icon, tip
    return "Unknown", "⚪", ""


# ── Core scoring model ───────────────────────────────────────────────────────

def _dti_score(dti: float) -> int:
    """
    Maps Debt-to-Income ratio to a score component (0–400 points).
    DTI = monthly_debt / net_salary
    """
    if dti <= 0.05:  return 400
    if dti <= 0.10:  return 370
    if dti <= 0.15:  return 340
    if dti <= 0.20:  return 310
    if dti <= 0.25:  return 275
    if dti <= 0.30:  return 235
    if dti <= 0.35:  return 195
    if dti <= 0.40:  return 155
    if dti <= 0.45:  return 115
    if dti <= 0.50:  return  75
    if dti <= 0.60:  return  40
    return 10


def _base_score(net_salary: float, total_debt: float) -> tuple[int, float]:
    """Returns (estimated_score, dti)."""
    dti = total_debt / net_salary if net_salary > 0 else 1.0
    # Base = 450 (payment history assumption — neutral) + DTI component
    score = min(999, max(0, 450 + _dti_score(dti)))
    return score, dti


# ── Dataclasses ──────────────────────────────────────────────────────────────

@dataclass
class SimScenario:
    label: str
    monthly_reduction: float
    new_total_debt: float
    new_dti: float
    new_score: int
    score_change: int
    new_band: str
    band_icon: str
    band_tip: str
    monthly_savings: float          # freed-up cash per month
    breakeven_months: Optional[int] # months to save enough to pay it off (if lump-sum provided)


@dataclass
class CreditSimReport:
    current_score: int
    current_dti: float
    current_band: str
    current_icon: str
    current_tip: str
    net_salary: float
    total_debt: float
    scenarios: list[SimScenario]
    best_scenario: Optional[SimScenario]   # highest score gain


# ── Main simulation ──────────────────────────────────────────────────────────

def simulate_credit_score(
    net_salary: float,
    total_debt: float,
    debts_to_simulate: list[dict],  # [{"label": "Car loan", "monthly_amount": 3500}]
) -> CreditSimReport:
    current_score, current_dti = _base_score(net_salary, total_debt)
    c_band, c_icon, c_tip = _band(current_score)

    scenarios: list[SimScenario] = []

    for debt in debts_to_simulate:
        label          = debt.get("label", "Debt")
        monthly_amount = float(debt.get("monthly_amount", 0))
        lump_sum       = debt.get("lump_sum")  # optional: outstanding balance to pay off

        if monthly_amount <= 0:
            continue

        new_total  = max(0.0, total_debt - monthly_amount)
        new_score, new_dti = _base_score(net_salary, new_total)
        score_change = new_score - current_score
        n_band, n_icon, n_tip = _band(new_score)

        # Breakeven: how many months of freed-up cash to accumulate the lump sum
        breakeven = None
        if lump_sum and monthly_amount > 0:
            breakeven = max(1, round(float(lump_sum) / monthly_amount))

        scenarios.append(SimScenario(
            label=label,
            monthly_reduction=monthly_amount,
            new_total_debt=new_total,
            new_dti=round(new_dti, 3),
            new_score=new_score,
            score_change=score_change,
            new_band=n_band,
            band_icon=n_icon,
            band_tip=n_tip,
            monthly_savings=monthly_amount,
            breakeven_months=breakeven,
        ))

    best = max(scenarios, key=lambda s: s.score_change) if scenarios else None

    return CreditSimReport(
        current_score=current_score,
        current_dti=round(current_dti, 3),
        current_band=c_band,
        current_icon=c_icon,
        current_tip=c_tip,
        net_salary=net_salary,
        total_debt=total_debt,
        scenarios=scenarios,
        best_scenario=best,
    )


# ── WhatsApp formatter ───────────────────────────────────────────────────────

def _score_bar(score: int, width: int = 10) -> str:
    filled = round((score / 999) * width)
    return "█" * filled + "░" * (width - filled)


def format_credit_sim_message(report: CreditSimReport, user_name: str = "") -> str:
    first = user_name.split()[0] if user_name else ""
    name_part = f" {first}" if first else ""
    dti_pct = round(report.current_dti * 100, 1)

    lines = [
        f"🏦 *BankBook Credit Simulator*{name_part}",
        f"",
        f"📊 *Your Estimated Credit Profile*",
        f"{report.current_icon} Score: *{report.current_score}/999* — {report.current_band}",
        f"{_score_bar(report.current_score)}",
        f"",
        f"  Take-home salary:  R{report.net_salary:,.0f}",
        f"  Monthly debt:      R{report.total_debt:,.0f}",
        f"  Debt-to-income:    *{dti_pct}%*",
        f"  _{report.current_tip}_",
        f"",
        f"━━━━━━━━━━━━━━━━━━━━",
        f"🔮 *WHAT-IF SCENARIOS*",
    ]

    for s in report.scenarios:
        change_str = f"+{s.score_change}" if s.score_change >= 0 else str(s.score_change)
        arrow = "📈" if s.score_change > 0 else ("➡️" if s.score_change == 0 else "📉")
        new_dti_pct = round(s.new_dti * 100, 1)

        lines += [
            f"",
            f"💳 *Pay off: {s.label}*",
            f"  Free up: R{s.monthly_reduction:,.0f}/month",
            f"  New score: *{s.new_score}/999* ({s.band_icon} {s.new_band})",
            f"  {arrow} Score change: *{change_str} points*",
            f"  New DTI: {new_dti_pct}%",
        ]

        if s.breakeven_months:
            lines.append(
                f"  ⏳ Pay it off in ~{s.breakeven_months} month{'s' if s.breakeven_months != 1 else ''} "
                f"by saving R{s.monthly_reduction:,.0f}/mo"
            )

    if report.best_scenario:
        b = report.best_scenario
        change_str = f"+{b.score_change}" if b.score_change >= 0 else str(b.score_change)
        lines += [
            f"",
            f"━━━━━━━━━━━━━━━━━━━━",
            f"⭐ *BIGGEST IMPACT*",
            f"Paying off *{b.label}* gives you the most points ({change_str}).",
            f"New score would be *{b.new_score}/999* — {b.band_icon} {b.new_band}.",
            f"That's R{b.monthly_savings:,.0f}/month back in your pocket.",
        ]

    lines += [
        f"",
        f"━━━━━━━━━━━━━━━━━━━━",
        f"_⚠️ Simulation only — not an official credit check._",
        f"_For your real score: CheckMyDebt, Experian SA, or TransUnion SA (free once/year)._",
    ]

    return "\n".join(lines)
