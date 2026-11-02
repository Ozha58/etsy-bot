import random
from . import llm
from .products import TYPES

def find_trending_niches(count=1):
    categories = ["Hayvanlar", "Mevsimler", "Hobiler", "Fantastik", "Moda", "Yemek", "Uzay", "Bitkiler"]
    random_category = random.choice(categories)
    
    # Yapay zekadan sadece niş fikri ve arama kelimesi istiyoruz. Türü biz seçeceğiz.
    prompt = f"""
    Sen dünyanın en iyi Etsy satıcısısın. Yazdırılabilir dijital ürünler satıyorsun.
    Şu anki hedefin: {random_category} kategorisinde, Etsy'de çok satan ama henüz çok fazla rakibin olmadığı 
    {count} ADET ÇOK SPESİFİK MİKRO-NİŞ (Micro-niche) fikri bulmak.
    
    Kurallar:
    1. Sadece "Noel", "Kedi", "Çiçek" gibi GENEL şeyler yazma.
    2. Çok spesifik ol. Örneğin: "Gotik tarzda sevimli kediler", "Steampunk tarzı baykuşlar", "80'ler retro tarzı uzaylılar".
    3. Yetişkinlerin veya çocukların ilgi duyacağı, çizgilerin net olacağı bir konsept olsun.
    
    Bana sadece ve sadece şu JSON DİZİSİ (Array) formatında cevap ver, başka hiçbir açıklama yazma:
    [
      {{
        "niche": "Bulduğun spesifik nişin adı (İngilizce)",
        "search_query": "Etsy'de aratılacak anahtar kelime",
        "why": "Neden bu nişin çok satacağını düşündüğünü anlatan kısa bir Türkçe açıklama",
        "etsy_results": 0
      }}
    ]
    """

    try:
        ideas = llm.ask_json(prompt)
        if isinstance(ideas, dict):
            ideas = [ideas]
            
        valid_ideas = []
        # Senin sistemindeki geçerli ürün tiplerini al (TYPES sözlüğünden)
        available_types = list(TYPES.keys())
        
        for idea in ideas:
            if "niche" in idea:
                # Yapay zekanın türünü yoksay, sistemdeki geçerli bir tür ata
                idea["type"] = random.choice(available_types) 
                valid_ideas.append(idea)
                
        if len(valid_ideas) >= count:
            return valid_ideas[:count]
            
    except Exception as e:
        print(f"AI Niş bulma hatası: {e}")
    
    # Yedek fikirler (Hata durumunda)
    fallback = []
    available_types = list(TYPES.keys())
    for i in range(count):
        fallback.append({
            "type": random.choice(available_types),
            "niche": f"Retro Botanical {i+1}",
            "search_query": "retro botanical printable",
            "why": "Yapay zeka yanıt veremedi, yedek niş kullanıldı.",
            "etsy_results": 0
        })
    return fallback
