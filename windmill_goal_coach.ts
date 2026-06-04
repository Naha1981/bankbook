/**
 * BankBook Goal Coach — Windmill Scheduled Job
 *
 * Schedule: 1st of every month at 08:00 SAST (06:00 UTC)
 * Windmill cron: 0 6 1 * *
 *
 * Purpose: Fetches every BankBook user's active savings goals and sends
 *          a personalised WhatsApp coaching nudge via Evolution API.
 *          Shows progress bars, how much to save this month, and
 *          motivational context to keep users on track.
 *
 * Required Windmill Variables:
 *   - BANKBOOK_BRAIN_URL   e.g. https://bankbook.onrender.com
 *   - EVOLUTION_API_URL    e.g. https://bankbook-whatsapp.onrender.com
 *   - EVOLUTION_API_KEY    Your AUTH_API_KEY from Evolution API
 *   - EVOLUTION_INSTANCE   Your Evolution API instance name
 */

const BRAIN_URL    = Deno.env.get("BANKBOOK_BRAIN_URL") ?? "";
const EVO_URL      = Deno.env.get("EVOLUTION_API_URL") ?? "";
const EVO_KEY      = Deno.env.get("EVOLUTION_API_KEY") ?? "";
const EVO_INSTANCE = Deno.env.get("EVOLUTION_INSTANCE") ?? "";

// ─── Types ────────────────────────────────────────────────────────────────────

interface User {
  whatsapp_id: string;
  full_name: string | null;
  net_salary: number;
  total_debt: number;
  onboarding_completed: boolean;
}

interface Goal {
  goal_id: number;
  label: string;
  target_amount: number;
  current_saved: number;
  remaining: number;
  percent_complete: number;
  monthly_needed: number | null;
  months_remaining: number | null;
  status: "on_track" | "behind" | "achieved" | "no_deadline";
  deadline: string | null;
}

