// Agent-ready over iMessage (Photon 2.0). A business owner texts their website and runs the whole test by text:
// meet the customers, approve or correct them, get the result, teach them what real customers do, test again.
//
//   PHOTON_MODE=terminal  → talk to it in this terminal (no Photon account needed)
//   otherwise             → iMessage via Photon 2.0: PHOTON_API_KEY, PHOTON_PROJECT_ID, PHOTON_AGENT_HANDLE
//   AGENT_READY_API       → our backend (default http://127.0.0.1:4620)
//   PUBLIC_URL            → where people can watch the map (default http://localhost:4621)
import "dotenv/config";
import { config } from "dotenv";
import readline from "node:readline";

config({ path: new URL("../.env", import.meta.url).pathname });

const API = process.env.AGENT_READY_API ?? "http://127.0.0.1:4620";
const PUBLIC = (process.env.PUBLIC_URL ?? "http://localhost:4621").replace(/\/$/, "");
const TERMINAL = process.env.PHOTON_MODE === "terminal" || !process.env.PHOTON_API_KEY;

type Stage = "idle" | "casting" | "approval" | "running" | "done";
interface Chat { sim?: string; stage: Stage; seen: string; send: (text: string) => Promise<void> }
const chats = new Map<string, Chat>();

// ---------- our API ----------
async function api(path: string, body?: unknown) {
  const r = await fetch(`${API}${path}`, body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}
const host = (u: string) => u.replace(/^https?:\/\//, "").replace(/\/.*$/, "");
// Find a website anywhere in the text: "can you test melomed.io?" → "melomed.io"
const findSite = (t: string) => t.match(/\b(https?:\/\/)?([a-z0-9-]+\.)+(com|io|co|org|net|ai|app|shop|store|biz|us|dev|xyz|me|info|cafe|restaurant)(\/[^\s]*)?\b/i)?.[0]?.replace(/[.,!?)]+$/, "");

function castText(sim: any) {
  const people = sim.personas.filter((p: any) => p.kind !== "agent");
  const bots = sim.personas.filter((p: any) => p.kind === "agent");
  const lines = people.map((p: any, i: number) => `${i + 1}. ${p.name}, ${p.age}, ${p.occupation} (${p.archetype}${p.model ? `, played by ${p.model}` : ""})`);
  return `Meet your ${people.length} customers at ${sim.input.name || host(sim.input.url)}:\n${lines.join("\n")}` + (bots.length ? `\n\nPlus ${bots.length} AI shopping agents (${bots.map((b: any) => b.model).join(", ")}) on a user's errand: ${bots[0].goal.replace(/^Your user asked: /, "")}` : "") + `\n\nReply "ok" to let them in, or tell me what's off (e.g. "my customers are older").`;
}

function bought(sim: any, pid: string) {
  const d = sim.decisions[pid];
  const carted = (sim.live[pid] ?? []).some((x: any) => x.cart);
  return carted || (d && (d.decision === "buy" || d.decision === "would recommend"));
}

function resultText(sim: any) {
  const people = sim.personas.filter((p: any) => p.kind !== "agent" && sim.decisions[p.id]);
  const bots = sim.personas.filter((p: any) => p.kind === "agent" && sim.decisions[p.id]);
  const n = people.filter((p: any) => bought(sim, p.id)).length;
  const name = sim.input.name || host(sim.input.url);
  const out = [`${n} of ${people.length} customers would buy from ${name}.` + (bots.length ? ` ${bots.filter((p: any) => bought(sim, p.id)).length} of ${bots.length} AI shopping agents could buy for their user.` : "")];
  if (sim.actions?.length) out.push("Do these first:\n" + sim.actions.slice(0, 3).map((a: any, i: number) => `${i + 1}. ${a.fix} (${a.audience === "AI agents" ? "for AI agents" : a.audience === "both" ? "for people + agents" : "for people"})`).join("\n"));
  const bm = sim.summary?.by_model;
  if (bm && Object.keys(bm).length > 1) out.push(Object.entries(bm).map(([m, v]: any) => `${m} ${v.bought}/${v.of}`).join(" · "));
  const misses = people.filter((p: any) => !bought(sim, p.id) && sim.decisions[p.id].missing).slice(0, 3);
  if (misses.length && !sim.actions?.length) out.push("What would win them over:\n" + misses.map((p: any) => `• ${p.name}: ${sim.decisions[p.id].missing}`).join("\n"));
  if (sim.social?.summary) out.push(`What's spreading: ${sim.social.summary.replace(/\*\*/g, "").split(/(?<=\.)\s/)[0]}`);
  out.push(`Watch them shop: ${PUBLIC}/#sim=${sim.id}`);
  out.push(`Tell me what real customers do and they'll learn. Changed your site? Say what you changed, or "again" to test again.`);
  return out.join("\n\n");
}

// ---------- the conversation ----------
async function handle(key: string, text: string) {
  const c = chats.get(key)!;
  const t = text.trim();
  const low = t.toLowerCase();

  if (["help", "?", "hi", "hey", "hello"].includes(low)) {
    return c.send(`Hi! I test your website on AI customers before you launch. Text me your website (e.g. yourshop.com) and I'll have 4-7 customers try it, then tell you who'd buy and what would win the rest over.`);
  }
  const site = findSite(t);
  if (site && c.stage !== "approval") {
    const { id } = await api("/api/sims", { url: site });
    Object.assign(c, { sim: id, stage: "casting", seen: "" });
    return c.send(`Reading ${host(site)} and finding your customers… about 30 seconds.`);
  }
  if (!c.sim) return c.send(`Text me your website to start, e.g. yourshop.com`);

  if (c.stage === "approval") {
    if (/^(ok|okay|yes|yep|go|let them in|approve|looks good|lgtm)\b/.test(low)) {
      await api(`/api/sims/${c.sim}/approve`, {});
      c.stage = "running";
      return c.send(`They're in. Watching them shop now, about 3-4 minutes. Live: ${PUBLIC}/#sim=${c.sim}`);
    }
    await api(`/api/sims/${c.sim}/recast`, { feedback: t });
    c.stage = "casting";
    return c.send(`Got it, recasting with that in mind…`);
  }
  if (c.stage === "casting" || c.stage === "running") return c.send(`Still working on it. I'll text you as soon as there's something to see.`);

  // done
  if (/^(again|yes|run again|test again|go|rerun)\b/.test(low)) {
    const { id } = await api(`/api/sims/${c.sim}/rerun`, {});
    Object.assign(c, { sim: id, stage: "running", seen: "" });
    return c.send(`Same customers, carrying what they learned, are back on your site. About 3-4 minutes.`);
  }
  if (/^(i |we )?(changed|added|removed|updated|fixed|lowered|raised|put)\b/.test(low)) {
    const { id } = await api(`/api/sims/${c.sim}/rerun`, { change: t });
    Object.assign(c, { sim: id, stage: "running", seen: "" });
    return c.send(`Testing your change with the same customers so it's a fair before/after. About 3-4 minutes.`);
  }
  const { changes } = await api(`/api/sims/${c.sim}/teach`, { truth: t });
  return c.send(changes.length
    ? `${changes.length} customer${changes.length > 1 ? "s" : ""} updated what they know:\n${changes.slice(0, 3).map((x: any) => `• ${x.lesson.replace(/^From the owner: /, "")}`).join("\n")}\n\nSay "again" to test with them.`
    : `That didn't change anyone's mind about how they shop. Say "again" to test again anyway.`);
}

// Push updates as the simulation moves: cast ready → result ready.
async function watch() {
  for (const c of chats.values()) {
    if (!c.sim || c.stage === "idle" || c.stage === "done") continue;
    try {
      const sim = await api(`/api/sims/${c.sim}`);
      if (sim.status === "awaiting_approval" && c.stage === "casting" && c.seen !== "cast") {
        c.seen = "cast"; c.stage = "approval";
        await c.send(castText(sim));
      } else if (sim.status === "done" && c.seen !== "done") {
        c.seen = "done"; c.stage = "done";
        await c.send(resultText(sim));
      } else if (sim.status === "error" && c.seen !== "error") {
        c.seen = "error"; c.stage = "done";
        await c.send(`Something broke on our side: ${sim.error}. Text the website again to retry.`);
      }
    } catch (e) { console.error("watch:", e); }
  }
}
setInterval(watch, 4000);

// ---------- terminal mode ----------
if (TERMINAL) {
  console.log("Agent-ready (terminal mode). Type like you're texting. Ctrl+C to quit.\n");
  chats.set("me", { stage: "idle", seen: "", send: async (t) => console.log(`\n📱 agent: ${t}\n`) });
  const rl = readline.createInterface({ input: process.stdin });
  rl.on("line", (line) => { if (line.trim()) handle("me", line).catch((e) => console.error("error:", e.message)); });
} else {
  // ---------- iMessage via Photon 2.0 ----------
  const { Photon } = await import("@photon-ai/api");
  const photon: any = new Photon({ headers: { Authorization: `Bearer ${process.env.PHOTON_API_KEY}` } });
  const project = process.env.PHOTON_PROJECT_ID!;
  const agent = process.env.PHOTON_AGENT_HANDLE!;
  const handled = new Set<string>();
  let since = new Date().toISOString();
  console.log(`Agent-ready on iMessage at ${agent}. Text it a website.`);

  const poll = async () => {
    try {
      const page = await photon.projects.listMessages({ path: { id: project }, query: { direction: "received", order: "asc", pageSize: 100, platform: "imessage", createdSince: since } });
      for (const m of page.items as any[]) {
        if (handled.has(m.id)) continue;
        handled.add(m.id);
        if (m.createdAt && m.createdAt > since) since = m.createdAt;
        if (m.status !== "received" || m.sentBy?.kind !== "human" || m.receivedBy?.handle !== agent || m.content?.type !== "text") continue;
        const key = m.space.id;
        if (!chats.has(key)) {
          chats.set(key, { stage: "idle", seen: "", send: async (text) => {
            console.log(`→ ${new Date().toLocaleTimeString()} ${text.slice(0, 80).replace(/\n/g, " ")}`);
            await photon.projects.sendMessage({ path: { id: project }, headers: { "idempotency-key": `ar:${key}:${Date.now()}:${text.length}` },
              body: { spaceId: key, senderId: m.receivedBy.id, content: { type: "text", format: "plain", text } } });
          } });
        }
        console.log(`← ${new Date().toLocaleTimeString()} ${m.content.text.slice(0, 80)}`);
        handle(key, m.content.text).catch((e) => console.error("handle:", e.message));
      }
    } catch (e: any) { console.error("poll:", e.message ?? e); }
    setTimeout(poll, 2000);
  };
  poll();
}
