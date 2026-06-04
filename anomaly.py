"""
BankBook Anomaly Detection — Flags financial risk triggers for each user.
Fires WhatsApp warnings when debt-to-income, bond exposure, or insurance
gaps breach safe thresholds.
"""

from dataclasses import dataclass, field
from typing import Optional


# ─── Thresholds ────────────────────────────────────────────────────────────────

DTI_WARN_PCT    = 0.30   # Debt-to-income warning (SA bank limit)
DTI_DANGER_PCT  = 0.40   # Critical — bank will reject new credit
BOND_EXPOSURE   = 0.80   # Bond balance > 80% of property value = high LTV risk
MIN_INSURANCE_COVER = 1  # At least 1 policy expected per property owner


# ─── Data Classes ──────────────────────────────────────────────────────────────

@dataclass
class Anomaly:
    code: str
    severity: str          # "warning" | "critical"
    message: str
    action: str            # Plain-language recommended action
    value: Optional[float] = None


@dataclass
class AnomalyReport:
    whatsapp_id: str
    anomalies: list[Anomaly] = field(default_factory=list)

    @property
    def has_issues(self) -> bool:
        return len(self.anomalies) > 0

    @property
    def critical_count(self) -> int:
        return sum(1 for a in self.anomalies if a.severity == "critical")


# ─── Detection Logic ───────────────────────────────────────────────────────────

def detect_anomalies(
    whatsapp_id: str,
    net_salary: float,
    total_debt: float,
    properties: list[dict],
    insurance_count: int,
) -> AnomalyReport:
    report = AnomalyReport(whatsapp_id=whatsapp_id)

    if net_salary <= 0:
        return report  # Can't analyse without salary data

    dti = total_debt / net_salary

    # 1. Debt-to-income ratio
    if dti >= DTI_DANGER_PCT:
        report.anomalies.append(Anomaly(
            code="DTI_CRITICAL",
            severity="critical",
            message=f"Your debt-to-income ratio is {dti:.0%} — banks cap at 30%. New credit will be rejected.",
            action="Prioritise paying off your highest-interest debt immediately. Reply 'Help' for a plan.",
            value=round(dti, 4),
        ))
    elif dti >= DTI_WARN_PCT:
        report.anomalies.append(Anomaly(
            code="DTI_WARNING",
            severity="warning",
            message=f"Your debt-to-income ratio is {dti:.0%} — at the SA bank limit of 30%.",
            action="Avoid taking on new credit until this ratio drops below 25%.",
            value=round(dti, 4),
        ))

    # 2. High loan-to-value on properties
    for prop in properties:
        value = prop.get("estimated_value", 0)
        bond  = prop.get("bond_balance", 0)
        if value > 0 and bond > 0:
            ltv = bond / value
            if ltv >= BOND_EXPOSURE:
                address = prop.get("address", "your property")
                report.anomalies.append(Anomaly(
                    code="HIGH_LTV",
                    severity="warning",
                    message=f"Your bond on '{address}' is {ltv:.0%} of its value — high LTV risk.",
                    action="Consider making extra bond payments to build equity faster.",
                    value=round(ltv, 4),
                ))

    # 3. Uninsured property owner
    if len(properties) > 0 and insurance_count < MIN_INSURANCE_COVER:
        report.anomalies.append(Anomaly(
            code="NO_INSURANCE",
            severity="critical",
            message="You own property but have no insurance policies in your BankBook.",
            action="Add your home and car insurance policies. Reply 'Insurance' to get started.",
        ))

    # 4. Salary fully consumed by debt
    safe_to_spend = net_salary - total_debt - (net_salary * 0.05)
    if safe_to_spend < net_salary * 0.10:
        report.anomalies.append(Anomaly(
            code="CASH_CRUNCH",
            severity="critical",
            message=f"Less than 10% of your salary is available after debt. You are cash-flow tight.",
            action="Review your debit orders and cut discretionary expenses this month.",
            value=round(safe_to_spend, 2),
        ))

    return report


# ─── WhatsApp Message Formatter ────────────────────────────────────────────────

def format_anomaly_alert(report: AnomalyReport, user_name: str = "") -> str:
    first = user_name.split()[0] if user_name else None
    greeting = f"Hi {first}! " if first else "Hi! "

    if not report.has_issues:
        return (
            f"🏦 *BankBook Health Check*\n\n"
            f"{greeting}✅ Your finances look healthy — no risk flags detected this week.\n\n"
            f"_Keep it up! 🇿🇦_"
        )

    icon_map = {"critical": "🚨", "warning": "⚠️"}

    lines = [
        f"🏦 *BankBook Risk Alert*",
        f"",
        f"{greeting}I've detected {len(report.anomalies)} issue{'s' if len(report.anomalies) > 1 else ''} in your BankBook:",
        f"",
    ]

    for i, a in enumerate(report.anomalies, 1):
        icon = icon_map.get(a.severity, "⚠️")
        lines += [
            f"{icon} *{i}. {a.code.replace('_', ' ').title()}*",
            f"   {a.message}",
            f"   _{a.action}_",
            f"",
        ]

    lines += [
        f"━━━━━━━━━━━━━━━━━━━━",
        f"_Reply 'Help' for guidance on any of the above._",
    ]

    return "\n".join(lines)
