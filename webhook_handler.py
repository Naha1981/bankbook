"""
BankBook Webhook Handler

Routes parsed intents to the correct Brain logic and formats a WhatsApp reply.
Called directly from the /webhook endpoint — no Make.com or Windmill needed.
"""

import os
import re
import requests
from typing import Optional
from intent import parse, ParsedIntent

EVO_URL      = os.getenv("EVOLUTION_API_URL", "")
EVO_KEY      = os.getenv("EVOLUTION_API_KEY", "")
EVO_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "bankbook")

HELP_TEXT = (
    "🏦 *BankBook AI — Your Financial OS*\n\n"
    "Here's what I can do:\n\n"
    "💰 *Profile*\n"
    "  _I earn 35000_ — set your salary\n"
    "  _My debt is 8000_ — set monthly debt\n"
    "  _My name is John_ — set your name\n\n"
    "🏠 *Property*\n"
    "  _Can I afford a R1.5M house?_\n\n"
    "💳 *Spending*\n"
    "  _Spent R200 at KFC_ — log an expense\n"
    "  _Budget_ — see this month's breakdown\n\n"
    "🏦 *Banking*\n"
    "  _Balance 42000_ — update your balance\n"
    "  _Safe to spend_ — see available cash\n"
    "  _Add debit R1500 Netflix_ — track debits\n\n"
    "🎯 *Goals*\n"
    "  _Save R50000 for Car by December 2026_\n"
    "  _Saved R2000 for Car_ — log a deposit\n"
    "  _My goals_ — see progress\n\n"
    "📊 *Analysis*\n"
    "  _Net worth_ — full wealth snapshot\n"
    "  _Health check_ — financial risk scan\n"
    "  _Briefing_ — weekly summary\n"
    "  _Credit score_ — score simulator\n"
    "  _My tax_ — SARS tax estimate\n"
    "  _My rewards_ — loyalty points value\n\n"
    "_BankBook — Your whole financial life, finally in one book._ 🇿🇦"
)


def send_whatsapp(to: str, text: str) -> bool:
    """Send a WhatsApp message via Evolution API."""
    if not EVO_URL or not EVO_KEY:
        return False
    try:
        resp = requests.post(
            f"{EVO_URL}/message/sendText/{EVO_INSTANCE}",
            json={"number": to, "text": text},
            headers={"Content-Type": "application/json", "apikey": EVO_KEY},
            timeout=10,
        )
        return resp.ok
    except Exception:
        return False


def _clean_sender(remote_jid: str) -> str:
    """Strip @s.whatsapp.net or @g.us suffix."""
    return remote_jid.split("@")[0]


def handle_webhook(body: dict) -> dict:
    """
    Main entry point. Receives raw Evolution API webhook payload,
    routes to the correct handler, sends reply, returns status dict.
    """
    # Only process inbound messages
    event = body.get("event", "")
    if event not in ("messages.upsert", "messages.update", "MESSAGES_UPSERT"):
        return {"status": "ignored_event", "event": event}

    data = body.get("data", {})
    key  = data.get("key", {})

    if key.get("fromMe"):
        return {"status": "skipped_outgoing"}

    remote_jid = key.get("remoteJid", "")
    # Skip group messages
    if "@g.us" in remote_jid:
        return {"status": "skipped_group"}

    sender = _clean_sender(remote_jid)
    if not sender:
        return {"status": "no_sender"}

    msg = data.get("message", {})
    text = (
        msg.get("conversation")
        or msg.get("extendedTextMessage", {}).get("text")
        or ""
    ).strip()

    if not text:
        return {"status": "no_text"}

    # Parse intent and route
    parsed = parse(text)
    reply  = _route(sender, parsed)

    if reply:
        sent = send_whatsapp(remote_jid, reply)
        return {"status": "replied", "intent": parsed.intent, "sent": sent}

    return {"status": "no_reply", "intent": parsed.intent}


# ── Routing ───────────────────────────────────────────────────────────────────

