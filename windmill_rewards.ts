/**
 * BankBook Rewards Tracker — Windmill Webhook Handler
 *
 * Handles WhatsApp messages like:
 *   "eBucks 5000"
 *   "Discovery Miles 12000 expires June 2025"
 *   "Show my rewards"
 *   "Check my points"
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

const KNOWN_PROGRAMS = [
  "eBucks", "UCount", "Discovery Miles", "Greenbacks",
  "Avios", "Voyager Miles", "Momentum Multiply",
];

/**
 * Detect rewards intent: "eBucks 5000" or "Discovery Miles 12000 expires 2025-06-30"
 */
function parseRewardsInput(text: string): Array<{ program: string; balance: number; expiry_date?: string }> | null {
  const results: Array<{ program: string; balance: number; expiry_date?: string }> = [];
  const lower = text.toLowerCase();

  for (const prog of KNOWN_PROGRAMS) {
    if (lower.includes(prog.toLowerCase())) {
      const pattern = new RegExp(`${prog.replace(/\s/g, "\\s")}[^\\d]*(r?\\s*[\\d,]+)`, "i");
      const match   = text.match(pattern);
      if (match) {
        const balance = parseFloat(match[1].replace(/[r,\s]/gi, ""));

        // Optional expiry: "expires 2025-06-30" or "exp June 2025"
        const expMatch = text.match(/(?:expir(?:es?|y)|exp)[^\d]*(\d{4}-\d{2}-\d{2}|\w+ \d{4})/i);
        let expiry_date: string | undefined;
        if (expMatch) {
          const raw = expMatch[1];
          if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) {
            expiry_date = raw;
          } else {
            // Try parsing "June 2025"
            const d = new Date(raw + " 01");
            if (!isNaN(d.getTime())) {
              expiry_date = d.toISOString().slice(0, 10);
            }
          }
        }

        results.push({ program: prog, balance, ...(expiry_date ? { expiry_date } : {}) });
      }
    }
  }

  return results.length > 0 ? results : null;
}

function isViewIntent(text: string): boolean {
  const lower = text.toLowerCase();
  return (
    lower.includes("rewards") || lower.includes("points") ||
    lower.includes("miles") || lower.includes("ebucks") ||
    lower.includes("my vault") || lower.includes("show rewards")
  ) && !parseRewardsInput(text);
}

export async function main(body: EvolutionBody) {
  if (body?.data?.key?.fromMe) return { status: "skipped" };

  const sender = body?.data?.key?.remoteJid;
  const text   = extractText(body);
  if (!sender || !text) return { status: "no_message" };

  const parsed = parseRewardsInput(text);
  const isView = isViewIntent(text);

  if (!parsed && !isView) return { status: "not_rewards_intent" };

  // --- ADD / UPDATE rewards ---
  if (parsed) {
    const res = await fetch(`${BRAIN_URL}/rewards`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ whatsapp_id: sender, rewards: parsed }),
    });

    if (!res.ok) {
      await sendWhatsApp(sender, `🏦 *BankBook*\n\nCouldn't save your rewards. Please try again.`);
      return { status: "save_failed" };
    }

    const data = await res.json();
    await sendWhatsApp(sender, data.whatsapp_message);
    return { status: "rewards_saved", count: parsed.length };
  }

  // --- VIEW rewards vault ---
  const res = await fetch(`${BRAIN_URL}/rewards/${encodeURIComponent(sender)}`);
  if (!res.ok) {
    await sendWhatsApp(
      sender,
      `🏦 *BankBook Rewards Vault*\n\nNo rewards on file yet.\n\nAdd one: _eBucks 5000_ or _Discovery Miles 12000_`
    );
    return { status: "no_rewards" };
  }

  const data = await res.json();
  await sendWhatsApp(sender, data.whatsapp_message);
  return { status: "rewards_shown" };
}
