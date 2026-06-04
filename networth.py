from dataclasses import dataclass, field
from typing import Optional


@dataclass
class NetWorthReport:
    # Assets
    property_value_gross: float       # sum of estimated values
    property_equity: float            # sum of (value - bond)
    outstanding_bonds: float          # sum of bond balances
    bank_balance: float
    savings_goals_total: float        # sum of current_saved across active goals
    rewards_rand_value: float
    total_assets: float

    # Liabilities
    outstanding_bonds_liability: float  # same as outstanding_bonds (for clarity in output)
    monthly_debt_obligations: float     # user.total_debt (monthly figure)

    # Summary
    net_worth: float
    net_worth_excl_property: float    # liquid net worth (excl property)

    # Breakdown detail
    properties: list   # [{"address": ..., "value": ..., "bond": ..., "equity": ...}]
    goals: list        # [{"label": ..., "saved": ...}]


def calculate_net_worth(
    net_salary: float,
    total_debt: float,
    properties: list,   # list of dicts with estimated_value, bond_balance, address
    goals: list,        # list of dicts with label, current_saved
    bank_balance: float,
    rewards_rand_value: float,
) -> NetWorthReport:
    # ── Property ──────────────────────────────────────────────────────────────
    prop_value_gross = sum(p.get("estimated_value", 0) for p in properties)
    prop_bonds       = sum(p.get("bond_balance", 0)    for p in properties)
    prop_equity      = prop_value_gross - prop_bonds

    prop_detail = [
        {
            "address": p.get("address", "Property"),
            "value": p.get("estimated_value", 0),
            "bond": p.get("bond_balance", 0),
            "equity": p.get("estimated_value", 0) - p.get("bond_balance", 0),
        }
        for p in properties
    ]

    # ── Savings goals ─────────────────────────────────────────────────────────
    goals_total = sum(g.get("current_saved", 0) for g in goals)
    goals_detail = [
        {"label": g.get("label", "Goal"), "saved": g.get("current_saved", 0)}
        for g in goals
    ]

    # ── Totals ────────────────────────────────────────────────────────────────
    total_assets = prop_equity + bank_balance + goals_total + rewards_rand_value
    net_worth    = total_assets  # bonds already netted in prop_equity
    net_worth_liquid = bank_balance + goals_total + rewards_rand_value

    return NetWorthReport(
        property_value_gross=round(prop_value_gross, 2),
        property_equity=round(prop_equity, 2),
        outstanding_bonds=round(prop_bonds, 2),
        bank_balance=round(bank_balance, 2),
        savings_goals_total=round(goals_total, 2),
        rewards_rand_value=round(rewards_rand_value, 2),
        total_assets=round(total_assets, 2),
        outstanding_bonds_liability=round(prop_bonds, 2),
        monthly_debt_obligations=round(total_debt, 2),
        net_worth=round(net_worth, 2),
        net_worth_excl_property=round(net_worth_liquid, 2),
        properties=prop_detail,
        goals=goals_detail,
    )


def _zar(n: float) -> str:
    return f"R{n:,.0f}"


def _trend_icon(n: float) -> str:
    if n >= 5_000_000:
        return "💎"
    if n >= 2_000_000:
        return "🏆"
    if n >= 1_000_000:
        return "🌟"
    if n >= 500_000:
        return "📈"
    if n >= 100_000:
        return "✅"
    if n >= 0:
        return "🌱"
    return "⚠️"


def format_net_worth_message(report: NetWorthReport, user_name: str = "") -> str:
    first = user_name.split()[0] if user_name else ""
    name_part = f" {first}" if first else ""

    lines = [
        f"🏦 *BankBook Net Worth*{name_part}",
        f"",
        f"{_trend_icon(report.net_worth)} *Total Net Worth: {_zar(report.net_worth)}*",
        f"",
        f"━━━━━━━━━━━━━━━━━━━━",
        f"🏡 *PROPERTY*",
    ]

    if report.properties:
        for p in report.properties:
            lines.append(f"  {p['address'][:28]}")
            lines.append(f"  Value: {_zar(p['value'])}  |  Bond: {_zar(p['bond'])}")
            equity_icon = "📈" if p["equity"] >= 0 else "📉"
            lines.append(f"  {equity_icon} Equity: *{_zar(p['equity'])}*")
        lines.append(f"  ──────────────────")
        lines.append(f"  Total equity: *{_zar(report.property_equity)}*")
    else:
        lines.append(f"  No properties on file")

    lines += [
        f"",
        f"━━━━━━━━━━━━━━━━━━━━",
        f"💵 *CASH & SAVINGS*",
        f"  Bank balance:   *{_zar(report.bank_balance)}*",
    ]

    if report.goals:
        lines.append(f"  Savings goals:")
        for g in report.goals:
            lines.append(f"    • {g['label']}: {_zar(g['saved'])}")
        lines.append(f"  Goals total:    *{_zar(report.savings_goals_total)}*")

    if report.rewards_rand_value > 0:
        lines += [
            f"",
            f"━━━━━━━━━━━━━━━━━━━━",
            f"🎁 *REWARDS*",
            f"  Loyalty points: *{_zar(report.rewards_rand_value)}*",
        ]

    lines += [
        f"",
        f"━━━━━━━━━━━━━━━━━━━━",
        f"📋 *SUMMARY*",
        f"  Property equity:  {_zar(report.property_equity)}",
        f"  Cash & savings:   {_zar(report.bank_balance + report.savings_goals_total)}",
    ]

    if report.rewards_rand_value > 0:
        lines.append(f"  Rewards value:    {_zar(report.rewards_rand_value)}")

    lines += [
        f"  ──────────────────",
        f"  🏆 Net worth:  *{_zar(report.net_worth)}*",
        f"  💧 Liquid only: *{_zar(report.net_worth_excl_property)}*",
    ]

    if report.monthly_debt_obligations > 0:
        lines += [
            f"",
            f"_Monthly debt obligations: {_zar(report.monthly_debt_obligations)}/mo_",
        ]

    lines += [
        f"",
        f"_Updated today · Reply 'Net worth' anytime to refresh_",
    ]

    return "\n".join(lines)
