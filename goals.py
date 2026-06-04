from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional
import math


@dataclass
class GoalProgress:
    goal_id: int
    label: str
    target_amount: float
    current_saved: float
    remaining: float
    percent_complete: float
    deadline: Optional[date]
    months_remaining: Optional[int]
    monthly_needed: Optional[float]
    on_track: bool
    status: str  # "on_track" | "behind" | "achieved" | "no_deadline"


@dataclass
class GoalSummary:
    goals: list
    total_saved: float
    total_targets: float
    active_count: int


def months_between(start: date, end: date) -> int:
    return max(0, (end.year - start.year) * 12 + (end.month - start.month))


def evaluate_goal(
    goal_id: int,
    label: str,
    target_amount: float,
    current_saved: float,
    deadline: Optional[date],
    created_at: Optional[datetime] = None,
) -> GoalProgress:
    remaining = max(0.0, target_amount - current_saved)
    percent_complete = min(100.0, round((current_saved / target_amount) * 100, 1)) if target_amount > 0 else 0.0

    if current_saved >= target_amount:
        return GoalProgress(
            goal_id=goal_id,
            label=label,
            target_amount=target_amount,
            current_saved=current_saved,
            remaining=0.0,
            percent_complete=100.0,
            deadline=deadline,
            months_remaining=0,
            monthly_needed=0.0,
            on_track=True,
            status="achieved",
        )

    today = date.today()

    if not deadline:
        return GoalProgress(
            goal_id=goal_id,
            label=label,
            target_amount=target_amount,
            current_saved=current_saved,
            remaining=remaining,
            percent_complete=percent_complete,
            deadline=None,
            months_remaining=None,
            monthly_needed=None,
            on_track=True,
            status="no_deadline",
        )

    months_left = months_between(today, deadline)

    if months_left <= 0:
        return GoalProgress(
            goal_id=goal_id,
            label=label,
            target_amount=target_amount,
            current_saved=current_saved,
            remaining=remaining,
            percent_complete=percent_complete,
            deadline=deadline,
            months_remaining=0,
            monthly_needed=remaining,
            on_track=False,
            status="behind",
        )

    monthly_needed = math.ceil(remaining / months_left)

    total_months = months_between(created_at.date() if created_at else today, deadline)
    if total_months > 0:
        expected_saved = (target_amount / total_months) * (total_months - months_left)
        on_track = current_saved >= (expected_saved * 0.85)
    else:
        on_track = False

    status = "on_track" if on_track else "behind"

    return GoalProgress(
        goal_id=goal_id,
        label=label,
        target_amount=target_amount,
        current_saved=current_saved,
        remaining=remaining,
        percent_complete=percent_complete,
        deadline=deadline,
        months_remaining=months_left,
        monthly_needed=float(monthly_needed),
        on_track=on_track,
        status=status,
    )


def _progress_bar(percent: float, width: int = 10) -> str:
    filled = round((percent / 100) * width)
    return "█" * filled + "░" * (width - filled)


def format_goal_message(progress: GoalProgress, user_name: str = "") -> str:
    name_part = f" {user_name.split()[0]}" if user_name else ""
    lines = [f"🏦 *BankBook Goal Tracker*\n"]

    status_icon = {
        "achieved": "🏆",
        "on_track": "✅",
        "behind": "⚠️",
        "no_deadline": "🎯",
    }.get(progress.status, "🎯")

    lines.append(f"{status_icon} *{progress.label}*")
    lines.append(f"{_progress_bar(progress.percent_complete)}  {progress.percent_complete:.0f}%")
    lines.append(f"")
    lines.append(f"💰 Saved:   R{progress.current_saved:,.0f}")
    lines.append(f"🎯 Target:  R{progress.target_amount:,.0f}")
    lines.append(f"📉 Remaining: R{progress.remaining:,.0f}")

    if progress.status == "achieved":
        lines.append(f"\n🎉 Goal reached{name_part}! Time to set a new one.")
    elif progress.status == "no_deadline":
        lines.append(f"\nKeep going{name_part} — every rand counts!")
    elif progress.deadline:
        deadline_str = progress.deadline.strftime("%B %Y")
        lines.append(f"\n📅 Deadline: {deadline_str}  ({progress.months_remaining} month{'s' if progress.months_remaining != 1 else ''} left)")
        lines.append(f"📆 Save R{progress.monthly_needed:,.0f}/month to hit your target.")
        if progress.status == "behind":
            lines.append(f"\n⚠️ You're a little behind — try to boost your monthly contribution.")
        else:
            lines.append(f"\n✅ You're on track{name_part}. Keep it up!")

    return "\n".join(lines)


def format_goals_summary(goals: list, user_name: str = "") -> str:
    if not goals:
        return (
            "🏦 *BankBook Goal Tracker*\n\n"
            "You haven't set any savings goals yet.\n\n"
            "To add one, reply:\n"
            "_Goal: Save R50000 for Car by December 2026_"
        )

    name_part = f" {user_name.split()[0]}" if user_name else ""
    lines = [f"🏦 *BankBook Goal Tracker*{name_part}\n", f"You have *{len(goals)} active goal{'s' if len(goals) != 1 else ''}*:\n"]
    lines.append("━━━━━━━━━━━━━━━━━━━━")

    total_saved = 0.0
    total_target = 0.0

    for g in goals:
        status_icon = {"achieved": "🏆", "on_track": "✅", "behind": "⚠️", "no_deadline": "🎯"}.get(g["status"], "🎯")
        bar = _progress_bar(g["percent_complete"], width=8)
        lines.append(f"\n{status_icon} *{g['label']}*  {bar} {g['percent_complete']:.0f}%")
        lines.append(f"   R{g['current_saved']:,.0f} / R{g['target_amount']:,.0f}")
        if g.get("monthly_needed") and g["status"] not in ("achieved", "no_deadline"):
            lines.append(f"   → R{g['monthly_needed']:,.0f}/month needed")
        total_saved += g["current_saved"]
        total_target += g["target_amount"]

    lines.append("\n━━━━━━━━━━━━━━━━━━━━")
    overall_pct = round((total_saved / total_target) * 100, 1) if total_target > 0 else 0
    lines.append(f"💰 Total saved: R{total_saved:,.0f} / R{total_target:,.0f}  ({overall_pct}%)")

    return "\n".join(lines)
