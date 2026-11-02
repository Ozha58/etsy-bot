import google.generativeai as genai
import os
import json
import random

# API Anahtarını ayarla (GitHub Secrets üzerinden çekiyoruz)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    print("HATA: GEMINI_API_KEY bulunamadı. Lütfen GitHub Secrets ayarlarını kontrol et.")

def find_trending_niche():
    """
    Yapay zekayı kullanarak Etsy için en karlı ve düşük rekabetli 
    mikro-niş (micro-niche) fikirlerini bulur.
    """
    print("🕵️‍♂️ Yapay Zeka pazar araştırması yapıyor, trendler analiz ediliyor...")
    
    # Botun ilham alması için rastgele kategoriler
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
        # Gemini modelini başlat
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        
        # Gelen cevabı JSON olarak temizle ve oku
        text_response = response.text.strip()
        # Bazen AI ```json ... ``` şeklinde cevap verebilir, onu temizleyelim
        if text_response.startswith("```json"):
            text_response = text_response[7:-3]
        elif text_response.startswith("```"):
             text_response = text_response[3:-3]
             
        niche_data = json.loads(text_response)
        
        print("\n" + "="*50)
        print("🎯 YENİ NİŞ BULUNDU!")
        print("="*50)
        print(f"🏷️  Niş Adı: {niche_data.get('niche_name')}")
        print(f"💡 Neden Satar?: {niche_data.get('reasoning')}")
        print(f"🎯 Hedef Kitle: {niche_data.get('target_audience')}")
        print(f"🖼️  Görsel Promptu: {niche_data.get('prompt_for_ai')}")
        print("="*50 + "\n")
        
        return niche_data
        
    except Exception as e:
        print(f"❌ Niş aranırken bir hata oluştu: {e}")
        return None

# Bu dosya doğrudan çalıştırıldığında test etmek için:
if __name__ == "__main__":
    find_trending_niche()