def _route(sender: str, p: ParsedIntent) -> Optional[str]:
    from database import engine
    from sqlmodel import Session, select
    from models import (
        UserProfile, Property, Insurance, Reward, SavingsGoal,
        GoalDeposit, BankBalance, DebitOrderRecord, SpendEntry,
    )

    with Session(engine) as session:

        def get_user():
            return session.exec(
                select(UserProfile).where(UserProfile.whatsapp_id == sender)
            ).first()

        def ensure_user():
            u = get_user()
            if not u:
                u = UserProfile(whatsapp_id=sender, net_salary=0.0, total_debt=0.0)
                session.add(u)
                session.commit()
                session.refresh(u)
            return u

        # ── HELP ──────────────────────────────────────────────────────────────
        if p.intent == "help":
            return HELP_TEXT

        # ── SET NAME ──────────────────────────────────────────────────────────
        if p.intent == "set_name":
            user = ensure_user()
            user.full_name = p.label
            session.commit()
            return f"🏦 *BankBook*\n\n✅ Got it! I'll call you *{p.label}* from now on.\n\nReply *Help* to see what I can do."

        # ── SET SALARY ────────────────────────────────────────────────────────
        if p.intent == "set_salary":
            if not p.amount:
                return "🏦 *BankBook*\n\nI couldn't read that salary. Try:\n_I earn 35000_"
            user = ensure_user()
            user.net_salary = p.amount
            user.onboarding_completed = True
            session.commit()
            return (
                f"🏦 *BankBook Updated*\n\n"
                f"✅ Salary saved: *R{p.amount:,.0f}/month*\n\n"
                f"Now try:\n"
                f"• _My debt is 5000_ — add your debt\n"
                f"• _Can I afford a R1.5M house?_"
            )

        # ── SET DEBT ──────────────────────────────────────────────────────────
        if p.intent == "set_debt":
            if not p.amount:
                return "🏦 *BankBook*\n\nI couldn't read that debt amount. Try:\n_My debt is 8000_"
            user = ensure_user()
            user.total_debt = p.amount
            session.commit()
            dti = round((user.total_debt / user.net_salary * 100), 1) if user.net_salary else 0
            status = "✅ Healthy" if dti < 30 else ("⚠️ High" if dti < 40 else "🔴 Very High")
            return (
                f"🏦 *BankBook Updated*\n\n"
                f"✅ Monthly debt saved: *R{p.amount:,.0f}/month*\n"
                f"Debt-to-income ratio: *{dti}%* {status}\n\n"
                f"Reply _Health check_ for a full financial risk scan."
            )

        # ── AFFORDABILITY ─────────────────────────────────────────────────────
        if p.intent == "affordability":
            user = get_user()
            if not user or user.net_salary == 0:
                return (
                    "🏦 *BankBook*\n\nI need your salary first.\n\n"
                    "Reply: _I earn [your monthly take-home]_\n"
                    "Example: _I earn 45000_"
                )
            if not p.amount:
                return "🏦 *BankBook*\n\nWhich property price? Example:\n_Can I afford a R1.8M house?_"

            from calculations import calculate_affordability
            result = calculate_affordability(
                salary=user.net_salary, debt=user.total_debt, price=p.amount
            )
            if result.get("is_affordable"):
                return (
                    f"🏦 *BankBook Property Analysis*\n\n"
                    f"✅ *R{p.amount:,.0f} is affordable!*\n\n"
                    f"📋 Monthly bond: *R{result['repayment']:,.0f}*\n"
                    f"📈 Rate: {result.get('annual_rate_pct', 11.75)}% over {result.get('term_years', 20)} years\n\n"
                    f"Reply _Net worth_ to see your full wealth picture."
                )
            else:
                return (
                    f"🏦 *BankBook Property Analysis*\n\n"
                    f"⚠️ *R{p.amount:,.0f} is over your limit*\n\n"
                    f"📋 Required repayment: R{result.get('repayment', 0):,.0f}/month\n"
                    f"❌ Shortfall: R{result.get('shortfall', 0):,.0f}/month\n\n"
                    f"✅ *Your max affordable price: R{result.get('max_affordable_price', 0):,.0f}*\n\n"
                    f"Reply _Credit score_ to see how paying off debt boosts your bond approval."
                )

        # ── LOG SPEND ─────────────────────────────────────────────────────────
        if p.intent == "log_spend":
            from budget import parse_spend_message, categorise, format_spend_confirm
            from datetime import date as date_type
            parsed_spend = parse_spend_message(p.raw)
            if not parsed_spend:
                return "🏦 *BankBook*\n\nI couldn't read that spend. Try:\n_Spent R200 at KFC_"
            ensure_user()
            category = categorise(parsed_spend["description"])
            entry = SpendEntry(
                whatsapp_id=sender,
                description=parsed_spend["description"],
                amount=parsed_spend["amount"],
                category=category,
                entry_date=date_type.today(),
                raw_text=p.raw,
            )
            session.add(entry)
            session.commit()
            return format_spend_confirm(parsed_spend["description"], parsed_spend["amount"], category)

        # ── BUDGET SUMMARY ────────────────────────────────────────────────────
        if p.intent == "budget_summary":
            from budget import build_budget_summary, format_budget_summary
            from datetime import date as date_type
            today = date_type.today()
            month_start = date_type(today.year, today.month, 1)
            entries = session.exec(
                select(SpendEntry).where(
                    SpendEntry.whatsapp_id == sender,
                    SpendEntry.entry_date >= month_start,
                )
            ).all()
            if not entries:
                return (
                    "🏦 *BankBook*\n\n"
                    "No spending logged this month yet.\n\n"
                    "To start: _Spent R200 at KFC_"
                )
            user = get_user()
            summary = build_budget_summary(
                entries=[{"category": e.category, "amount": e.amount} for e in entries],
                net_salary=user.net_salary if user else 0.0,
                month_label=today.strftime("%B %Y"),
            )
            return format_budget_summary(summary)

        # ── SET BALANCE ───────────────────────────────────────────────────────
        if p.intent == "set_balance":
            if not p.amount:
                return "🏦 *BankBook*\n\nI couldn't read the balance. Try:\n_Balance 42000_"
            from stitch import calculate_safe_to_spend, format_safe_to_spend_message
            from datetime import datetime as dt_type
            user = ensure_user()
            bal = session.exec(select(BankBalance).where(BankBalance.whatsapp_id == sender)).first()
            if bal:
                bal.balance = p.amount
                bal.updated_at = dt_type.utcnow()
            else:
                session.add(BankBalance(whatsapp_id=sender, balance=p.amount, data_source="manual"))
            session.commit()
            debits = session.exec(
                select(DebitOrderRecord).where(
                    DebitOrderRecord.whatsapp_id == sender,
                    DebitOrderRecord.is_active == True,
                )
            ).all()
            result = calculate_safe_to_spend(
                p.amount,
                [{"description": d.description, "amount": d.amount, "due_day": d.due_day} for d in debits],
            )
            return format_safe_to_spend_message(result, user_name=user.full_name or "")

        # ── SAFE TO SPEND ─────────────────────────────────────────────────────
        if p.intent == "safe_to_spend":
            from stitch import calculate_safe_to_spend, format_safe_to_spend_message
            bal = session.exec(select(BankBalance).where(BankBalance.whatsapp_id == sender)).first()
            if not bal:
                return (
                    "🏦 *BankBook*\n\nI don't have your balance yet.\n\n"
                    "Reply: _Balance 42000_"
                )
            debits = session.exec(
                select(DebitOrderRecord).where(
                    DebitOrderRecord.whatsapp_id == sender,
                    DebitOrderRecord.is_active == True,
                )
            ).all()
            result = calculate_safe_to_spend(
                bal.balance,
                [{"description": d.description, "amount": d.amount, "due_day": d.due_day} for d in debits],
            )
            user = get_user()
            return format_safe_to_spend_message(result, user_name=(user.full_name or "") if user else "")

        # ── ADD DEBIT ORDER ───────────────────────────────────────────────────
        if p.intent == "add_debit":
            if not p.amount:
                return "🏦 *BankBook*\n\nTry: _Add debit R1500 Netflix on the 1st_"
            ensure_user()
            existing = session.exec(
                select(DebitOrderRecord).where(
                    DebitOrderRecord.whatsapp_id == sender,
                    DebitOrderRecord.description == (p.label or "Debit"),
                )
            ).first()
            if existing:
                existing.amount = p.amount
                existing.due_day = p.due_day or 1
            else:
                session.add(DebitOrderRecord(
                    whatsapp_id=sender,
                    description=p.label or "Debit",
                    amount=p.amount,
                    due_day=p.due_day or 1,
                ))
            session.commit()
            all_debits = session.exec(
                select(DebitOrderRecord).where(
                    DebitOrderRecord.whatsapp_id == sender, DebitOrderRecord.is_active == True
                )
            ).all()
            total = sum(d.amount for d in all_debits)
            return (
                f"🏦 *BankBook*\n\n"
                f"✅ Debit saved: *{p.label}* — R{p.amount:,.0f} on the {p.due_day or 1}{_ordinal(p.due_day or 1)}\n\n"
                f"You have *{len(all_debits)} debit{'s' if len(all_debits) != 1 else ''}* totalling *R{total:,.0f}/month*.\n\n"
                f"Reply _Safe to spend_ to see your updated balance."
            )

        # ── GOALS LIST ────────────────────────────────────────────────────────
        if p.intent == "goals_list":
            from goals import evaluate_goal, format_goals_summary
            user = get_user()
            goals = session.exec(
                select(SavingsGoal).where(SavingsGoal.whatsapp_id == sender, SavingsGoal.is_active == True)
            ).all()
            goal_list = [
                {
                    "label": g.label,
                    "target_amount": g.target_amount,
                    "current_saved": g.current_saved,
                    "remaining": max(0, g.target_amount - g.current_saved),
                    "percent_complete": min(100, round(g.current_saved / g.target_amount * 100, 1)) if g.target_amount else 0,
                    "monthly_needed": evaluate_goal(g.id, g.label, g.target_amount, g.current_saved, g.deadline, g.created_at).monthly_needed,
                    "status": evaluate_goal(g.id, g.label, g.target_amount, g.current_saved, g.deadline, g.created_at).status,
                }
                for g in goals
            ]
            return format_goals_summary(goal_list, user_name=(user.full_name or "") if user else "")

        # ── GOAL CREATE ────────────────────────────────────────────────────────
        if p.intent == "goal_create":
            if not p.amount:
                return (
                    "🏦 *BankBook*\n\nTry:\n"
                    "_Save R50000 for Car by December 2026_"
                )
            from goals import evaluate_goal, format_goal_message
            from datetime import date as date_type
            user = ensure_user()
            deadline = date_type.fromisoformat(p.date_str) if p.date_str else None
            goal = SavingsGoal(
                whatsapp_id=sender,
                label=p.label or "Goal",
                target_amount=p.amount,
                current_saved=0.0,
                deadline=deadline,
            )
            session.add(goal)
            session.commit()
            session.refresh(goal)
            progress = evaluate_goal(goal.id, goal.label, goal.target_amount, 0.0, deadline, goal.created_at)
            return format_goal_message(progress, user_name=user.full_name or "")

        # ── GOAL DEPOSIT ──────────────────────────────────────────────────────
        if p.intent == "goal_deposit":
            if not p.amount:
                return "🏦 *BankBook*\n\nTry:\n_Saved R2000 for Car_"
            from goals import evaluate_goal, format_goal_message
            from datetime import datetime as dt_type
            # Find the matching goal
            goals = session.exec(
                select(SavingsGoal).where(SavingsGoal.whatsapp_id == sender, SavingsGoal.is_active == True)
            ).all()
            goal = None
            if p.label and goals:
                # fuzzy match label
                label_lo = p.label.lower()
                for g in goals:
                    if label_lo in g.label.lower() or g.label.lower() in label_lo:
                        goal = g
                        break
            if not goal and goals:
                goal = goals[0]  # fallback to most recent active goal
            if not goal:
                return (
                    "🏦 *BankBook*\n\nYou don't have any active goals yet.\n\n"
                    "To create one: _Save R50000 for Car by December 2026_"
                )
            goal.current_saved += p.amount
            goal.updated_at = dt_type.utcnow()
            session.add(GoalDeposit(goal_id=goal.id, whatsapp_id=sender, amount=p.amount))
            session.commit()
            session.refresh(goal)
            user = get_user()
            progress = evaluate_goal(goal.id, goal.label, goal.target_amount, goal.current_saved, goal.deadline, goal.created_at)
            return format_goal_message(progress, user_name=(user.full_name or "") if user else "")

        # ── NET WORTH ─────────────────────────────────────────────────────────
        if p.intent == "net_worth":
            from networth import calculate_net_worth, format_net_worth_message
            from rewards import evaluate_rewards
            user = get_user()
            if not user:
                return "🏦 *BankBook*\n\nSet up your profile first.\nReply: _I earn 35000_"
            properties = session.exec(select(Property).where(Property.whatsapp_id == sender)).all()
            goals      = session.exec(select(SavingsGoal).where(SavingsGoal.whatsapp_id == sender, SavingsGoal.is_active == True)).all()
            balance    = session.exec(select(BankBalance).where(BankBalance.whatsapp_id == sender)).first()
            rewards    = session.exec(select(Reward).where(Reward.whatsapp_id == sender)).all()
            rewards_rand = 0.0
            if rewards:
                rr = evaluate_rewards(sender, [
                    {"program": r.program, "balance": r.balance,
                     "expiry_date": r.expiry_date.isoformat() if r.expiry_date else None}
                    for r in rewards
                ])
                rewards_rand = rr.total_rand_value
            report = calculate_net_worth(
                net_salary=user.net_salary,
                total_debt=user.total_debt,
                properties=[p_.model_dump() for p_ in properties],
                goals=[{"label": g.label, "current_saved": g.current_saved} for g in goals],
                bank_balance=balance.balance if balance else 0.0,
                rewards_rand_value=rewards_rand,
            )
            return format_net_worth_message(report, user_name=user.full_name or "")

        # ── HEALTH CHECK ──────────────────────────────────────────────────────
        if p.intent == "health_check":
            from anomaly import detect_anomalies, format_anomaly_alert
            user = get_user()
            if not user:
                return "🏦 *BankBook*\n\nSet up your profile first.\nReply: _I earn 35000_"
            properties = session.exec(select(Property).where(Property.whatsapp_id == sender)).all()
            insurance  = session.exec(select(Insurance).where(Insurance.whatsapp_id == sender)).all()
            report = detect_anomalies(
                whatsapp_id=sender,
                net_salary=user.net_salary,
                total_debt=user.total_debt,
                properties=[p_.model_dump() for p_ in properties],
                insurance_count=len(insurance),
            )
            return format_anomaly_alert(report, user_name=user.full_name or "")

        # ── BRIEFING ──────────────────────────────────────────────────────────
        if p.intent == "briefing":
            from briefing import build_briefing_message
            user = get_user()
            if not user:
                return "🏦 *BankBook*\n\nSet up your profile first.\nReply: _I earn 35000_"
            properties = session.exec(select(Property).where(Property.whatsapp_id == sender)).all()
            insurance  = session.exec(select(Insurance).where(Insurance.whatsapp_id == sender)).all()
            return build_briefing_message(
                user_name=user.full_name or "",
                net_salary=user.net_salary,
                total_debt=user.total_debt,
                properties=[p_.model_dump() for p_ in properties],
                insurance_count=len(insurance),
            )

        # ── REWARDS ───────────────────────────────────────────────────────────
        if p.intent == "rewards":
            from rewards import evaluate_rewards, format_rewards_message
            user = get_user()
            saved = session.exec(select(Reward).where(Reward.whatsapp_id == sender)).all()
            if not saved:
                return (
                    "🏦 *BankBook*\n\nNo rewards on file yet.\n\n"
                    "To add: send your rewards balances, e.g.:\n"
                    "_eBucks: 5000_\n_Discovery Miles: 12000_"
                )
            report = evaluate_rewards(sender, [
                {"program": r.program, "balance": r.balance,
                 "expiry_date": r.expiry_date.isoformat() if r.expiry_date else None}
                for r in saved
            ])
            return format_rewards_message(report, user_name=(user.full_name or "") if user else "")

        # ── TAX ───────────────────────────────────────────────────────────────
        if p.intent == "tax":
            from tax import calculate_tax_envelope, format_tax_message
            from models import TaxRecord
            user   = get_user()
            record = session.exec(select(TaxRecord).where(TaxRecord.whatsapp_id == sender)).first()
            if not record:
                return (
                    "🏦 *BankBook Tax*\n\n"
                    "I need your income details first.\n\n"
                    "Reply with your annual income:\n"
                    "_My annual income is R420000_"
                )
            envelope = calculate_tax_envelope(
                annual_income=record.annual_income,
                annual_expenses=record.annual_expenses,
                rental_income=record.rental_income,
                rental_expenses=record.rental_expenses,
                age=record.age,
                medical_aid_dependants=record.medical_aid_dependants,
                income_type=record.income_type,
            )
            return format_tax_message(envelope, user_name=(user.full_name or "") if user else "", income_type=record.income_type)

        # ── CREDIT SCORE SIM ──────────────────────────────────────────────────
        if p.intent == "credit_sim":
            from creditscore import simulate_credit_score, format_credit_sim_message
            user = get_user()
            if not user or user.net_salary == 0:
                return "🏦 *BankBook*\n\nI need your salary first.\nReply: _I earn 35000_"
            # Simulate paying off total debt as single scenario
            report = simulate_credit_score(
                net_salary=user.net_salary,
                total_debt=user.total_debt,
                debts_to_simulate=[
                    {"label": "All monthly debt", "monthly_amount": user.total_debt}
                ] if user.total_debt > 0 else [
                    {"label": "Sample: R5000 car loan", "monthly_amount": 5000}
                ],
            )
            return format_credit_sim_message(report, user_name=user.full_name or "")

        # ── UNKNOWN ───────────────────────────────────────────────────────────
        return (
            "🏦 *BankBook*\n\nI didn't quite catch that.\n\n"
            "Try:\n"
            "• _I earn 45000_ — set salary\n"
            "• _Spent R200 at KFC_ — log spend\n"
            "• _Can I afford R1.5M?_ — bond check\n"
            "• _Help_ — see all commands"
        )

    return None


def _ordinal(n: int) -> str:
    if 11 <= (n % 100) <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