interface GoalsResponse {
  goals: Goal[];
  active_count: number;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

async function brainGet(path: string): Promise<unknown | null> {
  try {
    const res = await fetch(`${BRAIN_URL}${path}`);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

async function sendWhatsApp(to: string, text: string): Promise<boolean> {
  try {
    const res = await fetch(`${EVO_URL}/message/sendText/${EVO_INSTANCE}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", apikey: EVO_KEY },
      body: JSON.stringify({ number: to, text }),
    });
    return res.ok;
  } catch {
    return false;
  }
}

function formatZAR(n: number): string {
  return `R${Math.round(n).toLocaleString("en-ZA")}`;
}

function progressBar(percent: number, width = 10): string {
  const filled = Math.round((percent / 100) * width);
  return "█".repeat(filled) + "░".repeat(width - filled);
}

function monthName(): string {
  return new Date().toLocaleDateString("en-ZA", { month: "long", year: "numeric" });
}

// ─── Message Builder ──────────────────────────────────────────────────────────

function buildCoachMessage(user: User, goals: Goal[]): string {
  const firstName = user.full_name ? user.full_name.split(" ")[0] : null;
  const greeting  = firstName ? `, ${firstName}` : "";

  // Split goals into buckets
  const achieved  = goals.filter((g) => g.status === "achieved");
  const active    = goals.filter((g) => g.status !== "achieved");
  const behind    = active.filter((g) => g.status === "behind");
  const onTrack   = active.filter((g) => g.status === "on_track" || g.status === "no_deadline");

  const lines: string[] = [
    `🏦 *BankBook Goal Coach*`,
    `_${monthName()} check-in_`,
    ``,
    `Hey${greeting}! Here's how your savings goals are looking this month 👇`,
    ``,
    `━━━━━━━━━━━━━━━━━━━━`,
  ];

  // ── On-track goals ──
  if (onTrack.length > 0) {
    lines.push(`✅ *ON TRACK*`);
    for (const g of onTrack) {
      const bar = progressBar(g.percent_complete, 10);
      lines.push(``, `🎯 *${g.label}*`);
      lines.push(`${bar}  ${g.percent_complete.toFixed(0)}%`);
      lines.push(`Saved: ${formatZAR(g.current_saved)} / ${formatZAR(g.target_amount)}`);
      if (g.monthly_needed && g.months_remaining !== null && g.months_remaining > 0) {
        lines.push(`This month: save *${formatZAR(g.monthly_needed)}* to stay on track`);
        lines.push(`_${g.months_remaining} month${g.months_remaining !== 1 ? "s" : ""} to go_`);
      } else if (g.status === "no_deadline") {
        lines.push(`_No deadline set — every rand counts!_`);
      }
    }
    lines.push(``);
  }

  // ── Behind goals ──
  if (behind.length > 0) {
    lines.push(`━━━━━━━━━━━━━━━━━━━━`);
    lines.push(`⚠️ *NEEDS ATTENTION*`);
    for (const g of behind) {
      const bar = progressBar(g.percent_complete, 10);
      const shortfall = g.monthly_needed
        ? Math.ceil(g.monthly_needed * 1.25)  // 25% catch-up boost
        : null;
      lines.push(``, `📉 *${g.label}*`);
      lines.push(`${bar}  ${g.percent_complete.toFixed(0)}%`);
      lines.push(`Saved: ${formatZAR(g.current_saved)} / ${formatZAR(g.target_amount)}`);
      lines.push(`Still needed: *${formatZAR(g.remaining)}*`);
      if (shortfall) {
        lines.push(`To catch up: save *${formatZAR(shortfall)}* this month`);
      }
      if (g.months_remaining !== null && g.months_remaining > 0) {
        lines.push(`_${g.months_remaining} month${g.months_remaining !== 1 ? "s" : ""} remaining_`);
      }
    }
    lines.push(``);
  }

  // ── Achieved goals ──
  if (achieved.length > 0) {
    lines.push(`━━━━━━━━━━━━━━━━━━━━`);
    for (const g of achieved) {
      lines.push(`🏆 *${g.label}* — Goal reached! ${formatZAR(g.current_saved)} saved ✅`);
    }
    lines.push(``);
  }

  // ── Salary-based coaching tip ──
  lines.push(`━━━━━━━━━━━━━━━━━━━━`);
  const totalMonthlyNeeded = active.reduce((sum, g) => sum + (g.monthly_needed ?? 0), 0);
  if (user.net_salary > 0 && totalMonthlyNeeded > 0) {
    const pctOfSalary = Math.round((totalMonthlyNeeded / user.net_salary) * 100);
    lines.push(`💡 *This month's savings target: ${formatZAR(totalMonthlyNeeded)}*`);
    lines.push(`That's ${pctOfSalary}% of your take-home — ${
      pctOfSalary <= 20 ? "a healthy savings rate 👏" :
      pctOfSalary <= 30 ? "a solid commitment 💪" :
      "ambitious! Adjust if needed 🙏"
    }`);
    lines.push(``);
  }

  // ── Quick-action prompt ──
  lines.push(
    `_To log a deposit, reply:_`,
    `_"Saved R[amount] for [goal name]"_`,
    ``,
    `_To see full details, reply: *My goals*_`,
  );

  return lines.join("\n");
}

// ─── Main ─────────────────────────────────────────────────────────────────────

export async function main() {
  if (!BRAIN_URL || !EVO_URL || !EVO_KEY || !EVO_INSTANCE) {
    console.error("Missing required environment variables.");
    return { status: "error", message: "Missing env vars" };
  }

  // 1. Fetch all users
  const usersResp = await brainGet("/users") as { users: User[] } | null;
  if (!usersResp || !Array.isArray(usersResp.users)) {
    console.error("Could not fetch users from BankBook Brain.");
    return { status: "error", message: "Failed to fetch users" };
  }

  const results: Array<{ whatsapp_id: string; sent: boolean; goal_count: number }> = [];

  for (const user of usersResp.users) {
    // Only message users who completed onboarding
    if (!user.onboarding_completed) continue;

    // 2. Fetch this user's goals
    const goalsResp = await brainGet(`/goal/${encodeURIComponent(user.whatsapp_id)}`) as GoalsResponse | null;

    // Skip if no active goals
    if (!goalsResp || goalsResp.active_count === 0) {
      console.log(`⏭  No active goals for ${user.whatsapp_id} — skipping`);
      continue;
    }

    // 3. Build and send the coaching message
    const message = buildCoachMessage(user, goalsResp.goals);
    const sent    = await sendWhatsApp(user.whatsapp_id, message);

    console.log(`${sent ? "✅" : "❌"} Goal coach sent to ${user.whatsapp_id} (${goalsResp.active_count} goal${goalsResp.active_count !== 1 ? "s" : ""})`);
    results.push({ whatsapp_id: user.whatsapp_id, sent, goal_count: goalsResp.active_count });
  }

  const succeeded = results.filter((r) => r.sent).length;
  const skipped   = usersResp.users.length - results.length;

  return {
    status: "done",
    total_messaged: results.length,
    succeeded,
    failed: results.length - succeeded,
    skipped_no_goals: skipped,
  };
}
