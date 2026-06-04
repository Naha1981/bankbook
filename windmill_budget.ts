/**
 * BankBook Budget Coach — Windmill Webhook Handler
 *
 * Handles WhatsApp messages like:
 *   "Spent R800 at Woolworths"
 *   "R200 KFC"
 *   "Paid R1500 Netflix"
 *   "Budget" / "Show my spending"
 *   "Budget this month"
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
  return { ok: res.ok, data: await res.json().catch(() => ({})) };
}

async function brainGet(path: string) {
  const res = await fetch(`${BRAIN_URL}${path}`);
  return { ok: res.ok, data: await res.json().catch(() => ({})) };
}

// ─── Intent Detection ──────────────────────────────────────────────────────────

type Intent = "log_spend" | "view_budget" | "none";

function detectIntent(text: string): Intent {
  const lower = text.toLowerCase();

  // View intent
  if (
    lower === "budget" || lower.includes("show budget") ||
    lower.includes("my spending") || lower.includes("how much did i spend") ||
    lower.includes("budget this month") || lower.includes("spending breakdown")
  ) return "view_budget";

  // Log intent — must mention an amount
  if (
    (lower.includes("spent") || lower.includes("paid") ||
     lower.includes("bought") || lower.match(/^r?\s*\d/)) &&
    text.match(/r?\s*[\d,]+/i)
  ) return "log_spend";

  return "none";
}

export async function main(body: EvolutionBody) {
  if (body?.data?.key?.fromMe) return { status: "skipped" };

  const sender = body?.data?.key?.remoteJid;
  const text   = extractText(body);
  if (!sender || !text) return { status: "no_message" };

  const intent = detectIntent(text);
  if (intent === "none") return { status: "not_budget_intent" };

  if (intent === "log_spend") {
    const { ok, data } = await brainPost("/budget/log", {
      whatsapp_id: sender,
      text,
    });

    if (!ok || data?.status === "parse_failed") {
      await sendWhatsApp(
        sender,
        `🏦 *BankBook Budget Coach*\n\n` +
        `Couldn't read that. Try:\n` +
        `_Spent R800 at Woolworths_\n` +
        `_R200 KFC_\n` +
        `_Paid R1500 for Netflix_`
      );
      return { status: "parse_failed" };
    }

    await sendWhatsApp(sender, data.whatsapp_message);
    return { status: "spend_logged", category: data.category, amount: data.amount };
  }

  if (intent === "view_budget") {
    const { ok, data } = await brainGet(`/budget/summary/${encodeURIComponent(sender)}`);

    if (!ok || !data?.whatsapp_message) {
      await sendWhatsApp(
        sender,
        `🏦 *BankBook Budget Coach*\n\n` +
        `No spending logged yet this month.\n\n` +
        `Start tracking: _Spent R800 at Woolworths_`
      );
      return { status: "no_data" };
    }

    await sendWhatsApp(sender, data.whatsapp_message);
    return { status: "budget_shown" };
  }
}
