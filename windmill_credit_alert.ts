/**
 * BankBook Credit Alert — Windmill Scheduled Job
 *
 * Schedule: Every Monday at 07:00 SAST (05:00 UTC)
 * Windmill cron: 0 5 * * 1
 *
 * Purpose: Scans all BankBook users. Any user whose Debt-to-Income ratio
 *          has crept above 35% receives a proactive WhatsApp alert with
 *          their top debt-reduction recommendation from the credit simulator.
 *
 * Required Windmill Variables:
 *   - BANKBOOK_BRAIN_URL   e.g. https://bankbook.onrender.com
 *   - EVOLUTION_API_URL    e.g. https://bankbook-whatsapp-my-evolution-api.onrender.com
 *   - EVOLUTION_API_KEY    Your AUTH_API_KEY from Evolution API
 *   - EVOLUTION_INSTANCE   Your Evolution API instance name (e.g. bankbook)
 */

const BRAIN_URL    = Deno.env.get("BANKBOOK_BRAIN_URL") ?? "";
const EVO_URL      = Deno.env.get("EVOLUTION_API_URL") ?? "";
const EVO_KEY      = Deno.env.get("EVOLUTION_API_KEY") ?? "";
const EVO_INSTANCE = Deno.env.get("EVOLUTION_INSTANCE") ?? "";

// DTI threshold that triggers an alert (35%)
const DTI_ALERT_THRESHOLD = 0.35;

// ─── Types ────────────────────────────────────────────────────────────────────

interface User {
  whatsapp_id: string;
  full_name: string | null;
  net_salary: number;
  total_debt: number;
  onboarding_completed: boolean;
}

interface SimScenario {
  label: string;
  monthly_reduction: number;
  new_score: number;
  score_change: number;
  new_band: string;
  new_dti: number;
  breakeven_months: number | null;
}

interface CreditSimResponse {
  current_score: number;
  current_dti: number;
  current_band: string;
  scenarios: SimScenario[];
  best_scenario: string | null;
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

async function brainPost(path: string, payload: unknown): Promise<unknown | null> {
  try {
    const res = await fetch(`${BRAIN_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
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

function dtiBar(dti: number, width = 10): string {
  const filled = Math.min(width, Math.round((dti / 0.6) * width));
  return "█".repeat(filled) + "░".repeat(Math.max(0, width - filled));
}

// ─── Alert Message Builder ────────────────────────────────────────────────────

function buildAlertMessage(
  user: User,
  sim: CreditSimResponse,
  best: SimScenario | null
): string {
  const firstName = user.full_name ? user.full_name.split(" ")[0] : null;
  const greeting  = firstName ? `, ${firstName}` : "";
  const dtiPct    = Math.round(sim.current_dti * 100);
  const bar       = dtiBar(sim.current_dti);

  const lines: string[] = [
    `🏦 *BankBook Credit Alert*`,
    ``,
    `Hey${greeting} — your debt-to-income ratio needs attention 👇`,
    ``,
    `📊 *Current DTI: ${dtiPct}%*`,
    `${bar}  (Danger zone: above 35%)`,
    ``,
    `  Monthly salary: ${formatZAR(user.net_salary)}`,
    `  Monthly debt:   ${formatZAR(user.total_debt)}`,
    `  Credit score:   *${sim.current_score}/999* — ${sim.current_band}`,
    ``,
    `━━━━━━━━━━━━━━━━━━━━`,
  ];

  if (best) {
    const changeStr = best.score_change >= 0 ? `+${best.score_change}` : String(best.score_change);
    const newDtiPct = Math.round(best.new_dti * 100);

    lines.push(
      `⭐ *BEST ACTION TO TAKE*`,
      ``,
      `💳 Pay off or reduce: *${best.label}*`,
      `  Free up: ${formatZAR(best.monthly_reduction)}/month`,
      `  New DTI: ${newDtiPct}% (down from ${dtiPct}%)`,
      `  New score: *${best.new_score}/999* — ${best.new_band}`,
      `  📈 Score change: *${changeStr} points*`,
    );

    if (best.breakeven_months) {
      lines.push(
        `  ⏳ Cleared in ~${best.breakeven_months} month${best.breakeven_months !== 1 ? "s" : ""} if you focus payments`
      );
    }

    lines.push(``);
  }

  // Context-sensitive coaching tip based on DTI level
  lines.push(`━━━━━━━━━━━━━━━━━━━━`);

  if (sim.current_dti >= 0.50) {
    lines.push(
      `🚨 *URGENT:* Your debt is over 50% of your income.`,
      `Lenders will reject bond applications at this level.`,
      `Focus on paying the smallest debt first to build momentum.`,
    );
  } else if (sim.current_dti >= 0.40) {
    lines.push(
      `⚠️ Your DTI is in the *high-risk* zone.`,
      `You may still get credit, but at much higher interest rates.`,
      `Aim to bring this below 30% over the next 6 months.`,
    );
  } else {
    lines.push(
      `⚠️ You've crossed the 35% warning threshold.`,
      `Action now keeps your credit score healthy.`,
      `Reducing by even R1,000/month makes a meaningful difference.`,
    );
  }

  lines.push(
    ``,
    `_Reply *Credit score* for your full simulation._`,
    `_Reply *Health check* for a complete financial review._`,
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
    return { status: "error", message: "Failed to fetch users" };
  }

  const alerted:  Array<{ whatsapp_id: string; dti: number; sent: boolean }> = [];
  const skipped:  string[] = [];

  for (const user of usersResp.users) {
    // Only check users with salary data
    if (!user.onboarding_completed || user.net_salary === 0) continue;

    const dti = user.total_debt / user.net_salary;

    if (dti <= DTI_ALERT_THRESHOLD) {
      skipped.push(user.whatsapp_id);
      console.log(`✅ OK   ${user.whatsapp_id}  DTI=${Math.round(dti * 100)}%`);
      continue;
    }

    // 2. Run credit simulation — simulate paying off all debt as one scenario
    const simResp = await brainPost("/credit-score-sim", {
      whatsapp_id: user.whatsapp_id,
      debts_to_simulate: [
        { label: "All monthly debt", monthly_amount: user.total_debt },
      ],
    }) as CreditSimResponse | null;

    if (!simResp) {
      console.error(`❌ Failed to run sim for ${user.whatsapp_id}`);
      continue;
    }

    const best = simResp.scenarios.length > 0
      ? simResp.scenarios.reduce((a, b) => (b.score_change > a.score_change ? b : a))
      : null;

    // 3. Build and send alert
    const message = buildAlertMessage(user, simResp, best);
    const sent    = await sendWhatsApp(user.whatsapp_id, message);

    const dtiPct = Math.round(dti * 100);
    console.log(`${sent ? "✅" : "❌"} Alert sent to ${user.whatsapp_id}  DTI=${dtiPct}%  Score=${simResp.current_score}`);
    alerted.push({ whatsapp_id: user.whatsapp_id, dti, sent });
  }

  const succeeded = alerted.filter((a) => a.sent).length;

  return {
    status: "done",
    users_checked: usersResp.users.length,
    alerted: alerted.length,
    alerts_sent: succeeded,
    alerts_failed: alerted.length - succeeded,
    below_threshold: skipped.length,
  };
}
