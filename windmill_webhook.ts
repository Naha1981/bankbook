/**
 * BankBook AI OS — Windmill Webhook Handler
 *
 * Trigger: HTTP Webhook (from Evolution API)
 * Purpose: Routes incoming WhatsApp messages to the correct BankBook Brain endpoint,
 *          then sends the AI response back to the user via Evolution API.
 *
 * Required Windmill Variables (set in your Windmill workspace):
 *   - BANKBOOK_BRAIN_URL   e.g. https://bankbook-brain.onrender.com
 *   - EVOLUTION_API_URL    e.g. https://bankbook-whatsapp.onrender.com
 *   - EVOLUTION_API_KEY    Your AUTH_API_KEY from Evolution API
 *   - EVOLUTION_INSTANCE   Your Evolution API instance name
 */

type EvolutionWebhookBody = {
  event: string;
  data: {
    key: { remoteJid: string; fromMe: boolean };
    message?: { conversation?: string; extendedTextMessage?: { text: string } };
  };
};

// ─── Windmill Resource Variables ───────────────────────────────────────────────
const BRAIN_URL = Deno.env.get("BANKBOOK_BRAIN_URL") ?? "";
const EVO_URL = Deno.env.get("EVOLUTION_API_URL") ?? "";
const EVO_KEY = Deno.env.get("EVOLUTION_API_KEY") ?? "";
const EVO_INSTANCE = Deno.env.get("EVOLUTION_INSTANCE") ?? "";

// ─── Helpers ───────────────────────────────────────────────────────────────────

function extractText(body: EvolutionWebhookBody): string {
  return (
    body?.data?.message?.conversation ??
    body?.data?.message?.extendedTextMessage?.text ??
    ""
  ).trim();
}

