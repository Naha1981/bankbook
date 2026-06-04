"""
BankBook Pre-Approval Simulator — "What if?" debt payoff scenarios.
Shows how clearing specific debts unlocks more bond affordability.
"""

from calculations import calculate_monthly_repayment, SA_PRIME_RATE, BOND_TERM_YEARS, AFFORDABILITY_RATIO
from dataclasses import dataclass


@dataclass
class PayoffScenario:
    label: str                  # e.g. "Clear car loan (R5,000/mo)"
    debt_cleared: float         # Monthly debt amount removed
    new_total_debt: float
    new_max_bond: float
    new_max_price: float
    extra_bond_capacity: float  # vs. current
    extra_price_capacity: float
    monthly_repayment: float


def _max_price_from_capacity(capacity: float) -> float:
    """Invert the mortgage formula to get max affordable price."""
    if capacity <= 0:
        return 0.0
    r = SA_PRIME_RATE / 12
    n = BOND_TERM_YEARS * 12
    return capacity * ((1 + r) ** n - 1) / (r * (1 + r) ** n)


def simulate_payoffs(
    net_salary: float,
    total_debt: float,
    debts_to_simulate: list[dict],  # [{"label": "Car loan", "monthly_amount": 5000}, ...]
) -> dict:
    """
    For each debt item in debts_to_simulate, calculate how much more house
    the user can afford after clearing it (and how the numbers change).
    """
    # Baseline
    baseline_capacity = max(0.0, net_salary * AFFORDABILITY_RATIO - total_debt)
    baseline_max_price = _max_price_from_capacity(baseline_capacity)
    baseline_repayment = calculate_monthly_repayment(baseline_max_price) if baseline_max_price > 0 else 0.0

    scenarios: list[PayoffScenario] = []

    for debt in debts_to_simulate:
        label = debt.get("label", "Unknown debt")
        amount = float(debt.get("monthly_amount", 0))

        new_total_debt = max(0.0, total_debt - amount)
        new_capacity = max(0.0, net_salary * AFFORDABILITY_RATIO - new_total_debt)
        new_max_price = _max_price_from_capacity(new_capacity)
        new_repayment = calculate_monthly_repayment(new_max_price) if new_max_price > 0 else 0.0

        scenarios.append(PayoffScenario(
            label=label,
            debt_cleared=amount,
            new_total_debt=round(new_total_debt, 2),
            new_max_bond=round(new_capacity, 2),
            new_max_price=round(new_max_price, 2),
            extra_bond_capacity=round(new_capacity - baseline_capacity, 2),
            extra_price_capacity=round(new_max_price - baseline_max_price, 2),
            monthly_repayment=round(new_repayment, 2),
        ))

    return {
        "current": {
            "total_debt": round(total_debt, 2),
            "monthly_capacity": round(baseline_capacity, 2),
            "max_price": round(baseline_max_price, 2),
            "monthly_repayment": round(baseline_repayment, 2),
        },
        "scenarios": [
            {
                "label": s.label,
                "debt_cleared": s.debt_cleared,
                "new_total_debt": s.new_total_debt,
                "new_max_price": s.new_max_price,
                "extra_price_capacity": s.extra_price_capacity,
                "monthly_repayment": s.monthly_repayment,
            }
            for s in scenarios
        ],
        "best_scenario": max(scenarios, key=lambda s: s.extra_price_capacity).label if scenarios else None,
    }


def format_simulator_message(result: dict, user_name: str = "") -> str:
    """Format the simulation results as a WhatsApp-ready message."""
    first = user_name.split()[0] if user_name else None
    greeting = f"Here's your pre-approval simulation{', ' + first if first else ''}:"

    current = result["current"]

    def zar(n: float) -> str:
        return f"R{n:,.0f}"

    lines = [
        "🏦 *BankBook Pre-Approval Simulator*",
        "",
        greeting,
        "",
        "📊 *CURRENT STATUS*",
        f"  Monthly debt:     *{zar(current['total_debt'])}*",
        f"  Bond capacity:    *{zar(current['monthly_capacity'])}/mo*",
        f"  Max house price:  *{zar(current['max_price'])}*",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "🔮 *WHAT IF YOU PAID OFF...*",
        "",
    ]

    for s in result["scenarios"]:
        uplift = s["extra_price_capacity"]
        arrow = "📈" if uplift > 0 else "➡️"
        lines += [
            f"{arrow} *{s['label']}* (clears {zar(s['debt_cleared'])}/mo)",
            f"   New max price:  *{zar(s['new_max_price'])}*",
            f"   Price uplift:   *+{zar(uplift)}*",
            f"   Monthly bond:   *{zar(s['monthly_repayment'])}*",
            "",
        ]

    if result.get("best_scenario"):
        lines += [
            "━━━━━━━━━━━━━━━━━━━━",
            f"💡 *Best move:* Clear your *{result['best_scenario']}* first for maximum affordability.",
            "",
            "_Reply 'Affordability' to run a full bond check on any price._",
        ]

    return "\n".join(lines)
