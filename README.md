# Delivery Route Optimization with Ant Colony Optimization

![Python](https://img.shields.io/badge/Python-3776AB?style=flat-square&logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=flat-square&logo=streamlit&logoColor=white)
![OSMnx](https://img.shields.io/badge/OSMnx-7EBC6F?style=flat-square&logo=openstreetmap&logoColor=white)
![NetworkX](https://img.shields.io/badge/NetworkX-2C5BB4?style=flat-square)
![Folium](https://img.shields.io/badge/Folium-77B829?style=flat-square)
[![tests](https://github.com/aaas72/RotasOptimizasyonu/actions/workflows/tests.yml/badge.svg)](https://github.com/aaas72/RotasOptimizasyonu/actions/workflows/tests.yml)

**English overview** — An interactive tool that finds the shortest delivery route through several stops in the city of Elazığ, Türkiye, using **Ant Colony Optimization (ACO)** on the real road network from OpenStreetMap.

- **Real, directed road costs** — shortest paths on the OSM drive network respect one-way streets, so the distance matrix is asymmetric; optimize by **distance (km)** or **travel time (min)**
- **Routes drawn on the actual roads** — not straight lines between stops
- **Improved ACO** — fixed depot, closed tour or open path, elitist ant, MAX-MIN pheromone bounds, 2-opt local search, early stopping
- **Benchmarks built in** — every run is compared with Nearest Neighbour, Nearest Neighbour + 2-opt and (for ≤ 9 stops) the exact brute-force optimum
- **Flexible input** — pick from known locations, click on the map, or upload a CSV; edit everything in one table
- **Export** — route table as CSV and one-click Google Maps directions
- **Works offline too** — without the road network file the app falls back to straight-line distance × 1.3

```bash
pip install -r requirements.txt
python src/generate_graphml.py      # one-time download of the Elazığ road network (~12 MB)
python src/main.py                  # or: streamlit run src/ui/app.py
```

The detailed documentation below is in Turkish.

---

## Elâzığ Şehir İçi Teslimat Rotası Optimizasyonu (ACO Projesi)

Bu proje, **Elâzığ**'da birden fazla durak arasındaki en kısa (veya en hızlı) teslimat rotasını bulmak için **Karınca Kolonisi Optimizasyonu (Ant Colony Optimization, ACO)** algoritmasını OpenStreetMap'in gerçek yol ağı üzerinde kullanır.

## İçindekiler

1. [Proje Yapısı](#proje-yapısı)
2. [Kurulum ve Çalıştırma](#kurulum-ve-çalıştırma)
3. [Arayüz ve Kullanım](#arayüz-ve-kullanım)
4. [ACO Algoritmasının İşleyişi](#aco-algoritmasının-işleyişi)
5. [Maliyet Matrisi Hesaplama](#maliyet-matrisi-hesaplama)
6. [Sonuçlar ve Karşılaştırma](#sonuçlar-ve-karşılaştırma)
7. [Testler](#testler)
8. [Gelecek Geliştirmeler](#gelecek-geliştirmeler)

---

## Proje Yapısı

```
RotasOptimizasyonu/
├── requirements.txt / requirements-dev.txt
├── .github/workflows/tests.yml   # GitHub Actions: her push'ta pytest
├── tests/                        # ACO, TSP, CSV/dışa aktarım, OSM ve arayüz testleri
└── src/
    ├── main.py                   # `python src/main.py` ile uygulamayı başlatır
    ├── generate_graphml.py       # Elâzığ yol ağını indirip src/data/elazig_osm.graphml'e kaydeder
    ├── aco/
    │   ├── algorithm.py          # ACO (depo, açık/kapalı rota, elitist, MMAS sınırları, 2-opt)
    │   ├── tsp.py                # En Yakın Komşu, 2-opt, kaba kuvvet (kesin optimum)
    │   └── utils.py              # Haversine mesafesi ve yaklaşık mesafe matrisi
    ├── data/
    │   ├── osm_data.py           # Yol ağı indirme/yükleme, nokta eşleme, mesafe/süre matrisi, rota geometrisi
    │   └── location_data.py      # Hazır Elâzığ noktaları ve CSV okuma
    └── ui/
        ├── app.py                # Streamlit arayüzü
        ├── map_visualization.py  # Folium haritaları (gerçek yol geometrisi, numaralı duraklar)
        ├── plots.py              # Plotly: yakınsama, karşılaştırma, ısı haritası
        └── export.py             # Rota tablosu, Google Maps bağlantıları
```

---

## Kurulum ve Çalıştırma

Python **3.10+** gereklidir.

```bash
# 1) Sanal ortam (opsiyonel)
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # Windows PowerShell
# source .venv/bin/activate         # Linux / macOS

# 2) Paketler
pip install -r requirements.txt

# 3) Elâzığ yol ağı (bir kez, 1-3 dk)
python src/generate_graphml.py
#   --radius 12000                  # merkez etrafında indirilecek yarıçap (m, varsayılan 9000)
#   --place "Merkez, Elazığ, Türkiye"

# 4) Uygulama
python src/main.py                  # veya: streamlit run src/ui/app.py
```

- Script, hangi klasörden çalıştırılırsa çalıştırılsın dosyayı `src/data/elazig_osm.graphml` konumuna kaydeder.
- Overpass sunucusu meşgulse otomatik olarak yedek sunucular denenir.
- Dosya yoksa uygulama yine çalışır (kuş uçuşu × 1.3 yaklaşık mesafe) ve kenar çubuğunda **"Elâzığ yol ağını indir"** butonu sunar.
- Yol ağına hız ve seyahat süresi bilgisi eklenir (OSM `maxspeed` etiketi, yoksa yol tipine göre varsayılan hız).

---

## Arayüz ve Kullanım

### 1. Teslimat durakları

Duraklar üç yolla eklenir ve hepsi sağdaki **tek bir düzenlenebilir tabloda** toplanır (ad, enlem, boylam düzenlenebilir; satır silinebilir):

- **Hazır noktalar** — Elâzığ'daki 20 nokta; aranabilir çoklu seçim.
- **Haritadan ekle** — haritaya her tıklama yeni bir durak ekler; mevcut duraklar numaralı işaretlerle görünür.
- **CSV yükle** — kolonlar `name, latitude, longitude` (alternatif: `ad, enlem, boylam`, `lat, lon/lng`); ayraç `,` veya `;`. Örnek şablon indirilebilir.

### 2. Rota

- **Başlangıç noktası (depo)** — rotanın başladığı durak.
- **Depoya geri dön** — kapalı tur (kurye depoya döner) veya açık rota (son durakta biter).

### Kenar çubuğu ayarları

| Ayar | Açıklama | Varsayılan |
|---|---|---|
| Gerçek yol ağı (OSM) | Kapalıysa kuş uçuşu × 1.3 | Açık |
| Optimizasyon kriteri | Mesafe (km) veya Süre (dk) | Mesafe |
| Karınca sayısı / Maks. iterasyon / Tohum | | 20 / 100 / 42 |
| Erken durdurma (sabır) | Bu kadar iterasyon iyileşme yoksa dur | 30 |
| α, β, ρ, Q | Feromon etkisi, mesafe etkisi, buharlaşma, feromon sabiti | 1.0, 3.0, 0.3, 100 |
| Elitist ağırlık | En iyi rotaya ekstra feromon | 1.0 |
| 2-opt yerel arama | İterasyonun en iyi rotasındaki kesişmeleri giderir | Açık |

### Sonuçlar

- **Özet** — toplam mesafe, tahmini sürüş süresi, En Yakın Komşu'ya göre iyileşme, optimuma uzaklık (≤ 9 durak).
- **Harita** — rota gerçek yollar üzerinde (hareketli çizgi), depo "D", duraklar ziyaret sırasıyla numaralı; her ayağın üzerine gelince mesafe/süre görünür.
- **Rota detayı** — ayak ayak tablo (mesafe, süre, kümülatif), CSV indirme, **Google Maps'te aç** (11'den fazla durakta rota parçalara bölünür).
- **Yakınsama** — iterasyon başına en iyi / ortalama / en kötü maliyet.
- **Karşılaştırma** — ACO, En Yakın Komşu, En Yakın Komşu + 2-opt ve kesin optimum.
- **Maliyet matrisi** — mesafe veya süre ısı haritası; matrisin asimetriklik derecesi.

---

## ACO Algoritmasının İşleyişi

1. **Hazırlık** — `n × n` maliyet matrisi (km veya dk). Ulaşılamayan çiftler (`inf`) büyük bir ceza değeriyle değiştirilir. Sezgisel bilgi `η = (1/d)^β`. Başlangıç feromonu `τ₀ = Q / L_NN` (En Yakın Komşu rotasının uzunluğu).
2. **Rota oluşturma** — her karınca depodan başlar ve bir sonraki durağı `τ^α · η` ile orantılı olasılıkla seçer (vektörel, `numpy.random.Generator`).
3. **Yerel arama** — iterasyonun en iyi rotasına **2-opt** uygulanır. Asimetrik matrislerde ters çevrilen parçanın iç kenarlarının maliyeti de hesaba katılır.
4. **Feromon güncelleme**
   - Buharlaşma: `τ ← (1 − ρ) · τ`
   - Her karınca: rotasındaki kenarlara `Q / L`
   - Elitist: şimdiye kadarki en iyi rotaya `e · Q / L_best`
   - **MAX-MIN sınırları**: `τ` değerleri `[τ_min, τ_max]` aralığına kırpılır (Stützle & Hoos, 2000). Bu, feromonun tek bir rotada kilitlenmesini (durgunluk) önler.
   - Matris simetrikse feromon iki yöne, asimetrikse yalnızca gidilen yöne eklenir.
5. **Durdurma** — maksimum iterasyon veya `sabır` kadar iterasyon iyileşme olmaması.

```python
from aco.algorithm import ACO

aco = ACO(dist_matrix, ant_count=20, start=0, return_to_start=True, seed=42)
best_route, best_length, history = aco.run(iterations=100, patience=30)
```

---

## Maliyet Matrisi Hesaplama

1. **Nokta eşleme** — her durak, en yakın yol düğümüne (Haversine) bağlanır; 300 m'den uzak duraklar için uyarı verilir.
2. **Dijkstra** — her durak için **tek bir** `single_source_dijkstra_path_length` çağrısı (eskiden her çift için ayrı çağrı: `n²/2` → `n`). Hem `length` (km) hem `travel_time` (dk) hesaplanır.
3. **Yönlü ağ** — sürüş ağı tek yönlü yolları içerdiğinden `d[i][j] ≠ d[j][i]` olabilir. Elâzığ'daki 20 hazır noktada gidiş-dönüş farkı **1.2 km**'ye kadar çıkmaktadır; bu yüzden matris artık simetrik varsayılmaz.
4. **Rota geometrisi** — seçilen rotanın her ayağı için yol kenarlarının gerçek geometrisi haritaya çizilir.

---

## Sonuçlar ve Karşılaştırma

20 hazır Elâzığ noktası, kapalı tur, gerçek (yönlü) yol mesafeleri, 20 karınca / 100 iterasyon:

| Yöntem | Toplam mesafe | Süre |
|---|---|---|
| En Yakın Komşu | 33.78 km | < 1 ms |
| En Yakın Komşu + 2-opt | 29.18 km | ~ 5 ms |
| Önceki ACO sürümü* | 30.33 – 31.47 km | ~ 1.7 sn |
| **Yeni ACO** (3 farklı tohum) | **28.90 – 29.06 km** | **~ 0.5 sn** |

\* Önceki sürüm simetrik matris kullandığından ekranda 29.43 km gösteriyordu; bulduğu rotanın gerçek yönlü mesafesi 30.3 – 31.5 km'dir.

≤ 9 duraklı problemlerde ACO sonucu kaba kuvvetle bulunan kesin optimumla karşılaştırılır; testlerde rastgele örneklerin en az %90'ında kesin optimum bulunmaktadır.

**Uygulama alanları:** kurye/teslimat lojistiği, saha ekiplerinin ziyaret sırası, turistik gezi rotaları.

---

## Testler

```bash
pip install -r requirements-dev.txt
pytest -q
```

- `tests/test_aco.py` — kesin optimumla karşılaştırma, simetrik/asimetrik, açık/kapalı rota, depo, ulaşılamayan kenarlar, tohum tekrarlanabilirliği, erken durdurma
- `tests/test_io.py` — CSV okuma (alternatif kolonlar, `;` ayracı), Google Maps bağlantıları, rota tablosu
- `tests/test_osm.py` — gerçek yol ağıyla matris ve geometri (GraphML yoksa atlanır)
- `tests/test_app.py` — Streamlit arayüzünün uçtan uca testi (`streamlit.testing`)

---

## Gelecek Geliştirmeler

- [x] ~~Trafik/süre temelli hesaplama~~ → hız sınırlarına dayalı süre optimizasyonu eklendi
- [x] ~~Harita üzerinde nokta silme~~ → tüm duraklar tabloda düzenlenip silinebilir
- [ ] **Zaman pencereleri (VRPTW)** — durakların belirli saatlerde ziyaret edilmesi
- [ ] **Birden fazla araç / kapasite (CVRP)** — durakların araçlar arasında bölüştürülmesi
- [ ] **Gerçek zamanlı trafik** — OpenRouteService / OSRM ile canlı süreler
- [ ] **Paralel karıncalar** — çok çekirdekli rota oluşturma

---

## Author

**Abdellah Sheikh** — [abdellahsheikh.dev](https://abdellahsheikh.dev) · [LinkedIn](https://www.linkedin.com/in/abdellahsheikh)