async function sendWhatsApp(to: string, text: string): Promise<void> {
  await fetch(`${EVO_URL}/message/sendText/${EVO_INSTANCE}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      apikey: EVO_KEY,
    },
    body: JSON.stringify({ number: to, text }),
  });
}

async function callBrain(path: string, payload: Record<string, unknown>) {
  const res = await fetch(`${BRAIN_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}

// ─── Intent Detection ──────────────────────────────────────────────────────────

type Intent =
  | "set_salary"
  | "set_debt"
  | "affordability"
  | "add_property"
  | "insurance"
  | "help"
  | "unknown";

function detectIntent(text: string): { intent: Intent; value?: number; text?: string } {
  const lower = text.toLowerCase();

  // Salary: "I earn 45000" / "my salary is 45000" / "I take home 45000"
  const salaryMatch = lower.match(/(?:i earn|salary is|take home|net pay is|i make)\s+r?\s*([\d,]+)/);
  if (salaryMatch) {
    return { intent: "set_salary", value: parseFloat(salaryMatch[1].replace(/,/g, "")) };
  }

  // Quick salary input: just "45000" alone
  const pureNumber = lower.match(/^r?\s*([\d,]+)\s*$/);
  if (pureNumber) {
    return { intent: "set_salary", value: parseFloat(pureNumber[1].replace(/,/g, "")) };
  }

  // Debt: "my debt is 5000" / "I owe 5000"
  const debtMatch = lower.match(/(?:my debt|i owe|total debt)\s+(?:is\s+)?r?\s*([\d,]+)/);
  if (debtMatch) {
    return { intent: "set_debt", value: parseFloat(debtMatch[1].replace(/,/g, "")) };
  }

  // Affordability: "can I afford a 1.8m house" / "how much is a 1500000 bond"
  const affordMatch = lower.match(
    /(?:afford|bond|house|property|home)\s+(?:for\s+)?r?\s*([\d,.]+)\s*(?:m(?:illion)?|k)?/
  );
  if (affordMatch || lower.includes("how much can i afford") || lower.includes("what can i afford")) {
    let price = 0;
    if (affordMatch) {
      const raw = affordMatch[1].replace(/,/g, "");
      price = lower.includes("m") ? parseFloat(raw) * 1_000_000 : parseFloat(raw);
    }
    return { intent: "affordability", value: price };
  }

  // Help / menu
  if (lower.includes("help") || lower.includes("menu") || lower === "hi" || lower === "hello") {
    return { intent: "help" };
  }

  return { intent: "unknown" };
}

// ─── Response Formatters ───────────────────────────────────────────────────────

function formatAffordability(data: Record<string, unknown>, price: number): string {
  if (data.status === "missing_data") {
    return (
      `🏦 *BankBook*\n\nI don't have your salary on file yet.\n\n` +
      `Reply with: *I earn [your monthly take-home pay]*\n` +
      `Example: _I earn 45000_`
    );
  }

  const repayment = (data.repayment as number).toLocaleString("en-ZA", { style: "currency", currency: "ZAR", maximumFractionDigits: 0 });
  const maxPrice = ((data.max_affordable_price as number) ?? 0).toLocaleString("en-ZA", { style: "currency", currency: "ZAR", maximumFractionDigits: 0 });
  const affordable = data.is_affordable as boolean;

  if (affordable) {
    return (
      `🏦 *BankBook Property Analysis*\n\n` +
      `✅ *R${(price).toLocaleString()} is affordable.*\n\n` +
      `📋 Monthly bond repayment: *${repayment}*\n` +
      `📈 Rate: ${data.annual_rate_pct}% (SA Prime) over ${data.term_years} years\n\n` +
      `I've updated your BankBook Property Page. Want me to save this search?`
    );
  } else {
    return (
      `🏦 *BankBook Property Analysis*\n\n` +
      `⚠️ *R${(price).toLocaleString()} is over your limit.*\n\n` +
      `📋 Required repayment: *${repayment}/month*\n` +
      `❌ Shortfall: R${(data.shortfall as number).toLocaleString()} /month\n\n` +
      `✅ *Your max approved price is ${maxPrice}*\n\n` +
      `Want to see properties in that range, or get a plan to boost your affordability?`
    );
  }
}

// ─── Main Handler ──────────────────────────────────────────────────────────────

export async function main(body: EvolutionWebhookBody) {
  // Only process incoming messages, not outgoing
  if (body?.data?.key?.fromMe) return { status: "skipped_outgoing" };

  const sender = body?.data?.key?.remoteJid;
  const text = extractText(body);

  if (!sender || !text) return { status: "no_message" };

  const { intent, value } = detectIntent(text);

  switch (intent) {

    case "help": {
      await sendWhatsApp(
        sender,
        `🏦 *Welcome to BankBook AI*\n\n` +
        `Your personal AI Financial Operating System. Here's what I can do:\n\n` +
        `🏠 *Bond Affordability* — "Can I afford a R1.5M house?"\n` +
        `💰 *Set Salary* — "I earn 45000"\n` +
        `📊 *Full Analysis* — Just tell me the property price\n\n` +
        `_BankBook — Your whole financial life, finally in one book._`
      );
      return { status: "help_sent" };
    }

    case "set_salary": {
      if (!value) {
        await sendWhatsApp(sender, `🏦 *BankBook*\n\nSorry, I couldn't read that salary. Try: _I earn 45000_`);
        return { status: "parse_error" };
      }
      await callBrain("/profile", {
        whatsapp_id: sender,
        net_salary: value,
        total_debt: 0,
      });
      const formatted = value.toLocaleString("en-ZA", { style: "currency", currency: "ZAR", maximumFractionDigits: 0 });
      await sendWhatsApp(
        sender,
        `🏦 *BankBook Updated*\n\n` +
        `✅ Salary saved: *${formatted}/month*\n\n` +
        `Now ask me: _"Can I afford a R1.5M house?"_`
      );
      return { status: "salary_saved", salary: value };
    }

    case "affordability": {
      if (!value) {
        await sendWhatsApp(
          sender,
          `🏦 *BankBook*\n\nWhich property price should I analyse?\n\nExample: _Can I afford a R1.8M house?_`
        );
        return { status: "needs_price" };
      }
      const data = await callBrain("/calculate-affordability", {
        whatsapp_id: sender,
        property_price: value,
      });
      await sendWhatsApp(sender, formatAffordability(data, value));
      return { status: "affordability_sent", data };
    }

    default: {
      await sendWhatsApp(
        sender,
        `🏦 *BankBook*\n\nI didn't quite catch that. Try:\n\n` +
        `• _I earn 45000_ — to set your salary\n` +
        `• _Can I afford a R1.5M house?_ — for bond analysis\n` +
        `• _Help_ — to see all commands`
      );
      return { status: "unknown_intent" };
    }
  }
}
