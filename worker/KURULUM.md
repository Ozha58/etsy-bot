# Sakin mod kurulumu (GitHub hesabı açıldıktan SONRA)

GitHub hesabı açılmadan hiçbir şey yapmayın. Açılınca sırayla:

## 1. Kodu yükle (tek push)
1. GitHub Desktop'ta **Fetch / Pull origin** yapın.
2. Claude'a "hesap açıldı, yaz" deyin. Dosyaları klasörünüze yazacak.
3. GitHub Desktop'ta tek commit + **Push**.

## 2. Cloudflare Worker (5 dk, ücretsiz)
1. dash.cloudflare.com > **Workers & Pages** > **Create** > **Create Worker** > ad: `foxlantern-bot` > Deploy.
2. **Edit code**: içindekini silin, `worker.js` dosyasının tamamını yapıştırın > Deploy.
3. **Storage & Databases > KV** > Create namespace: `foxlantern-q`.
4. Worker > **Settings > Bindings** > Add > KV namespace: değişken adı `Q`, namespace `foxlantern-q`.
5. Worker > **Settings > Variables and Secrets** > şunları ekleyin:
   - `TG_TOKEN` (Secret): Telegram bot token'ı (GitHub'daki TELEGRAM_BOT_TOKEN ile aynı)
   - `CHAT_ID`: GitHub'daki TELEGRAM_CHAT_ID ile aynı
   - `TG_SECRET` (Secret): uydurma uzun bir kelime, ör. `tilki-fener-8842-orman`
   - `PULL_KEY` (Secret): başka uydurma uzun bir kelime, ör. `kuyruk-anahtar-5531-ay`
   - `GH_REPO`: `Ozha58/etsy-bot`
   - `GH_TOKEN` (Secret): aşağıdaki 3. adımdaki token

## 3. GitHub token (Worker'ın iş başlatabilmesi için)
github.com > Settings > Developer settings > **Fine-grained tokens** > Generate:
- Repository access: **Only select** > `etsy-bot`
- Permissions > **Actions: Read and write** (başka hiçbir şey)
- Süre: 1 yıl. Çıkan token'ı Worker'a `GH_TOKEN` olarak koyun.

## 4. GitHub secret'ları
etsy-bot > Settings > Secrets and variables > Actions > New secret:
- `TG_WORKER_URL`: Worker adresi, ör. `https://foxlantern-bot.KULLANICI.workers.dev`
- `TG_WORKER_KEY`: Worker'daki `PULL_KEY` ile aynı kelime

## 5. Telegram'ı Worker'a bağla
Tarayıcıda açın: `https://foxlantern-bot.KULLANICI.workers.dev/setup?key=PULL_KEY`
`"ok":true` görürseniz tamam. Telegram'a `/kota` yazın; 1-2 dakika içinde cevap gelmeli.

## Nasıl çalışır
- Telegram'a yazınca / butona basınca GitHub'da tek kısa iş başlar (1-2 dk), biter.
- Günde 3 kez (11:20, 17:00, 21:00) kısa kontrol: günlük üretimi başlatır, pinler, kişiye özel siparişler.
- Her iş en fazla 1 commit yapar. Sürekli çalışan hiçbir şey yok.
