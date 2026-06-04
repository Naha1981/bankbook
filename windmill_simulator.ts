/**
 * BankBook Pre-Approval Simulator — Windmill Webhook Handler
 *
 * Triggered by: Evolution API webhook (same as windmill_webhook.ts)
 * Handles messages like:
 *   "What if I pay off my car loan of R5000?"
 *   "If I clear my personal loan, how much house can I afford?"
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
  event: string;
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

/**
 * Parse debt items from natural language, e.g.:
 *   "car loan 5000 and personal loan 3000"
 *   "what if I pay off my R2500 clothing account"
 */
function parseDebts(text: string): Array<{ label: string; monthly_amount: number }> {
  const debts: Array<{ label: string; monthly_amount: number }> = [];
  const lower = text.toLowerCase();

  const debtTypes = [
    "car loan", "vehicle finance", "personal loan", "credit card",
    "clothing account", "store account", "student loan", "furniture account",
    "micro loan", "payday loan", "overdraft",
  ];

  for (const dtype of debtTypes) {
    if (lower.includes(dtype)) {
      // Look for an amount near the debt type mention
      const pattern = new RegExp(`${dtype}[^\\d]*(r?\\s*[\\d,]+)`, "i");
      const match = text.match(pattern);
      if (match) {
        const amount = parseFloat(match[1].replace(/[r,\s]/gi, ""));
        if (amount > 0) {
          debts.push({ label: dtype.replace(/\b\w/g, (c) => c.toUpperCase()), monthly_amount: amount });
        }
      }
    }
  }

  // Fallback: generic "R5000" or "5000" mentioned
  if (debts.length === 0) {
    const amountMatch = text.match(/r?\s*([\d,]+)/i);
    if (amountMatch) {
      const amount = parseFloat(amountMatch[1].replace(/,/g, ""));
      if (amount > 0) {
        debts.push({ label: "Current debt", monthly_amount: amount });
      }
    }
  }

  return debts;
}

export async function main(body: EvolutionBody) {
  if (body?.data?.key?.fromMe) return { status: "skipped" };

  const sender = body?.data?.key?.remoteJid;
  const text   = extractText(body);
  if (!sender || !text) return { status: "no_message" };

  const lower = text.toLowerCase();
  const isSimulator =
    lower.includes("what if") ||
    lower.includes("if i pay") ||
    lower.includes("if i clear") ||
    lower.includes("pay off") ||
    lower.includes("simulator") ||
    lower.includes("scenario");

  if (!isSimulator) return { status: "not_simulator_intent" };

  const debts = parseDebts(text);

  if (debts.length === 0) {
    await sendWhatsApp(
      sender,
      `🏦 *BankBook Simulator*\n\n` +
      `I couldn't pick up which debt you want to clear. Try:\n\n` +
      `_"What if I pay off my car loan of R5,000?"_\n` +
      `_"If I clear my personal loan of R3,500, how much house can I afford?"_`
    );
    return { status: "parse_failed" };
  }

  // Call the Brain's simulator endpoint
  const res = await fetch(`${BRAIN_URL}/pre-approval-simulator`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ whatsapp_id: sender, debts_to_simulate: debts }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    if (err?.detail?.includes("not found") || res.status === 404) {
      await sendWhatsApp(
        sender,
        `🏦 *BankBook*\n\nI need your salary first before running simulations.\n\nReply: _I earn [take-home pay]_`
      );
      return { status: "no_profile" };
    }
    await sendWhatsApp(sender, `🏦 *BankBook*\n\nSomething went wrong. Please try again shortly.`);
    return { status: "brain_error" };
  }

  const data = await res.json();
  await sendWhatsApp(sender, data.whatsapp_message);
  return { status: "simulation_sent", scenarios: data.scenarios?.length ?? 0 };
}
