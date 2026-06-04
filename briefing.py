"""
BankBook Morning Briefing — Weekly financial summary sent via WhatsApp.
Covers: Safe-to-Spend, upcoming debit orders, property equity snapshot.
"""

from datetime import datetime


def format_zar(amount: float) -> str:
    return f"R{amount:,.0f}"


def safe_to_spend(net_salary: float, total_debt: float, buffer_pct: float = 0.05) -> float:
    """
    Estimated safe-to-spend after committed debt obligations and a 5% buffer.
    In a full integration this would query live bank balances — here we estimate
    from the profile data stored in BankBook.
    """
    committed = total_debt + (net_salary * buffer_pct)
    return max(0.0, net_salary - committed)


def equity_summary(properties: list[dict]) -> dict:
    """
    Returns total estimated equity across all properties.
    equity = estimated_value - bond_balance
    """
    total_value = sum(p.get("estimated_value", 0) for p in properties)
    total_bond  = sum(p.get("bond_balance", 0)  for p in properties)
    total_rental = sum(p.get("rental_income", 0) for p in properties)
    return {
        "total_value":   round(total_value, 2),
        "total_bond":    round(total_bond, 2),
        "total_equity":  round(total_value - total_bond, 2),
        "total_rental":  round(total_rental, 2),
        "property_count": len(properties),
    }


def build_briefing_message(
    user_name: str,
    net_salary: float,
    total_debt: float,
    properties: list[dict],
    insurance_count: int,
) -> str:
    """
    Composes the full WhatsApp-formatted Monday morning briefing message.
    """
    now = datetime.now()
    day_name = now.strftime("%A")
    date_str = now.strftime("%-d %B %Y")

    sts = safe_to_spend(net_salary, total_debt)
    equity = equity_summary(properties)

    greeting = f"Good morning{', ' + user_name.split()[0] if user_name else ''}! 👋"

    lines = [
        f"🏦 *BankBook Weekly Briefing*",
        f"_{day_name}, {date_str}_",
        "",
        greeting,
        "Here's your financial snapshot for this week:",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "💰 *CASHFLOW*",
        f"  Take-home salary:  *{format_zar(net_salary)}*",
        f"  Committed debt:    *{format_zar(total_debt)}*",
        f"  ✅ Safe-to-Spend:  *{format_zar(sts)}*",
        "",
    ]

    if equity["property_count"] > 0:
        lines += [
            "━━━━━━━━━━━━━━━━━━━━",
            "🏡 *PROPERTY*",
            f"  Properties:        *{equity['property_count']}*",
            f"  Portfolio value:   *{format_zar(equity['total_value'])}*",
            f"  Outstanding bonds: *{format_zar(equity['total_bond'])}*",
            f"  📈 Net equity:     *{format_zar(equity['total_equity'])}*",
        ]
        if equity["total_rental"] > 0:
            lines.append(f"  🏘 Rental income:  *{format_zar(equity['total_rental'])}/mo*")
        lines.append("")

    if insurance_count > 0:
        lines += [
            "━━━━━━━━━━━━━━━━━━━━",
            f"🛡 *INSURANCE*  {insurance_count} polic{'y' if insurance_count == 1 else 'ies'} on file",
            "",
        ]

    lines += [
        "━━━━━━━━━━━━━━━━━━━━",
        "_Need a bond calculation or property check?_",
        "_Just ask me anytime. Have a great week! 🇿🇦_",
    ]

    return "\n".join(lines)
