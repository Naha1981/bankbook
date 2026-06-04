"""
BankBook Intent Parser — Natural Language → Structured Action

Converts freeform WhatsApp messages into machine-readable intents
covering all BankBook features.
"""

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ParsedIntent:
    intent: str
    # numeric extractions
    amount: Optional[float] = None
    amount2: Optional[float] = None   # second amount (e.g. debt in salary+debt message)
    # text extractions
    label: Optional[str] = None       # goal name, debit description, etc.
    date_str: Optional[str] = None    # deadline / due date string
    due_day: Optional[int] = None     # debit order day of month
    # raw text pass-through
    raw: str = ""


def _clean(text: str) -> str:
    return text.strip().lower()


def _rand(s: str) -> Optional[float]:
    """Extract a rand amount from a string fragment."""
    s = s.replace(",", "").replace(" ", "")
    # Handle shorthand: 1.5m, 1.5M, 500k, 500K
    m = re.match(r"r?([\d.]+)m$", s, re.I)
    if m:
        return float(m.group(1)) * 1_000_000
    m = re.match(r"r?([\d.]+)k$", s, re.I)
    if m:
        return float(m.group(1)) * 1_000
    m = re.match(r"r?([\d.]+)$", s, re.I)
    if m:
        return float(m.group(1))
    return None


def _extract_amount(text: str) -> Optional[float]:
    """Find the first rand amount in text."""
    # Match: R1500, r 1 500, 1500, 1.5m, 1.5M, 500k
    patterns = [
        r"r\s*([\d,]+\.?\d*)\s*(?:m(?:illion)?)\b",
        r"r\s*([\d,]+\.?\d*)\s*(?:k)\b",
        r"r\s*([\d,]+\.?\d*)",
        r"\b([\d,]+\.?\d*)\s*(?:m(?:illion)?)\b",
        r"\b([\d,]+\.?\d*)\s*(?:k)\b",
        r"\b([\d]{3,}(?:[,\s]\d+)*\.?\d*)\b",
    ]
    for p in patterns:
        m = re.search(p, text, re.I)
        if m:
            raw = m.group(0)
            val = _rand(raw)
            if val and val > 0:
                return val
    return None


# Month name → number
MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


