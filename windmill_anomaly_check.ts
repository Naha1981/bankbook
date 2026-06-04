/**
 * BankBook Anomaly Check — Windmill Scheduled Job
 *
 * Schedule: Every Friday at 17:00 SAST (15:00 UTC) — end-of-week risk review
 * Windmill cron: 0 15 * * 5
 *
 * Purpose: Fetches every BankBook user, checks their financial health,
 *          and sends a WhatsApp alert if any risk thresholds are breached.
 *
 * Required Windmill Variables:
 *   - BANKBOOK_BRAIN_URL   e.g. https://bankbook-brain.onrender.com
 *   - EVOLUTION_API_URL    e.g. https://bankbook-whatsapp.onrender.com
 *   - EVOLUTION_API_KEY    Your AUTH_API_KEY from Evolution API
 *   - EVOLUTION_INSTANCE   Your Evolution API instance name
 */

const BRAIN_URL    = Deno.env.get("BANKBOOK_BRAIN_URL") ?? "";
const EVO_URL      = Deno.env.get("EVOLUTION_API_URL") ?? "";
const EVO_KEY      = Deno.env.get("EVOLUTION_API_KEY") ?? "";
const EVO_INSTANCE = Deno.env.get("EVOLUTION_INSTANCE") ?? "";

// ─── Thresholds (mirror anomaly.py) ────────────────────────────────────────────

const DTI_WARN    = 0.30;
const DTI_DANGER  = 0.40;
const HIGH_LTV    = 0.80;

// ─── Helpers ───────────────────────────────────────────────────────────────────

async function brainGet(path: string) {
  const res = await fetch(`${BRAIN_URL}${path}`);
  if (!res.ok) return null;
  return res.json();
}

async function sendWhatsApp(to: string, text: string): Promise<boolean> {
  const res = await fetch(`${EVO_URL}/message/sendText/${EVO_INSTANCE}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", apikey: EVO_KEY },
    body: JSON.stringify({ number: to, text }),
  });
  return res.ok;
}

// ─── Anomaly Detection ─────────────────────────────────────────────────────────

type Anomaly = { icon: string; label: string; detail: string; action: string };

function detectAnomalies(
  salary: number,
  debt: number,
  properties: Array<{ address: string; estimated_value: number; bond_balance: number }>,
  insuranceCount: number,
): Anomaly[] {
  const issues: Anomaly[] = [];
  if (salary <= 0) return issues;

  const dti = debt / salary;

  if (dti >= DTI_DANGER) {
    issues.push({
      icon: "🚨",
      label: "Critical DTI",
      detail: `Your debt-to-income ratio is ${(dti * 100).toFixed(0)}% — banks cap at 30%. New credit will be rejected.`,
      action: "Prioritise paying off your highest-interest debt immediately.",
    });
  } else if (dti >= DTI_WARN) {
    issues.push({
      icon: "⚠️",
      label: "High DTI",
      detail: `Your debt-to-income ratio is ${(dti * 100).toFixed(0)}% — at the SA bank limit.`,
      action: "Avoid new credit until this drops below 25%.",
    });
  }

  for (const prop of properties) {
    if (prop.estimated_value > 0 && prop.bond_balance > 0) {
      const ltv = prop.bond_balance / prop.estimated_value;
      if (ltv >= HIGH_LTV) {
        issues.push({
          icon: "⚠️",
          label: "High LTV",
          detail: `Bond on '${prop.address}' is ${(ltv * 100).toFixed(0)}% of its value.`,
          action: "Make extra bond payments to build equity faster.",
        });
      }
    }
  }

  if (properties.length > 0 && insuranceCount === 0) {
    issues.push({
      icon: "🚨",
      label: "No Insurance",
      detail: "You own property but have no insurance policies in your BankBook.",
      action: "Add your home and car insurance. Reply 'Insurance' to get started.",
    });
  }

  const safeToSpend = salary - debt - salary * 0.05;
  if (safeToSpend < salary * 0.10) {
    issues.push({
      icon: "🚨",
      label: "Cash Crunch",
      detail: `Less than 10% of your salary is available after debt (R${safeToSpend.toLocaleString("en-ZA", { maximumFractionDigits: 0 })}).`,
      action: "Review your debit orders and cut discretionary spending this month.",
    });
  }

  return issues;
}

function buildAlertMessage(name: string | null, issues: Anomaly[]): string {
  const first = name?.split(" ")[0] ?? null;
  const greeting = first ? `Hi ${first}! ` : "Hi! ";

  if (issues.length === 0) {
    return (
      `🏦 *BankBook Health Check*\n\n` +
      `${greeting}✅ Your finances look healthy — no risk flags this week.\n\n` +
      `_Keep it up! 🇿🇦_`
    );
  }

  const lines = [
    `🏦 *BankBook Risk Alert*`,
    ``,
    `${greeting}I've flagged ${issues.length} issue${issues.length > 1 ? "s" : ""} in your BankBook:`,
    ``,
  ];

  issues.forEach((issue, i) => {
    lines.push(
      `${issue.icon} *${i + 1}. ${issue.label}*`,
      `   ${issue.detail}`,
      `   _${issue.action}_`,
      ``,
    );
  });

  lines.push(`━━━━━━━━━━━━━━━━━━━━`, `_Reply 'Help' for guidance on any of the above._`);
  return lines.join("\n");
}

// ─── Main ──────────────────────────────────────────────────────────────────────

export async function main() {
  const usersResp = await brainGet("/users");
  if (!usersResp?.users) {
    console.error("Could not fetch users.");
    return { status: "error" };
  }

  const results: Array<{ whatsapp_id: string; issues: number; sent: boolean }> = [];

  for (const user of usersResp.users) {
    if (!user.onboarding_completed || user.net_salary === 0) continue;

    const [propsResp, insResp] = await Promise.all([
      brainGet(`/properties/${encodeURIComponent(user.whatsapp_id)}`),
      brainGet(`/insurance/${encodeURIComponent(user.whatsapp_id)}`),
    ]);

    const properties     = propsResp?.properties ?? [];
    const insuranceCount = insResp?.policies?.length ?? 0;

    const issues = detectAnomalies(user.net_salary, user.total_debt, properties, insuranceCount);
    const message = buildAlertMessage(user.full_name, issues);

    // Only send if there are issues (don't spam healthy users every week)
    const shouldSend = issues.length > 0;
    const sent = shouldSend ? await sendWhatsApp(user.whatsapp_id, message) : false;

    console.log(
      `${sent ? "✅ alert sent" : issues.length === 0 ? "✔ healthy" : "❌ failed"} — ${user.whatsapp_id} (${issues.length} issues)`
    );
    results.push({ whatsapp_id: user.whatsapp_id, issues: issues.length, sent });
  }

  const alerted  = results.filter((r) => r.sent).length;
  const healthy  = results.filter((r) => r.issues === 0).length;
  return { status: "done", total: results.length, alerted, healthy };
}
