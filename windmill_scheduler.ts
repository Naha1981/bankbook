/**
 * BankBook Morning Briefing — Windmill Scheduled Job
 *
 * Schedule: Every Monday at 08:00 SAST (06:00 UTC)
 * Windmill cron: 0 6 * * 1
 *
 * Purpose: Fetches every BankBook user and sends them a weekly WhatsApp
 *          financial summary via Evolution API.
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

// ─── Helpers ───────────────────────────────────────────────────────────────────

async function brainGet(path: string) {
  const res = await fetch(`${BRAIN_URL}${path}`);
  if (!res.ok) return null;
  return res.json();
}

async function sendWhatsApp(to: string, text: string): Promise<boolean> {
  const res = await fetch(`${EVO_URL}/message/sendText/${EVO_INSTANCE}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      apikey: EVO_KEY,
    },
    body: JSON.stringify({ number: to, text }),
  });
  return res.ok;
}

function formatZAR(n: number): string {
  return `R${n.toLocaleString("en-ZA", { maximumFractionDigits: 0 })}`;
}

// ─── Briefing Builder ──────────────────────────────────────────────────────────

function buildBriefing(
  name: string | null,
  salary: number,
  debt: number,
  properties: Array<{ estimated_value: number; bond_balance: number; rental_income: number }>,
  insuranceCount: number
): string {
  const now       = new Date();
  const dateStr   = now.toLocaleDateString("en-ZA", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  const firstName = name ? name.split(" ")[0] : null;

  const safeToSpend = Math.max(0, salary - debt - salary * 0.05);
  const totalValue  = properties.reduce((s, p) => s + p.estimated_value, 0);
  const totalBond   = properties.reduce((s, p) => s + p.bond_balance, 0);
  const totalEquity = totalValue - totalBond;
  const totalRental = properties.reduce((s, p) => s + p.rental_income, 0);

  const lines: string[] = [
    `🏦 *BankBook Weekly Briefing*`,
    `_${dateStr}_`,
    ``,
    `Good morning${firstName ? ", " + firstName : ""}! 👋`,
    `Here's your financial snapshot for this week:`,
    ``,
    `━━━━━━━━━━━━━━━━━━━━`,
    `💰 *CASHFLOW*`,
    `  Take-home salary:  *${formatZAR(salary)}*`,
    `  Committed debt:    *${formatZAR(debt)}*`,
    `  ✅ Safe-to-Spend:  *${formatZAR(safeToSpend)}*`,
    ``,
  ];

  if (properties.length > 0) {
    lines.push(
      `━━━━━━━━━━━━━━━━━━━━`,
      `🏡 *PROPERTY*`,
      `  Properties:        *${properties.length}*`,
      `  Portfolio value:   *${formatZAR(totalValue)}*`,
      `  Outstanding bonds: *${formatZAR(totalBond)}*`,
      `  📈 Net equity:     *${formatZAR(totalEquity)}*`,
    );
    if (totalRental > 0) lines.push(`  🏘 Rental income:  *${formatZAR(totalRental)}/mo*`);
    lines.push(``);
  }

  if (insuranceCount > 0) {
    lines.push(
      `━━━━━━━━━━━━━━━━━━━━`,
      `🛡 *INSURANCE*  ${insuranceCount} polic${insuranceCount === 1 ? "y" : "ies"} on file`,
      ``,
    );
  }

  lines.push(
    `━━━━━━━━━━━━━━━━━━━━`,
    `_Need a bond calculation or property check?_`,
    `_Just ask me anytime. Have a great week! 🇿🇦_`,
  );

  return lines.join("\n");
}

// ─── Main ──────────────────────────────────────────────────────────────────────

export async function main() {
  // Fetch all users from BankBook Brain
  const usersResp = await brainGet("/users");
  if (!usersResp || !Array.isArray(usersResp.users)) {
    console.error("Could not fetch users from BankBook Brain.");
    return { status: "error", message: "Failed to fetch users" };
  }

  const users: Array<{
    whatsapp_id: string;
    full_name: string | null;
    net_salary: number;
    total_debt: number;
    onboarding_completed: boolean;
  }> = usersResp.users;

  const results: Array<{ whatsapp_id: string; sent: boolean }> = [];

  for (const user of users) {
    // Only send to users who completed onboarding
    if (!user.onboarding_completed || user.net_salary === 0) continue;

    const [propertiesResp, insuranceResp] = await Promise.all([
      brainGet(`/properties/${encodeURIComponent(user.whatsapp_id)}`),
      brainGet(`/insurance/${encodeURIComponent(user.whatsapp_id)}`),
    ]);

    const properties = propertiesResp?.properties ?? [];
    const insuranceCount = insuranceResp?.policies?.length ?? 0;

    const message = buildBriefing(
      user.full_name,
      user.net_salary,
      user.total_debt,
      properties,
      insuranceCount,
    );

    const sent = await sendWhatsApp(user.whatsapp_id, message);
    console.log(`${sent ? "✅" : "❌"} Briefing sent to ${user.whatsapp_id}`);
    results.push({ whatsapp_id: user.whatsapp_id, sent });
  }

  const succeeded = results.filter((r) => r.sent).length;
  return {
    status: "done",
    total: results.length,
    succeeded,
    failed: results.length - succeeded,
  };
}
