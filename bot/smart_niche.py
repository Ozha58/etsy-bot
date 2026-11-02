import random
from . import llm

def find_trending_niches(count=1):
    categories = ["Hayvanlar", "Mevsimler", "Hobiler", "Fantastik", "Moda", "Yemek", "Uzay", "Bitkiler"]
    random_category = random.choice(categories)
    
    # DİKKAT: Kotayı korumak için tek istekte birden fazla fikir istiyoruz
    prompt = f"""
    Sen dünyanın en iyi Etsy satıcısısın. Yazdırılabilir 'Boyama Sayfaları' (Coloring Pages) satıyorsun.
    Şu anki hedefin: {random_category} kategorisinde, Etsy'de çok satan ama henüz çok fazla rakibin olmadığı 
    {count} ADET ÇOK SPESİFİK MİKRO-NİŞ (Micro-niche) fikri bulmak.
    
    Kurallar:
    1. Sadece "Noel", "Kedi", "Çiçek" gibi GENEL şeyler yazma.
    2. Çok spesifik ol. Örneğin: "Gotik tarzda sevimli kediler", "Steampunk tarzı baykuşlar", "80'ler retro tarzı uzaylılar".
    3. Yetişkinlerin veya çocukların boyamaktan keyif alacağı, çizgilerin net olacağı bir konsept olsun.
    
    Bana sadece ve sadece şu JSON DİZİSİ (Array) formatında cevap ver, başka hiçbir açıklama yazma:
    [
      {{
        "type": "coloring_page",
        "niche": "Bulduğun spesifik nişin adı (İngilizce)",
        "search_query": "Etsy'de aratılacak anahtar kelime",
        "why": "Neden bu nişin çok satacağını düşündüğünü anlatan kısa bir Türkçe açıklama",
        "etsy_results": 0
      }}
    ]
    """

    try:
        ideas = llm.ask_json(prompt)
        # Eğer tek bir obje dönerse listeye çevir
        if isinstance(ideas, dict):
            ideas = [ideas]
            
        # İstenen sayıda fikir geldiğinden emin ol
        valid_ideas = []
        for idea in ideas:
            if "niche" in idea and "type" in idea:
                valid_ideas.append(idea)
                
        if len(valid_ideas) >= count:
            return valid_ideas[:count]
            
    except Exception as e:
        print(f"AI Niş bulma hatası: {e}")
    
    # Eğer AI hata verirse veya limit dolarsa botun çökmemesi için yedek fikirler
    fallback = []
    for i in range(count):
        fallback.append({
            "type": "coloring_page",
            "niche": f"Retro Christmas {i+1}",
            "search_query": "retro christmas coloring page",
            "why": "Yapay zeka yanıt veremedi, yedek niş kullanıldı.",
            "etsy_results": 0
        })
    return fallback
