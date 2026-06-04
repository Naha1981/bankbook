"""
BankBook Rewards Tracker — eBucks, UCount, Discovery Miles, Greenbacks & more.
Tracks balances, flags expiry risk, and estimates Rand value of points.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional


# ─── Conversion rates (approximate Rand value per point/mile) ──────────────────

REWARD_PROGRAMS = {
    "eBucks": {
        "provider": "FNB",
        "rand_per_point": 0.01,          # 100 eBucks = R1
        "expiry_months": 12,
        "description": "FNB eBucks",
    },
    "UCount": {
        "provider": "Standard Bank",
        "rand_per_point": 0.01,
        "expiry_months": 36,
        "description": "Standard Bank UCount Rewards",
    },
    "Discovery Miles": {
        "provider": "Discovery Bank / Vitality",
        "rand_per_point": 0.01,          # 100 miles = R1 at standard redemption
        "expiry_months": 36,
        "description": "Discovery Vitality Miles",
    },
    "Greenbacks": {
        "provider": "Nedbank",
        "rand_per_point": 0.01,
        "expiry_months": 36,
        "description": "Nedbank Greenbacks",
    },
    "Avios": {
        "provider": "British Airways / Comair",
        "rand_per_point": 0.12,          # ~12c per Avios point for flights
        "expiry_months": 36,
        "description": "British Airways Avios",
    },
    "Voyager Miles": {
        "provider": "SAA",
        "rand_per_point": 0.10,
        "expiry_months": 36,
        "description": "SAA Voyager Miles",
    },
    "Momentum Multiply": {
        "provider": "Momentum",
        "rand_per_point": 0.01,
        "expiry_months": 24,
        "description": "Momentum Multiply Cashbacks",
    },
}

EXPIRY_WARNING_DAYS = 90   # Warn when expiry is within 90 days


@dataclass
class RewardEntry:
    program: str
    balance: float
    expiry_date: Optional[date]
    rand_value: float
    days_to_expiry: Optional[int]
    expiry_risk: str    # "safe" | "warning" | "urgent" | "unknown"
    provider: str
    description: str


@dataclass
class RewardsReport:
    whatsapp_id: str
    entries: list[RewardEntry] = field(default_factory=list)
    total_rand_value: float = 0.0
    urgent_programs: list[str] = field(default_factory=list)


def evaluate_rewards(
    whatsapp_id: str,
    rewards: list[dict],   # [{"program": "eBucks", "balance": 5000, "expiry_date": "2025-06-30"}]
) -> RewardsReport:
    report = RewardsReport(whatsapp_id=whatsapp_id)
    today  = date.today()

    for r in rewards:
        program  = r.get("program", "")
        balance  = float(r.get("balance", 0))
        exp_str  = r.get("expiry_date")  # "YYYY-MM-DD" or None

        meta = REWARD_PROGRAMS.get(program, {
            "provider": "Unknown",
            "rand_per_point": 0.01,
            "expiry_months": 12,
            "description": program,
        })

        rand_value = round(balance * meta["rand_per_point"], 2)

        # Expiry
        expiry_date  = None
        days_to_exp  = None
        expiry_risk  = "unknown"

        if exp_str:
            try:
                expiry_date = date.fromisoformat(exp_str)
                days_to_exp = (expiry_date - today).days
                if days_to_exp < 0:
                    expiry_risk = "expired"
                elif days_to_exp <= 30:
                    expiry_risk = "urgent"
                elif days_to_exp <= EXPIRY_WARNING_DAYS:
                    expiry_risk = "warning"
                else:
                    expiry_risk = "safe"
            except ValueError:
                pass

        entry = RewardEntry(
            program=program,
            balance=balance,
            expiry_date=expiry_date,
            rand_value=rand_value,
            days_to_expiry=days_to_exp,
            expiry_risk=expiry_risk,
            provider=meta["provider"],
            description=meta["description"],
        )
        report.entries.append(entry)

        report.total_rand_value += rand_value
        if expiry_risk in ("urgent", "expired"):
            report.urgent_programs.append(program)

    report.total_rand_value = round(report.total_rand_value, 2)
    return report


def format_rewards_message(report: RewardsReport, user_name: str = "") -> str:
    first = user_name.split()[0] if user_name else None
    greeting = f"Hi {first}! " if first else ""

    if not report.entries:
        return (
            f"🏦 *BankBook Rewards Vault*\n\n"
            f"{greeting}You haven't added any rewards programmes yet.\n\n"
            f"To add one, reply: _eBucks 5000_ or _Discovery Miles 12000_"
        )

    def zar(n: float) -> str:
        return f"R{n:,.0f}"

    risk_icon = {"safe": "✅", "warning": "⚠️", "urgent": "🚨", "expired": "❌", "unknown": "📋"}

    lines = [
        "🏦 *BankBook Rewards Vault*",
        "",
        f"{greeting}Here's your rewards summary:",
        "",
    ]

    for e in report.entries:
        icon = risk_icon.get(e.expiry_risk, "📋")
        exp_str = ""
        if e.days_to_expiry is not None:
            if e.expiry_risk == "expired":
                exp_str = "  ❌ _EXPIRED_"
            elif e.days_to_expiry <= 30:
                exp_str = f"  🚨 _Expires in {e.days_to_expiry} days!_"
            elif e.days_to_expiry <= 90:
                exp_str = f"  ⚠️ _Expires in {e.days_to_expiry} days_"
            else:
                exp_str = f"  ✅ _{e.days_to_expiry} days left_"

        lines += [
            f"{icon} *{e.program}* ({e.provider})",
            f"   Balance: *{e.balance:,.0f} points* = *{zar(e.rand_value)}*",
        ]
        if exp_str:
            lines.append(f"  {exp_str.strip()}")
        lines.append("")

    lines += [
        "━━━━━━━━━━━━━━━━━━━━",
        f"💰 *Total Rewards Value: {zar(report.total_rand_value)}*",
        "",
    ]

    if report.urgent_programs:
        programs_str = ", ".join(f"*{p}*" for p in report.urgent_programs)
        lines += [
            f"🚨 *Action required:* {programs_str} expire soon — use them before they're gone!",
            "",
        ]

    lines.append("_Reply 'Rewards' anytime to check your vault._")
    return "\n".join(lines)
