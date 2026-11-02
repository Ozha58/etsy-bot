import google.generativeai as genai
import os
import json
import random
import requests # Telegram'a bağlanmak için eklendi

# API Anahtarlarını ayarla
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

def send_telegram_message(text):
    """Bulunan nişi Telegram botuna gönderir."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram token veya chat_id eksik, mesaj gönderilemedi.")
        return
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            print("✅ Telegram'a mesaj başarıyla gönderildi!")
        else:
            print(f"❌ Telegram hatası: {response.text}")
    except Exception as e:
        print(f"❌ Telegram bağlantı hatası: {e}")

def find_trending_niche():
    print("🕵️‍♂️ Yapay Zeka pazar araştırması yapıyor, trendler analiz ediliyor...")
    
    categories = ["Hayvanlar", "Mevsimler", "Hobiler", "Fantastik", "Moda", "Yemek", "Uzay", "Bitkiler"]
    random_category = random.choice(categories)
    
    prompt = f"""
    Sen dünyanın en iyi Etsy satıcısısın. Yazdırılabilir 'Boyama Sayfaları' (Coloring Pages) satıyorsun.
    Şu anki hedefin: {random_category} kategorisinde, Etsy'de çok satan ama henüz çok fazla rakibin olmadığı (Blue Ocean stratejisi) 
    ÇOK SPESİFİK BİR MİKRO-NİŞ (Micro-niche) bulmak.
    
    Kurallar:
    1. Sadece "Noel", "Kedi", "Çiçek" gibi GENEL şeyler yazma. Bunlar çok rekabetli.
    2. Çok spesifik ol. Örneğin: "Gotik tarzda sevimli kediler", "Steampunk tarzı baykuşlar", "K-pop temalı çiçek desenleri", "80'ler retro tarzı uzaylılar".
    3. Yetişkinlerin veya çocukların boyamaktan keyif alacağı, çizgilerin net olacağı bir konsept olsun.
    
    Bana sadece ve sadece şu JSON formatında cevap ver, başka hiçbir açıklama yazma:
    {{
        "niche_name": "Bulduğun spesifik nişin adı (İngilizce, Etsy SEO uyumlu)",
        "reasoning": "Neden bu nişin çok satacağını düşündüğünü anlatan kısa bir Türkçe açıklama",
        "prompt_for_ai": "Bu nişi görselleştirmek için Midjourney/Gemini'ye verilecek detaylı İngilizce görsel promptu (örneğin: A beautiful line art coloring page of a gothic cute cat...)",
        "target_audience": "Bu ürünü kimler alır? (Örn: Gençler, Yetişkinler, Çocuklar)"
    }}
    """

    try:
        model = genai.GenerativeModel('gemini-3.6-flash')
        response = model.generate_content(prompt)
        
        text_response = response.text.strip()
        if text_response.startswith("```json"):
            text_response = text_response[7:-3]
        elif text_response.startswith("```"):
             text_response = text_response[3:-3]
             
        niche_data = json.loads(text_response)
        
        # Telegram'a gönderilecek mesaj formatı
        telegram_msg = f"""
🎯 <b>YENİ NİŞ BULUNDU!</b>
            
🏷️ <b>Niş Adı:</b> {niche_data.get('niche_name')}
💡 <b>Neden Satar?:</b> {niche_data.get('reasoning')}
🎯 <b>Hedef Kitle:</b> {niche_data.get('target_audience')}
🖼️ <b>Görsel Promptu:</b>
<code>{niche_data.get('prompt_for_ai')}</code>

👉 <i>Onaylıyor musun? (Onay sistemini bir sonraki adımda ekleyeceğiz)</i>
        """
        
        print("\n" + "="*50)
        print(telegram_msg)
        print("="*50 + "\n")
        
        # Telegram'a gönder
        send_telegram_message(telegram_msg)
        
        return niche_data
        
    except Exception as e:
        error_msg = f"❌ Niş aranırken bir hata oluştu: {e}"
        print(error_msg)
        send_telegram_message(error_msg)
        return None

if __name__ == "__main__":
    find_trending_niche()
