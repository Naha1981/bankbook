/**
 * BankBook Safe-to-Spend — Windmill Webhook Handler
 *
 * Handles WhatsApp messages like:
 *   "Balance 12000"            → update manual balance
 *   "Add debit Netflix 199 on the 25th"
 *   "Remove debit Netflix"
 *   "Safe to spend?" / "How much can I spend?"
 *   "Connect my bank"          → send Stitch Link URL
 *
 * Required Windmill Variables:
 *   - BANKBOOK_BRAIN_URL
 *   - EVOLUTION_API_URL
 *   - EVOLUTION_API_KEY
 *   - EVOLUTION_INSTANCE
 *   - STITCH_REDIRECT_URI  (your backend URL for OAuth callback)
 */

const BRAIN_URL      = Deno.env.get("BANKBOOK_BRAIN_URL") ?? "";
const EVO_URL        = Deno.env.get("EVOLUTION_API_URL") ?? "";
const EVO_KEY        = Deno.env.get("EVOLUTION_API_KEY") ?? "";
const EVO_INSTANCE   = Deno.env.get("EVOLUTION_INSTANCE") ?? "";
const REDIRECT_URI   = Deno.env.get("STITCH_REDIRECT_URI") ?? "";

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

// ─── Intent Detection ──────────────────────────────────────────────────────────

type Intent =
  | "update_balance"
  | "add_debit"
  | "remove_debit"
  | "view_safe_to_spend"
  | "connect_bank"
  | "none";

function detectIntent(text: string): Intent {
  const lower = text.toLowerCase();

  if (lower.match(/^balance\s+r?[\d,]+/) || lower.match(/my balance is r?[\d,]+/)) return "update_balance";
  if (lower.includes("add debit") || lower.includes("add order") || lower.match(/debit .+ r?[\d,]+/)) return "add_debit";
  if (lower.includes("remove debit") || lower.includes("delete debit") || lower.includes("cancel debit")) return "remove_debit";
  if (lower.includes("connect") && (lower.includes("bank") || lower.includes("stitch"))) return "connect_bank";
  if (
    lower.includes("safe to spend") || lower.includes("how much can i spend") ||
    lower.includes("available") || lower.includes("spending money") ||
    lower.match(/^balance\s*$/)
  ) return "view_safe_to_spend";

  return "none";
}

function parseBalance(text: string): number {
  const match = text.match(/r?\s*([\d,]+)/i);
  return match ? parseFloat(match[1].replace(/,/g, "")) : 0;
}

function parseDebitOrder(text: string): { description: string; amount: number; due_day: number } | null {
  // "Add debit Netflix 199 on the 25th"
  // "Debit Discovery Health 3500 day 1"
  const amountMatch  = text.match(/r?\s*([\d,]+)/i);
  const dayMatch     = text.match(/(?:on the|day|due)\s+(\d{1,2})(?:st|nd|rd|th)?/i);
  const descMatch    = text.match(/(?:debit|order)\s+([a-z][a-z\s]+?)(?:\s+r?[\d,])/i);

  if (!amountMatch || !descMatch) return null;

  const amount      = parseFloat(amountMatch[1].replace(/,/g, ""));
  const description = descMatch[1].trim();
  const due_day     = dayMatch ? parseInt(dayMatch[1]) : 1;

  return { description, amount, due_day };
}

function parseDebitName(text: string): string {
  const match = text.match(/(?:remove|delete|cancel)\s+debit\s+(.+)/i);
  return match ? match[1].trim() : "";
}

// ─── Main ──────────────────────────────────────────────────────────────────────

export async function main(body: EvolutionBody) {
  if (body?.data?.key?.fromMe) return { status: "skipped" };

  const sender = body?.data?.key?.remoteJid;
  const text   = extractText(body);
  if (!sender || !text) return { status: "no_message" };

  const intent = detectIntent(text);
  if (intent === "none") return { status: "not_sts_intent" };

  switch (intent) {

    case "update_balance": {
      const balance = parseBalance(text);
      if (balance === 0) {
        await sendWhatsApp(sender, `🏦 *BankBook*\n\nCouldn't read that balance. Try: _Balance 12500_`);
        return { status: "parse_error" };
      }
      const { ok, data } = await brainPost("/safe-to-spend/balance", { whatsapp_id: sender, balance });
      if (!ok) {
        await sendWhatsApp(sender, `🏦 *BankBook*\n\nCouldn't save balance. Please try again.`);
        return { status: "save_failed" };
      }
      await sendWhatsApp(sender, data.whatsapp_message);
      return { status: "balance_updated", balance };
    }

    case "add_debit": {
      const debit = parseDebitOrder(text);
      if (!debit) {
        await sendWhatsApp(
          sender,
          `🏦 *BankBook*\n\nCouldn't parse that debit order. Try:\n_Add debit Netflix 199 on the 25th_`
        );
        return { status: "parse_error" };
      }
      const { ok, data } = await brainPost("/safe-to-spend/debit", {
        whatsapp_id: sender,
        ...debit,
      });
      if (!ok) {
        await sendWhatsApp(sender, `🏦 *BankBook*\n\nCouldn't save debit order. Please try again.`);
        return { status: "save_failed" };
      }
      await sendWhatsApp(sender, data.whatsapp_message);
      return { status: "debit_added" };
    }

    case "remove_debit": {
      const name = parseDebitName(text);
      if (!name) {
        await sendWhatsApp(sender, `🏦 *BankBook*\n\nWhich debit should I remove? Try: _Remove debit Netflix_`);
        return { status: "parse_error" };
      }
      const { ok, data } = await brainPost("/safe-to-spend/debit/remove", {
        whatsapp_id: sender,
        description: name,
      });
      await sendWhatsApp(sender, ok ? data.whatsapp_message : `🏦 *BankBook*\n\nCouldn't find a debit named "${name}".`);
      return { status: ok ? "debit_removed" : "not_found" };
    }

    case "connect_bank": {
      const { ok, data } = await brainGet(`/safe-to-spend/stitch-link?whatsapp_id=${encodeURIComponent(sender)}&redirect_uri=${encodeURIComponent(REDIRECT_URI)}`);
      if (!ok || !data?.link_url) {
        await sendWhatsApp(
          sender,
          `🏦 *BankBook*\n\nBank connection via Stitch is coming soon.\n\nFor now, update your balance manually:\n_Balance 12500_`
        );
        return { status: "stitch_unavailable" };
      }
      await sendWhatsApp(
        sender,
        `🏦 *BankBook — Connect Your Bank*\n\n` +
        `Tap the link below to securely connect your FNB, Standard Bank, Absa, Nedbank, Capitec, or Discovery Bank account:\n\n` +
        `🔗 ${data.link_url}\n\n` +
        `_Your login details are never shared with BankBook — Stitch uses bank-grade encryption._`
      );
      return { status: "link_sent" };
    }

    case "view_safe_to_spend": {
      const { ok, data } = await brainGet(`/safe-to-spend/${encodeURIComponent(sender)}`);
      if (!ok || !data?.whatsapp_message) {
        await sendWhatsApp(
          sender,
          `🏦 *BankBook Safe-to-Spend*\n\n` +
          `No balance on file yet. Update it with:\n_Balance 12500_\n\n` +
          `Then add your debit orders:\n_Add debit Discovery Health 3500 on the 1st_`
        );
        return { status: "no_balance" };
      }
      await sendWhatsApp(sender, data.whatsapp_message);
      return { status: "sts_shown" };
    }
  }
}
