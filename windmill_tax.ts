/**
 * BankBook SARS Tax Envelope — Windmill Webhook Handler
 *
 * Handles WhatsApp messages like:
 *   "I'm freelance, I earn 30000 a month"
 *   "I have rental income of R15000"
 *   "What's my tax?"
 *   "Show my tax envelope"
 *
 * Also handles the deadline reminder scheduler (cron: 0 8 1 7 * and 0 8 1 1 *)
 * = 1st July (30 days before 31 Aug) and 1st January (30 days before 31 Jan)
 *
 * Required Windmill Variables:
 *   - BANKBOOK_BRAIN_URL
 *   - EVOLUTION_API_URL
 *   - EVOLUTION_API_KEY
 *   - EVOLUTION_INSTANCE
 */

const BRAIN_URL    = Deno.env.get("BANKBOOK_BRAIN_URL") ?? "";
const EVO_URL      = Deno.env.get("EVOLUTION_API_URL") ?? "";
const EVO_KEY      = Deno.env.get("EVOLUTION_API_KEY") ?? "";
const EVO_INSTANCE = Deno.env.get("EVOLUTION_INSTANCE") ?? "";

type EvolutionBody = {
  data: {
    key: { remoteJid: string; fromMe: boolean };
    message?: { conversation?: string; extendedTextMessage?: { text: string } };
  };
};

function extractText(body: EvolutionBody): string {
  return (
    body?.data?.message?.conversation ??
    body?.data?.message?.extendedTextMessage?.text ??
    ""
  ).trim();
}