def _extract_date(text: str) -> Optional[str]:
    """Try to extract a target date and return ISO string YYYY-MM-DD."""
    import datetime
    today = datetime.date.today()

    # "by December 2026" / "december 2026" / "dec 26"
    m = re.search(r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+(\d{2,4})\b", text, re.I)
    if m:
        month_num = MONTHS.get(m.group(1).lower()[:3])
        year_raw = m.group(2)
        year = int(year_raw) if len(year_raw) == 4 else 2000 + int(year_raw)
        if month_num:
            import calendar
            last_day = calendar.monthrange(year, month_num)[1]
            return f"{year:04d}-{month_num:02d}-{last_day:02d}"

    # "end of year" / "end of 2026"
    m = re.search(r"end of\s+(\d{4})", text, re.I)
    if m:
        return f"{m.group(1)}-12-31"

    # "next year"
    if "next year" in text:
        return f"{today.year + 1}-12-31"

    return None


def parse(raw_text: str) -> ParsedIntent:
    text = raw_text.strip()
    lo = _clean(text)

    # ── HELP / MENU ────────────────────────────────────────────────────────────
    if lo in ("hi", "hello", "hey", "start", "help", "menu", "commands", "what can you do"):
        return ParsedIntent(intent="help", raw=text)
    if re.match(r"^(hi|hello|hey)\b", lo) and len(lo.split()) <= 3:
        return ParsedIntent(intent="help", raw=text)

    # ── NAME ──────────────────────────────────────────────────────────────────
    m = re.search(r"(?:my name is|call me|i am|i'm)\s+([a-z]+)", lo)
    if m:
        return ParsedIntent(intent="set_name", label=m.group(1).title(), raw=text)

    # ── SALARY ────────────────────────────────────────────────────────────────
    if re.search(r"(i earn|salary is|take home|net pay|net salary|i make|my salary|i get paid)\s+r?", lo):
        amt = _extract_amount(lo)
        return ParsedIntent(intent="set_salary", amount=amt, raw=text)

    # ── DEBT ──────────────────────────────────────────────────────────────────
    if re.search(r"(my debt|i owe|total debt|monthly debt|debt is)\s+r?", lo):
        amt = _extract_amount(lo)
        return ParsedIntent(intent="set_debt", amount=amt, raw=text)

    # ── BANK BALANCE ─────────────────────────────────────────────────────────
    if re.search(r"(my balance is|balance is|bank balance|current balance)\s+r?", lo):
        amt = _extract_amount(lo)
        return ParsedIntent(intent="set_balance", amount=amt, raw=text)
    if re.match(r"^balance\s+r?[\d,]+", lo):
        amt = _extract_amount(lo)
        return ParsedIntent(intent="set_balance", amount=amt, raw=text)

    # ── SAFE TO SPEND ─────────────────────────────────────────────────────────
    if re.search(r"(safe to spend|how much can i spend|spending money|what.*spend)", lo):
        return ParsedIntent(intent="safe_to_spend", raw=text)

    # ── DEBIT ORDER ADD ────────────────────────────────────────────────────────
    if re.search(r"(add debit|debit order|monthly debit|recurring)", lo):
        amt = _extract_amount(lo)
        # Extract description: everything after the amount-ish word
        desc_match = re.search(r"(?:add debit|debit order|monthly debit|recurring)[^\d]*r?[\d,]+\s*(?:for\s+)?([a-z][\w\s]+)", lo)
        label = desc_match.group(1).strip().title() if desc_match else "Debit order"
        day_match = re.search(r"(\d+)(?:st|nd|rd|th)", lo)
        due_day = int(day_match.group(1)) if day_match else 1
        return ParsedIntent(intent="add_debit", amount=amt, label=label, due_day=due_day, raw=text)

    # ── AFFORDABILITY ─────────────────────────────────────────────────────────
    if re.search(r"(can i afford|afford a|how much.*afford|what.*afford|bond.*r?[\d]|house.*r?[\d]|property.*r?[\d])", lo):
        amt = _extract_amount(lo)
        return ParsedIntent(intent="affordability", amount=amt, raw=text)

    # ── GOAL DEPOSIT ──────────────────────────────────────────────────────────
    if re.search(r"(saved r|put r|deposited r|added r|saving r)[\d]", lo) or \
       re.search(r"(saved|deposited|added|put)\s+r?[\d,]+\s+(into|for|towards?|toward)\s+", lo):
        amt = _extract_amount(lo)
        # Extract goal name after "for/into/towards"
        gm = re.search(r"(?:into|for|towards?|toward)\s+(?:my\s+)?([a-z][\w\s]+?)(?:\s+goal)?$", lo)
        label = gm.group(1).strip().title() if gm else None
        return ParsedIntent(intent="goal_deposit", amount=amt, label=label, raw=text)

    # ── GOAL CREATE ────────────────────────────────────────────────────────────
    if re.search(r"(save r|goal.*r|want to save|saving for|goal:)", lo):
        amt = _extract_amount(lo)
        date_str = _extract_date(lo)
        # Extract label: word(s) between amount and "by/before/until"
        lm = re.search(r"(?:save r[\d,\.mkMK]+|r[\d,\.mkMK]+)\s+(?:for\s+)?([a-z][\w\s]+?)(?:\s+by|\s+before|\s+until|$)", lo)
        if not lm:
            lm = re.search(r"goal.*?for\s+([a-z][\w\s]+?)(?:\s+by|$)", lo)
        label = lm.group(1).strip().title() if lm else "Goal"
        return ParsedIntent(intent="goal_create", amount=amt, label=label, date_str=date_str, raw=text)

    # ── GOALS LIST ────────────────────────────────────────────────────────────
    if re.search(r"^(my goals|goals|goal progress|show goals|goal status|goals\?)$", lo):
        return ParsedIntent(intent="goals_list", raw=text)
    if lo in ("goals", "my goals"):
        return ParsedIntent(intent="goals_list", raw=text)

    # ── BUDGET LOG (spend entry) ───────────────────────────────────────────────
    if re.search(r"(spent r|paid r|bought r|r[\d,]+\s+\w|spending)", lo) and \
       not re.search(r"(budget summary|how much.*spent|show.*budget|my.*budget)", lo):
        return ParsedIntent(intent="log_spend", raw=text)

    # ── BUDGET SUMMARY ────────────────────────────────────────────────────────
    if re.search(r"(budget|my spending|spending summary|how much.*spent|show.*spending)", lo):
        return ParsedIntent(intent="budget_summary", raw=text)

    # ── NET WORTH ─────────────────────────────────────────────────────────────
    if re.search(r"(net worth|my wealth|how much.*worth|wealth snapshot|total worth)", lo):
        return ParsedIntent(intent="net_worth", raw=text)

    # ── REWARDS ───────────────────────────────────────────────────────────────
    if re.search(r"(rewards|ebucks|discovery miles|vitality|my points)", lo):
        return ParsedIntent(intent="rewards", raw=text)

    # ── TAX ───────────────────────────────────────────────────────────────────
    if re.search(r"(my tax|tax estimate|how much.*tax|sars|provisional tax|tax envelope)", lo):
        return ParsedIntent(intent="tax", raw=text)

    # ── CREDIT SCORE SIM ──────────────────────────────────────────────────────
    if re.search(r"(credit score|credit simulator|what if.*pay off|improve.*credit|credit rating)", lo):
        return ParsedIntent(intent="credit_sim", raw=text)

    # ── FINANCIAL HEALTH / ANOMALY ────────────────────────────────────────────
    if re.search(r"(health check|financial health|check my finances|anomaly|debt check|am i ok)", lo):
        return ParsedIntent(intent="health_check", raw=text)

    # ── BRIEFING ──────────────────────────────────────────────────────────────
    if re.search(r"(briefing|morning briefing|weekly summary|financial summary|my summary)", lo):
        return ParsedIntent(intent="briefing", raw=text)

    return ParsedIntent(intent="unknown", raw=text)
