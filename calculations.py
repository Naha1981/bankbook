"""
South African mortgage and financial calculations for BankBook AI OS.
Based on current SA Prime Rate and standard bank affordability rules.
"""

# Current South African Prime Rate
SA_PRIME_RATE = 0.1175  # 11.75% per annum
BOND_TERM_YEARS = 20
AFFORDABILITY_RATIO = 0.30  # Banks allow max 30% of net income


def calculate_monthly_repayment(price: float, annual_rate: float = SA_PRIME_RATE, years: int = BOND_TERM_YEARS) -> float:
    """
    Standard mortgage amortisation formula:
    PMT = P * [r(1+r)^n] / [(1+r)^n - 1]
    """
    monthly_rate = annual_rate / 12
    n = years * 12
    repayment = price * (monthly_rate * (1 + monthly_rate) ** n) / ((1 + monthly_rate) ** n - 1)
    return round(repayment, 2)


def calculate_affordability(salary: float, debt: float, price: float) -> dict:
    """
    Calculate whether a property is affordable based on SA bank criteria.
    Banks deduct existing debt from the 30% threshold.
    """
    monthly_repayment = calculate_monthly_repayment(price)

    # Available capacity after existing debt obligations
    max_allowed = (salary * AFFORDABILITY_RATIO) - debt
    is_affordable = monthly_repayment <= max_allowed

    # Work out maximum affordable property price
    affordable_payment = max(0.0, salary * AFFORDABILITY_RATIO - debt)
    monthly_rate = SA_PRIME_RATE / 12
    n = BOND_TERM_YEARS * 12
    max_price = affordable_payment * ((1 + monthly_rate) ** n - 1) / (monthly_rate * (1 + monthly_rate) ** n)

    return {
        "repayment": monthly_repayment,
        "max_allowed": round(max_allowed, 2),
        "is_affordable": is_affordable,
        "shortfall": round(monthly_repayment - max_allowed, 2) if not is_affordable else 0.0,
        "max_affordable_price": round(max_price, 2),
        "annual_rate_pct": SA_PRIME_RATE * 100,
        "term_years": BOND_TERM_YEARS,
    }


def insurance_savings_estimate(current_premium: float, savings_rate: float = 0.15) -> dict:
    """
    Estimate potential insurance savings vs. market average.
    South Africans typically overpay by ~15% vs. best available rate.
    """
    potential_saving = current_premium * savings_rate
    return {
        "current_premium": round(current_premium, 2),
        "estimated_saving": round(potential_saving, 2),
        "optimised_premium": round(current_premium - potential_saving, 2),
    }
