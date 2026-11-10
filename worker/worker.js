// Foxlantern Telegram köprüsü (Cloudflare Worker, ücretsiz plan yeterli).
// Telegram mesajlarını bu Worker alır, kuyruğa (KV) koyar ve GitHub'da TEK kısa iş (poll.yml) başlatır.
// Böylece GitHub'da sürekli çalışan hiçbir şey kalmaz; iş sadece siz bir şey yazınca / butona basınca başlar.
//
// Ayarlar (Worker > Settings > Variables and Secrets):
//   TG_TOKEN   Telegram bot token'ı                    (Secret)
//   TG_SECRET  rastgele uzun bir kelime (webhook şifresi) (Secret)
//   CHAT_ID    sizin Telegram sohbet numaranız
//   GH_TOKEN   GitHub fine-grained token (sadece etsy-bot, Actions: Read and write) (Secret)
//   GH_REPO    Ozha58/etsy-bot
//   PULL_KEY   rastgele uzun bir kelime; GitHub'da TG_WORKER_KEY secret'ı ile aynı (Secret)
// KV bağlantısı (Bindings > KV namespace): değişken adı  Q

const json = (o, s = 200) => new Response(JSON.stringify(o), { status: s, headers: { "content-type": "application/json" } });

async function tg(env, method, body) {
  return fetch(`https://api.telegram.org/bot${env.TG_TOKEN}/${method}`, {
    method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body),
  });
}

async function startJob(env) {
  // the same button pressed several times in a row starts only one job
  const last = Number(await env.Q.get("last_dispatch")) || 0;
  if (Date.now() - last < 20000) return;
  await env.Q.put("last_dispatch", String(Date.now()));
  const r = await fetch(`https://api.github.com/repos/${env.GH_REPO}/actions/workflows/poll.yml/dispatches`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.GH_TOKEN}`, Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "foxlantern-worker",
    },
    body: JSON.stringify({ ref: "main", inputs: {} }),
  });
  if (r.status >= 300) {
    await env.Q.delete("last_dispatch");
    await tg(env, "sendMessage", { chat_id: env.CHAT_ID, text: `⚠️ GitHub işi başlatılamadı (HTTP ${r.status}). Token süresi dolmuş olabilir.` });
  }
}

export default {
  async fetch(req, env, ctx) {
    const url = new URL(req.url);
    const key = req.headers.get("X-Key") || url.searchParams.get("key");

    // Telegram -> Worker
    if (url.pathname === "/tg" && req.method === "POST") {
      if (req.headers.get("X-Telegram-Bot-Api-Secret-Token") !== env.TG_SECRET) return new Response("no", { status: 403 });
      const u = await req.json();
      const src = u.callback_query || u.message || {};
      const chat = u.callback_query ? src.message?.chat?.id : src.chat?.id;
      if (String(chat) !== String(env.CHAT_ID)) return new Response("ok");
      await env.Q.put(`u:${String(u.update_id).padStart(12, "0")}`, JSON.stringify(u), { expirationTtl: 7 * 86400 });
      if (u.callback_query) {
        ctx.waitUntil(tg(env, "answerCallbackQuery", { callback_query_id: u.callback_query.id, text: "⏳ Tamam, 1-2 dakika içinde işlenecek" }));
      }
      ctx.waitUntil(startJob(env));
      return new Response("ok");
    }

    if (!env.PULL_KEY || key !== env.PULL_KEY) return new Response("no", { status: 403 });

    // GitHub job -> Worker: queued updates
    if (url.pathname === "/pull") {
      const list = await env.Q.list({ prefix: "u:", limit: 100 });
      const updates = [];
      for (const k of list.keys) {
        const v = await env.Q.get(k.name);
        if (v) updates.push(JSON.parse(v));
      }
      return json({ updates });
    }

    // GitHub job -> Worker: these are done
    if (url.pathname === "/ack" && req.method === "POST") {
      const { ids = [] } = await req.json();
      await Promise.all(ids.map((id) => env.Q.delete(`u:${String(id).padStart(12, "0")}`)));
      return json({ ok: true, deleted: ids.length });
    }

    // one-time: connect Telegram to this Worker (open https://<worker>/setup?key=PULL_KEY in the browser)
    if (url.pathname === "/setup") {
      const r = await tg(env, "setWebhook", {
        url: `${url.origin}/tg`, secret_token: env.TG_SECRET,
        allowed_updates: ["message", "callback_query"], drop_pending_updates: false,
      });
      return json(await r.json());
    }
    if (url.pathname === "/status") {
      const r = await tg(env, "getWebhookInfo", {});
      return json(await r.json());
    }
    return new Response("Foxlantern köprüsü çalışıyor 🦊");
  },
};