async function sendWhatsApp(to: string, text: string) {
  await fetch(`${EVO_URL}/message/sendText/${EVO_INSTANCE}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", apikey: EVO_KEY },
    body: JSON.stringify({ number: to, text }),
  });
}

async function brainPost(path: string, payload: Record<string, unknown>) {
  const res = await fetch(`${BRAIN_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return { ok: res.ok, status: res.status, data: await res.json().catch(() => ({})) };
}

async function brainGet(path: string) {
  const res = await fetch(`${BRAIN_URL}${path}`);
  return { ok: res.ok, data: await res.json().catch(() => ({})) };
}

// ─── Intent & Parsing ──────────────────────────────────────────────────────────

type TaxIntent = "calculate" | "view" | "none";

function detectTaxIntent(text: string): TaxIntent {
  const lower = text.toLowerCase();
  if (
    lower.includes("tax") || lower.includes("sars") ||
    lower.includes("provisional") || lower.includes("freelance") ||
    lower.includes("rental income") || lower.includes("side hustle") ||
    lower.includes("self employed") || lower.includes("sole trader")
  ) {
    if (
      lower.includes("show") || lower.includes("view") ||
      lower.includes("my tax") || lower.includes("check tax")
    ) return "view";
    return "calculate";
  }
  return "none";
}

function parseMonthlyAmount(text: string, keywords: string[]): number {
  for (const kw of keywords) {
    const pattern = new RegExp(`${kw}[^\\d]*(r?\\s*[\\d,]+)`, "i");
    const match   = text.match(pattern);
    if (match) return parseFloat(match[1].replace(/[r,\s]/gi, ""));
  }
  // Generic number fallback
  const m = text.match(/r?\s*([\d,]+)/i);
  return m ? parseFloat(m[1].replace(/,/g, "")) : 0;
}

function detectIncomeType(text: string): "freelance" | "salary_plus_rental" | "rental_only" {
  const lower = text.toLowerCase();
  if (lower.includes("rental only") || lower.includes("property investor")) return "rental_only";
  if (lower.includes("rental") || lower.includes("property")) return "salary_plus_rental";
  return "freelance";
}

// ─── Main Webhook Handler ──────────────────────────────────────────────────────

export async function main(body: EvolutionBody) {
  if (body?.data?.key?.fromMe) return { status: "skipped" };

  const sender = body?.data?.key?.remoteJid;
  const text   = extractText(body);
  if (!sender || !text) return { status: "no_message" };

  const intent = detectTaxIntent(text);
  if (intent === "none") return { status: "not_tax_intent" };

  // VIEW existing tax envelope
  if (intent === "view") {
    const { ok, data } = await brainGet(`/tax-envelope/${encodeURIComponent(sender)}`);
    if (!ok || !data?.whatsapp_message) {
      await sendWhatsApp(
        sender,
        `🏦 *BankBook Tax Envelope*\n\nNo tax profile saved yet.\n\n` +
        `Tell me your situation:\n` +
        `• _I'm freelance, I earn R30,000/month_\n` +
        `• _I have rental income of R15,000/month_`
      );
      return { status: "no_tax_profile" };
    }
    await sendWhatsApp(sender, data.whatsapp_message);
    return { status: "tax_shown" };
  }

  // CALCULATE — parse income figures from the message
  const income_type  = detectIncomeType(text);
  const monthly_income = parseMonthlyAmount(text, ["earn", "income", "make", "salary", "turnover"]);
  const monthly_rental = parseMonthlyAmount(text, ["rental", "rent income", "property income"]);

  if (monthly_income === 0 && monthly_rental === 0) {
    await sendWhatsApp(
      sender,
      `🏦 *BankBook SARS Tax Envelope*\n\n` +
      `I need your income to calculate your tax.\n\n` +
      `Try:\n` +
      `• _I'm freelance and I earn R25,000/month_\n` +
      `• _I have rental income of R12,000/month_\n` +
      `• _I earn R40,000 salary plus R10,000 rental_`
    );
    return { status: "missing_income" };
  }

  const payload = {
    whatsapp_id:      sender,
    annual_income:    monthly_income * 12,
    rental_income:    monthly_rental * 12,
    income_type,
    annual_expenses:  0,
    rental_expenses:  0,
    age:              35,
    medical_aid_dependants: 0,
  };

  const { ok, data } = await brainPost("/tax-envelope", payload);
  if (!ok) {
    await sendWhatsApp(sender, `🏦 *BankBook*\n\nCouldn't calculate your tax. Please try again.`);
    return { status: "calc_failed" };
  }

  await sendWhatsApp(sender, data.whatsapp_message);
  return { status: "tax_calculated", annual_tax: data.annual_tax_payable };
}

// ─── Deadline Reminder (scheduled separately in Windmill) ──────────────────────
// Cron 1: "0 8 1 7 *"  = 1 July  → 30-day warning before 31 August deadline
// Cron 2: "0 8 1 1 *"  = 1 Jan   → 30-day warning before 31 January deadline

export async function sendDeadlineReminders() {
  const { data } = await brainGet("/users");
  if (!data?.users) return { status: "no_users" };

  const now   = new Date();
  const month = now.getMonth() + 1;  // 1-indexed
  const isAug = month === 7;          // July = warn about August
  const isFeb = month === 1;          // January = warn about February

  if (!isAug && !isFeb) return { status: "not_reminder_month" };

  const deadline = isAug ? "31 August" : "28 February";
  let sent = 0;

  for (const user of data.users) {
    if (!user.onboarding_completed) continue;

    const { ok, data: taxData } = await brainGet(`/tax-envelope/${encodeURIComponent(user.whatsapp_id)}`);
    if (!ok || !taxData?.provisional_period_1) continue;

    const amount = isAug ? taxData.provisional_period_1 : taxData.provisional_period_2;
    const msg = (
      `🏦 *BankBook SARS Reminder*\n\n` +
      `⏰ Your provisional tax payment of *R${amount.toLocaleString("en-ZA")}* ` +
      `is due by *${deadline}*.\n\n` +
      `Make sure your Tax Envelope account has enough. Reply 'Tax' to review your full breakdown.`
    );

    const res = await fetch(`${EVO_URL}/message/sendText/${EVO_INSTANCE}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", apikey: EVO_KEY },
      body: JSON.stringify({ number: user.whatsapp_id, text: msg }),
    });
    if (res.ok) sent++;
  }

  return { status: "reminders_sent", count: sent };
}
