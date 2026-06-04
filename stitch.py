"""
BankBook Safe-to-Spend — Real balance engine.

Integration layer for Stitch (stitch.money) — South Africa's open banking API.
Falls back to manual balance entry when Stitch is not connected.

Stitch provides:
  - Account balances (FNB, Standard Bank, Nedbank, Absa, Capitec, Discovery)
  - Recent transactions
  - Upcoming debit orders (via recurring transaction detection)

Setup:
  1. Register at stitch.money/developers
  2. Set STITCH_CLIENT_ID and STITCH_CLIENT_SECRET in your environment
  3. User completes Stitch Link flow once to authorise their bank account
  4. BankBook stores the user_token and refreshes it automatically
"""

import os
import json
import urllib.request
import urllib.error
from datetime import date, timedelta
from dataclasses import dataclass, field
from typing import Optional


STITCH_BASE_URL    = "https://api.stitch.money"
STITCH_TOKEN_URL   = "https://secure.stitch.money/connect/token"
STITCH_LINK_URL    = "https://secure.stitch.money/connect/link"
STITCH_CLIENT_ID   = os.getenv("STITCH_CLIENT_ID", "")
STITCH_CLIENT_SECRET = os.getenv("STITCH_CLIENT_SECRET", "")


# ─── Stitch GraphQL helpers ────────────────────────────────────────────────────

def _gql(user_token: str, query: str, variables: dict = None) -> dict:
    """Execute a Stitch GraphQL query using the user's access token."""
    payload = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(
        f"{STITCH_BASE_URL}/graphql",
        data=payload,
        headers={
            "Authorization": f"Bearer {user_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"errors": [{"message": str(e)}]}


def get_account_balances(user_token: str) -> list[dict]:
    """Fetch all linked account balances for a user."""
    query = """
    query {
      user {
        bankAccounts {
          name
          accountType
          bankId
          currentBalance { quantity currency }
          availableBalance { quantity currency }
        }
      }
    }
    """
    resp = _gql(user_token, query)
    accounts = resp.get("data", {}).get("user", {}).get("bankAccounts", [])
    return [
        {
            "name":              a.get("name", ""),
            "account_type":      a.get("accountType", ""),
            "bank_id":           a.get("bankId", ""),
            "current_balance":   float(a.get("currentBalance", {}).get("quantity", 0)),
            "available_balance": float(a.get("availableBalance", {}).get("quantity", 0)),
        }
        for a in accounts
    ]


def get_recent_transactions(user_token: str, days: int = 30) -> list[dict]:
    """Fetch recent transactions to detect recurring debit orders."""
    since = (date.today() - timedelta(days=days)).isoformat()
    query = """
    query($filter: TransactionFilterInput) {
      user {
        transactions(filter: $filter) {
          edges {
            node {
              amount { quantity }
              date
              description
              transactionType
            }
          }
        }
      }
    }
    """
    variables = {"filter": {"date": {"gt": since}}}
    resp = _gql(user_token, query, variables)
    edges = (
        resp.get("data", {})
        .get("user", {})
        .get("transactions", {})
        .get("edges", [])
    )
    return [
        {
            "amount":       float(e["node"]["amount"]["quantity"]),
            "date":         e["node"]["date"],
            "description":  e["node"]["description"],
            "type":         e["node"]["transactionType"],
        }
        for e in edges
        if e.get("node")
    ]


def build_stitch_link_url(redirect_uri: str, state: str) -> str:
    """Generate the Stitch Link URL for a user to authorise their bank account."""
    return (
        f"{STITCH_LINK_URL}"
        f"?client_id={STITCH_CLIENT_ID}"
        f"&redirect_uri={redirect_uri}"
        f"&state={state}"
        f"&scope=accounts+transactions"
        f"&response_type=code"
    )


# ─── Safe-to-Spend Calculator ─────────────────────────────────────────────────

@dataclass
class DebitOrder:
    description: str
    amount: float
    due_day: int            # Day of month (1–31)
    days_until_due: int


@dataclass
class SafeToSpendResult:
    bank_balance: float
    total_upcoming_debits: float
    safe_to_spend: float
    debit_orders: list[DebitOrder] = field(default_factory=list)
    data_source: str = "manual"     # "stitch" | "manual"
    accounts: list[dict] = field(default_factory=list)


def calculate_safe_to_spend(
    bank_balance: float,
    debit_orders: list[dict],       # [{"description": "Netflix", "amount": 199, "due_day": 25}]
    buffer_pct: float = 0.05,
) -> SafeToSpendResult:
    """
    Safe-to-Spend = Balance − Upcoming debits (this month) − 5% buffer.
    Only counts debits that haven't gone off yet this month.
    """
    today = date.today()

    upcoming: list[DebitOrder] = []
    for d in debit_orders:
        due_day     = int(d.get("due_day", 1))
        amount      = float(d.get("amount", 0))
        description = d.get("description", "Debit order")

        # Days until this debit goes off this month
        try:
            due_date = date(today.year, today.month, min(due_day, 28))
        except ValueError:
            due_date = date(today.year, today.month, 28)

        days_until = (due_date - today).days
        if days_until >= 0:     # Still upcoming this month
            upcoming.append(DebitOrder(
                description=description,
                amount=amount,
                due_day=due_day,
                days_until_due=days_until,
            ))

    upcoming.sort(key=lambda x: x.days_until_due)
    total_upcoming = sum(d.amount for d in upcoming)
    buffer         = bank_balance * buffer_pct
    safe           = max(0.0, bank_balance - total_upcoming - buffer)

    return SafeToSpendResult(
        bank_balance=round(bank_balance, 2),
        total_upcoming_debits=round(total_upcoming, 2),
        safe_to_spend=round(safe, 2),
        debit_orders=upcoming,
    )


def format_safe_to_spend_message(result: SafeToSpendResult, user_name: str = "") -> str:
    first    = user_name.split()[0] if user_name else None
    greeting = f"Hi {first}! " if first else ""

    def zar(n: float) -> str:
        return f"R{n:,.0f}"

    source_tag = "🔗 _Live from Stitch_" if result.data_source == "stitch" else "📝 _Manual balance_"

    lines = [
        "🏦 *BankBook Safe-to-Spend*",
        source_tag,
        "",
        f"{greeting}Here's your real available cash right now:",
        "",
        f"💳 Bank balance:        *{zar(result.bank_balance)}*",
        f"📅 Upcoming debits:    -*{zar(result.total_upcoming_debits)}*",
        f"🛡 Buffer (5%):        -*{zar(round(result.bank_balance * 0.05, 2))}*",
        "━━━━━━━━━━━━━━━━━━━━",
        f"✅ Safe-to-Spend:      *{zar(result.safe_to_spend)}*",
        "",
    ]

    if result.debit_orders:
        lines.append("📋 *UPCOMING THIS MONTH*")
        for d in result.debit_orders:
            due_str = "today" if d.days_until_due == 0 else f"in {d.days_until_due} day{'s' if d.days_until_due > 1 else ''}"
            lines.append(f"  • {d.description}: *{zar(d.amount)}* ({due_str})")
        lines.append("")

    if result.data_source == "manual":
        lines += [
            "━━━━━━━━━━━━━━━━━━━━",
            "_Connect your bank via Stitch for live balance updates._",
            "_Reply 'Balance 12000' to update your balance manually._",
        ]

    return "\n".join(lines)
