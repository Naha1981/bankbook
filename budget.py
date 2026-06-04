"""
BankBook Budget Coach — Spend categorisation & monthly breakdown.
Users text their expenses ("Spent R800 at Woolworths") and BankBook
categorises them, tracks totals, and coaches on overspending.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional
import re


# ─── Category Definitions ─────────────────────────────────────────────────────

CATEGORIES: dict[str, list[str]] = {
    "Groceries":       ["woolworths", "pick n pay", "pnp", "checkers", "spar", "food lover", "shoprite", "clicks food", "makro food"],
    "Eating Out":      ["kfc", "mcdonalds", "mcdonald", "steers", "nandos", "nando", "ocean basket", "spur", "wimpy", "fishaways", "debonairs", "pizza", "burger", "restaurant", "café", "cafe", "takeaway", "uber eats", "mr delivery", "bolt food"],
    "Transport":       ["uber", "bolt", "engen", "sasol", "shell", "bp ", "caltex", "total petrol", "gauge", "petrol", "fuel", "e-toll", "sanral", "metered taxi", "gautrain"],
    "Medical":         ["clicks", "dischem", "dis-chem", "doctor", "pharmacy", "medirite", "hospital", "clinic", "dentist", "optometrist"],
    "Entertainment":   ["netflix", "showmax", "dstv", "apple tv", "spotify", "amazon prime", "youtube premium", "cinema", "nu metro", "ster-kinekor", "movies", "concert", "event"],
    "Insurance":       ["outsurance", "ooutsu", "discovery insure", "old mutual", "sanlam", "momentum insure", "miway", "dialdirect", "king price", "hippo"],
    "Clothing":        ["mr price", "mrp", "woolworths clothing", "foschini", "truworths", "edgars", "h&m", "zara", "cotton on", "ackermans", "pep store", "jet store", "clothing"],
    "Electronics":     ["game store", "incredible connection", "takealot", "apple store", "samsung", "hi-fi corp", "makro electronics"],
    "Home & Garden":   ["builders", "leroy merlin", "mica", "cashbuild", "build it", "potteries", "garden", "home depot"],
    "Health & Gym":    ["virgin active", "planet fitness", "gym", "crossfit", "yoga", "pilates", "biokinetics", "physiotherapy"],
    "Education":       ["school fees", "university", "unisa", "varsity", "tuition", "course", "udemy", "coursera"],
    "Banking Fees":    ["bank charge", "service fee", "atm fee", "monthly fee", "nedbank fee", "fnb fee", "absa fee", "standard bank fee"],
    "Savings":         ["savings", "investment", "unit trust", "etf", "tfsa", "tax free", "easy equities", "old mutual saving"],
    "Other":           [],
}

# Monthly spending benchmarks as % of net salary
BENCHMARKS: dict[str, float] = {
    "Groceries":    0.15,
    "Eating Out":   0.05,
    "Transport":    0.10,
    "Entertainment": 0.03,
    "Clothing":     0.05,
}


@dataclass
class SpendEntry:
    description: str
    amount: float
    category: str
    entry_date: date
    raw_text: str


@dataclass
class BudgetSummary:
    month_label: str
    total_spent: float
    by_category: dict[str, float]
    entry_count: int
    over_budget: list[dict]   # [{"category": ..., "spent": ..., "limit": ..., "overage": ...}]
    net_salary: float = 0.0


def categorise(description: str) -> str:
    """Match description to a category using keyword lookup."""
    lower = description.lower()
    for cat, keywords in CATEGORIES.items():
        for kw in keywords:
            if kw in lower:
                return cat
    return "Other"


def parse_spend_message(text: str) -> Optional[dict]:
    """
    Parse natural language spend messages into structured data.
    Supports:
      "Spent R800 at Woolworths"
      "R200 KFC"
      "Paid 1500 for Netflix"
      "150 at Checkers"
    Returns {"amount": float, "description": str} or None.
    """
    # Remove common filler words
    clean = re.sub(r"\b(spent|paid|bought|spend|at|for|on|the|a)\b", " ", text, flags=re.IGNORECASE)
    clean = re.sub(r"\s+", " ", clean).strip()

    # Extract amount
    amount_match = re.search(r"r?\s*([\d,]+(?:\.\d{1,2})?)", clean, re.IGNORECASE)
    if not amount_match:
        return None

    amount = float(amount_match.group(1).replace(",", ""))
    if amount <= 0 or amount > 500_000:
        return None

    # Description = everything that is not the amount
    desc = re.sub(r"r?\s*[\d,]+(?:\.\d{1,2})?", "", clean, flags=re.IGNORECASE).strip(" .,")
    if not desc:
        desc = "Other"

    return {"amount": amount, "description": desc}


def build_budget_summary(
    entries: list[dict],
    net_salary: float,
    month_label: str,
) -> BudgetSummary:
    by_cat: dict[str, float] = {}
    total = 0.0

    for e in entries:
        cat   = e.get("category", "Other")
        amt   = float(e.get("amount", 0))
        by_cat[cat] = by_cat.get(cat, 0.0) + amt
        total += amt

    over_budget = []
    if net_salary > 0:
        for cat, bench_pct in BENCHMARKS.items():
            limit = net_salary * bench_pct
            spent = by_cat.get(cat, 0.0)
            if spent > limit:
                over_budget.append({
                    "category": cat,
                    "spent":    round(spent, 2),
                    "limit":    round(limit, 2),
                    "overage":  round(spent - limit, 2),
                })

    return BudgetSummary(
        month_label=month_label,
        total_spent=round(total, 2),
        by_category={k: round(v, 2) for k, v in sorted(by_cat.items(), key=lambda x: -x[1])},
        entry_count=len(entries),
        over_budget=over_budget,
        net_salary=net_salary,
    )


def format_spend_confirm(description: str, amount: float, category: str) -> str:
    return (
        f"🏦 *BankBook Budget Coach*\n\n"
        f"✅ Logged: *{description}* — R{amount:,.0f}\n"
        f"📂 Category: _{category}_\n\n"
        f"Reply 'Budget' anytime to see your monthly breakdown."
    )


def format_budget_summary(summary: BudgetSummary) -> str:
    def zar(n: float) -> str:
        return f"R{n:,.0f}"

    lines = [
        "🏦 *BankBook Budget Coach*",
        f"_{summary.month_label}_",
        "",
        f"📊 *{summary.entry_count} transactions logged — {zar(summary.total_spent)} total*",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "💸 *SPENDING BY CATEGORY*",
    ]

    for cat, amt in summary.by_category.items():
        pct = f"{(amt / summary.total_spent * 100):.0f}%" if summary.total_spent > 0 else ""
        over = any(o["category"] == cat for o in summary.over_budget)
        flag = " ⚠️" if over else ""
        lines.append(f"  {cat}: *{zar(amt)}* _{pct}_{flag}")

    lines += ["", "━━━━━━━━━━━━━━━━━━━━"]

    if summary.over_budget:
        lines.append("🚨 *OVER YOUR BENCHMARKS*")
        for item in summary.over_budget:
            lines += [
                f"  *{item['category']}*",
                f"  Spent {zar(item['spent'])} vs. limit {zar(item['limit'])}",
                f"  ⬆️ Over by *{zar(item['overage'])}*",
                "",
            ]
    else:
        lines += ["✅ *All categories within healthy limits!*", ""]

    if summary.net_salary > 0:
        savings_rate = max(0.0, (summary.net_salary - summary.total_spent) / summary.net_salary * 100)
        lines += [
            "━━━━━━━━━━━━━━━━━━━━",
            f"💰 Salary:       {zar(summary.net_salary)}",
            f"💸 Total spent:  {zar(summary.total_spent)}",
            f"📈 Remaining:    *{zar(summary.net_salary - summary.total_spent)}* ({savings_rate:.0f}% unspent)",
        ]

    lines += ["", "_Reply 'Spent R[amount] at [place]' to log more._"]
    return "\n".join(lines)
