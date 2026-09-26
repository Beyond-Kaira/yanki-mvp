# Top Cited Pages for Your Industry — Yankı uygulama planı

## Geçerli karar — 2026-09-20

Önceki yeni soru üretme yaklaşımı kullanıcı tarafından iptal edildi. Kaynak,
tüm organizasyonlardaki mevcut GEO kayıtlarıdır. Sektör sorunun içeriğinden
tahmin edilmeyecek; `GeoRecord.sector` etiketiyle seçilecek. Kapsam “bu
sektördeki şirketlerin GEO analizleri”dir; ürün/giyim/kozmetik soruları da bu
etiketin altında bulunabilir. `brand-probe` kayıtları hariçtir.

İlk parça `backend/app/industry_citations/ranking.py` içindeki bağımsız,
salt okunur toplama modülüdür. Mevcut canlılık ve atıf kanıtı kuralları uygulanır.
Eski kayıtlarda eksik canlılık bilgisi tahminle doldurulmaz; bu kayıtlar ayrı
sayılır ve doğrulanana kadar sıralamaya katılmaz. Tek yanıt aynı sitede birden
fazla sayfa kullansa da site sayımı birdir. Tekrarlanan çalıştırmalar ayrı
gözlemdir; soru sayısında Unicode/büyük-küçük harf/boşluk normalizasyonundan
sonra aynı metin tek sayılır. Hostname gruplaması kullanılır; alt alan adları
otomatik birleştirilmez. Müşteri kimliği, soru/yanıt metni ve kayıt ID'leri
çıktıda yoktur. Kullanıcı onayıyla API ve ekran bağlantısı tamamlandı:
`GET /api/v1/industry-citations/sectors` mevcut sektörleri;
`GET /api/v1/industry-citations/ranking?sector=...` ortak sıralamayı döndürür.
Her ikisi oturum ve `analysis:read` yetkisi gerektirir. Sektör ekranı artık
yeni soru üretmez; mevcut kayıtları site → açılabilir sayfalar olarak gösterir.
Eski Citations ekranı korunur. Eski soru üretme API'si korunmuş ancak bu
ekrandan kullanılmamaktadır.

Yerel doğrulama: 99 aday e-commerce kaydından 4 brand-probe ve canlılık bilgisi
eksik 65 kayıt hariç; 30 yanıt, 10 farklı soru, 36 sayfa, 34 site. Yanıt içi
atıf işareti olmayan 22 atıf reddedildi. Dokuz test, Ruff ve mypy geçti.
API/UI doğrulaması: 31 backend ve 20 frontend testi geçti; tip/lint kontrolleri
geçti. Tarayıcıda sektör seçimi, e-commerce sonuçları, sayfa açılımı, ileri/geri
sayfalama ve AI sektörünün doğrulanmış veri yok açıklaması kontrol edildi.
Yanıtlar varsayılan 25 site, site başına ilk 50 sayfayla sınırlı; toplamlar
tüm sonuçları kapsar. Toplama halen kayıtları tarar; büyük veri için indeksli
normalize sektör ve ön hesaplama sonraki performans işidir. Bu parça kullanıcı
incelemesini bekliyor; eski kayıtların canlılık doğrulaması henüz tamamlanmadı.

Aşağıdaki bölümler önceki yaklaşımın tarihsel kaydıdır.

Tarih: 2026-09-17. Kapsam düzeltmesi: kullanıcı sektör girişiyle başlayan,
mevcut marka analizinden bağımsız bir kaynak keşif ekranı istiyor. Aşağıdaki
A–D uygulaması bu hedefi tamamlamıyor; önceki analiz bazlı yaklaşımın kaydıdır.
Eski Citations ekranı geri getirildi. Yeni ekran Citations altında ayrı bir
alt sayfa olarak, her parçada kullanıcı onayıyla geliştirilecek. İlk karar:
sektör → sektör soruları → arama destekli model yanıtları → doğrulanmış atıf
sıralaması. Bu ölçüm tüm sektörün eksiksiz indeksi olarak sunulmamalı.

### Güncel sektör akışı — parça 1 (2026-09-18)

`/ai-visibility/industry-citations` giriş önizlemesi eklendi. Menüde Citations
hemen altında yer alır. Serbest sektör ve ülke, dil seçimi, soruları önce
düzenleme veya doğrudan başlatma tercihi bulunur. Bu parçada yalnızca form
önizlemesi çalışır; sorular üretilmez, veri kaydedilmez, model çağrılmaz.
Ülke şimdilik serbest metindir; dil seçimi gelecekteki analiz için tercihtir,
sağlayıcı desteği garantisi değildir. Sonuç hedefi: siteler ve açılabilir sayfalar.
Kullanıcı kontrolünden sonra soru üretimi/düzenleme parçasına geçilecek.
Aşağıdaki eski marka analizi kapsamı tarihsel kayıttır.

### Sektör akışı — parça 2 (2026-09-19)

Bağımsız soru üretimi ve düzenleme tamamlandı. Kimlik doğrulamalı
`POST /api/v1/industry-citations/questions` endpoint'i sektör, ülke ve ISO
639-1 dil kodunu alır; OpenRouter üzerinden tam 10 farklı soru üretir. Model
çıktısı JSON şemasıyla doğrulanır; eksik, yinelenen veya geçersiz soru seti
502 olarak reddedilir ve sağlayıcı metni istemciye yansıtılmaz. `analysis:run`
yetkisi gerekir. Organizasyon başına saatlik 10 deneme sınırı sağlayıcı
çağrısından önce kalıcı olarak artırılır; başarılı ve hatalı çağrılar audit
loguna model ve maliyet bilgisiyle yazılır.

Arayüzde review yolunda sorular düzenlenebilir, eklenebilir ve silinebilir;
direct yolunda üretilen set salt okunur gösterilir. Değişiklikler henüz
sunucuda saklanmaz. “Start analysis” üçüncü parça olan job/persistence ve
arama destekli yanıt üretimi eklenene kadar devre dışıdır. Canlı yerel kontrolde
“Koşu ayakkabıları / Türkiye / Türkçe” örneğiyle 10 Türkçe soru üretildi.

## 1. Araştırma sonucu

Yerel Semrush raporlarının kaynak metinlerinde ilgili özellik bulundu:

- `tmp/semrush-ai/content.py`: Visibility Overview, Competitor Research ve Narrative Drivers bölümleri.
- `tmp/semrush-ai/1596-visibility-overview-report.txt`: Topics & Sources; Cited Pages, Cited Sources ve Source Opportunities açıklamaları.
- `tmp/semrush-ai/1598-competitor-research-report.txt`: rakibin anıldığı, hedef markanın anılmadığı yanıtların kaynakları.
- `output/yanki-semrush-code-gap-analysis-tr.md`: mevcut citation altyapısı ve Citation Opportunities önerisi.

Tam “Top Cited Pages for Your Industry” başlığı incelenen yerel metinlerde doğrulanamadı. Aşağıdaki resmi kaynaklarla yakın özelliklerin anlamı kontrol edildi; bu plan birebir Semrush ekran kopyası iddiası taşımıyor.

Semrush Visibility Overview'da Cited Pages, analiz edilen şirketin kaynak gösterilen sayfalarını; Cited Sources, yanıt kaynaklarını; Source Opportunities ise rakipler anılırken markanın eksik kaldığı yanıtların kaynaklarını gösterir. Yanıt detayları üzerinden prompt, cevap ve kaynaklar incelenebilir. [Resmi açıklama](https://www.semrush.com/kb/1596-visibility-overview-report)

Semrush'ın ücretsiz aracındaki Top Cited Pages tanımı da analiz edilen web sitesinin en sık kaynak gösterilen sayfalarına odaklanır. [Resmi açıklama](https://www.semrush.com/free-tools/ai-search-visibility-checker/)

**Yankı için öneri:** sektörle ilgili seçilmiş sorularda kaynak gösterilen bütün sayfaları listelemek; kullanıcının, rakiplerin ve üçüncü tarafların sayfalarını filtrelerle ayırmak. Bu, yukarıdaki araştırmadan türetilmiş ürün önerisidir.

## 2. Mevcut kod ve açıklar

| Alan | Mevcut durum | Gerekli geliştirme |
| --- | --- | --- |
| Citation ekranı | `frontend/app/ai-visibility/citations/CitationsClient.tsx` alan adlarını ve açılır URL listesini gösteriyor | URL bazlı sıralama, filtreler, yanıt kanıtına geçiş |
| Veri dönüşümü | `frontend/lib/ai-visibility-data.ts` alan adı başına sayım yapıyor; URL listesini tekilleştiriyor | Yanıt × URL tekilleştirme; URL başına yanıt/prompt sayısı |
| Depolama | `GeoRecord`: sector, prompt, response_id, citations, competitors, generated_at | Mevcut kayıtları Response ve Analysis ile ilişkilendirerek model ve yöntem bilgisi |
| API | `GeoOut` ve `build_geo_out` citation kayıtlarını döndürüyor | Tipli kaynak raporu ve ölçüm metadatası; mevcut GeoOut'ta geo_run yok |
| Ölçüm | Tavily araması + OpenRouter üzerinden oluşturulan grounded yanıtlar | Kullanıcıya gerçek veri kapsamı; native platform gözlemiyle karıştırmama |
| Simülasyon | `simulated.py` olası kaynaklar üretebiliyor | Canlı sıralamadan çıkarma; demo verisini açık etiketleme |
| Kanıt doğrulama | `normalize_grounded_citations` modelin URL/domain alanını arama sonucundan önce tercih ediyor; eşleşmeyen rank boş lookup'a düşebiliyor | Kaynak rank eşleşmesini zorunlu tutma; URL/domain/title için arama sonucunu esas alma |

Kod incelemesi statiktir; bu çalışma kapsamında canlı analiz çalıştırılmadı.

## 3. Ürün kapsamı

İlk ekran mevcut **AI Visibility → Citations** altında geliştirilir. Başlık “Top Cited Pages”; açıklama “Seçili sektör sorularında en çok kaynak gösterilen sayfalar”. Analiz kimliği URL'de korunur.

- Üst özet: farklı sayfa, farklı alan adı, değerlendirilen başarılı yanıt ve kapsanan soru sayısı.
- Kapsam satırı: sektör, analiz tarihi, kullanılan modeller, ölçüm yöntemi ve örneklem büyüklüğü.
- Görünümler: Pages / Domains. Filtreler: model, soru grubu, sahiplik (tümü / bize ait / rakip / üçüncü taraf), URL veya başlık araması.
- Tablo: sayfa başlığı ve URL, alan adı, kaynak gösteren yanıt sayısı, yanıt kapsamı yüzdesi, farklı soru sayısı, modeller, sahiplik.
- Satır detayı: ilgili sorular, yanıt metni, kaynak konumu ve gözlem zamanı; orijinal sayfaya bağlantı.
- Fırsat görünümü: seçilen rakiplerden en az birinin anıldığı, hedef markanın açıkça anılmadığı yanıtların üçüncü taraf kaynakları. Kaynak sayfanın markayı anmadığı veya backlink vermediği ayrıca doğrulanmış sayılmaz.
- CSV dışa aktarımı: ekrandaki filtreli sonuçlar, kapsam ve ölçüm yöntemiyle birlikte; formül enjeksiyonuna karşı güvenli hücre yazımı.

Boş analiz, başarısız yanıt, kaynak bulunmaması ve yalnız simülasyon bulunması ayrı mesajlarla gösterilir. Veri yokluğu sıfır performans olarak sunulmaz.

## 4. Ölçüm sözleşmesi

İlk sürüm tek analiz kapsamındadır. “Sektör” analizdeki sektör ve soru setini ifade eder; bütün pazarın tarandığı iddiası yapılmaz. Mevcut set dar veya marka ağırlıklıysa bu kapsam görünür olmalıdır.

- Sayfa atıf sayısı = o URL'yi kaynak gösteren farklı başarılı `response_id` sayısı. Aynı yanıtta tekrar edilen URL bir kez sayılır.
- Yanıt kapsamı = sayfayı kaynak gösteren yanıtlar / aktif filtrelerdeki değerlendirilebilir başarılı yanıtlar × 100. Kaynaksız başarılı yanıtlar paydaya dahildir; başarısız/simüle/bilinmeyen yöntemli kayıtlar dahil değildir. Payda sıfırsa sonuç null'dır.
- Farklı soru sayısı = ilişkili Response üzerinden bulunan farklı prompt kimlikleri; model sayısı soruları çoğaltmaz.
- Alan adı sayımı, URL sayımlarını toplayarak yapılmaz: aynı yanıtta aynı alana ait üç URL varsa alan adı yanıt sayısı birdir.
- Modeller birlikte seçildiğinde her prompt × model ayrı gözlemdir. Ortak Tavily aramasının modeller arasında paylaşıldığı yöntem açıklamasında belirtilir.
- Varsayılan sıralama: atıf sayısı azalan, farklı soru sayısı azalan, normalize URL artan.
- URL normalizasyonu: sadece HTTP(S), küçük harf hostname, fragment ve bilinen takip parametrelerinin kaldırılması, varsayılan portların temizlenmesi. Path harf büyüklüğü ve anlam taşıyan query korunur; http/https, www veya trailing-slash eşitliği kanıtsız varsayılmaz. Ham URL ayrıca saklanır.
- Sahiplik, doğrulanmış proje/marka alan adlarıyla tam hostname veya subdomain sınırı üzerinden belirlenir. Metin içeren alan adları yanlışlıkla eşleştirilmez.
- “Yanıtta marka anılıyor” ile “kaynak sayfada marka anılıyor” farklı alanlardır. Belirsiz değer false'a çevrilmez.

Gözlenen native platform yanıtları ileride eklenirse ayrı provenance ile tutulur. OpenRouter model slug'ı ChatGPT veya Gemini tüketici uygulamasında yapılmış gözlem gibi etiketlenmez.

## 5. Uygulama adımları

### A. Kanıt ve yöntem sözleşmesi

`llm_analytics_measured.py` içindeki kaynak eşleştirmesini sertleştir. Eşleşmeyen rank, dışarıdan üretilmiş URL ve hatalı kaydı rapor sıralamasına alma. Eski kayıtları stored search_results üzerinden yeniden doğrulayabiliyorsak kullan; doğrulanamayanları unknown olarak ayır. `geo_run` ve gerçek dry-run/mock kökenini API'ye taşı; yalnız `mode=measured` değerini gerçek ölçüm kanıtı sayma. Mock kökeni kalıcı veriden çıkarılamıyorsa yeni koşular için açık işaret ekle; eski veriyi tahmin etme.

Kabul: uydurulmuş URL, simülasyon ve mock veri gerçek kaynak tablosuna giremez. Eski verinin kullanılamadığı durum açıkça görünür.

### B. Tek analiz kaynak raporu API'si

Önerilen uç: `GET /api/v1/analyses/{id}/citation-sources`.

Mevcut analiz erişim kontrolünü kullan; organizasyon yetkisini kontrol etmeden rapor üretme. `GeoRecord.response_id` → Response üzerinden model/prompt bilgisine ulaş. Tek bir backend aggregation servisi Pages, Domains ve export için ortak sayım yapar. Başlangıçta mevcut JSON kayıtlarından hesaplama yeterlidir; yeni tablo/migration zorunlu varsayılmaz.

Yanıt sözleşmesi: `scope`, `methodology`, `coverage`, `summary`, `rows`, `pagination`. Her satır stable page key, URL, domain, ownership, response_count, prompt_count, response_coverage, model listesi ve evidence referanslarını taşır. Filtreleme/sıralama pagination'dan önce yapılır. Yanıt kanıtı detayı da aynı analiz yetkisine tabidir.

Kabul: UI ve CSV aynı filtrelerde aynı sayıları üretir; model filtresi payı ve paydayı birlikte değiştirir; farklı organizasyonun analizi okunamaz.

### C. Ekran ve kanıt detayı

Mevcut CitationsClient ve AnalysisBoundSubpage akışını genişlet. Pages / Domains görünümü, filtreler, tablo, sayfalama, erişilebilir detay paneli ve boş/hata durumlarını ekle. Başarıyla ölçülen ama sıfır kaynak bulunan kayıtları veri hatasından ayır.

Kabul: kullanıcı tek bir sayfanın neden üst sırada olduğunu soruya ve yanıta giderek doğrulayabilir. Sayfa tablosu ile alan adı tablosu kendi tekilleştirme kurallarına uyar.

### D. Fırsat filtresi ve dışa aktarım

Rakip ve hedef marka anılmasını yanıt düzeyinde değerlendir; üçüncü taraf sayfalara kanıt bağlantılı fırsat filtresi ekle. CSV'de provenance ve kapsamı koru. Bu adım otomatik outreach veya mesaj gönderimi içermez.

Kabul: hedef marka bilgisi unknown olan yanıt “markanız eksik” fırsatı sayılmaz; bir kaynakta görünmek nedensellik veya backlink kanıtı diye sunulmaz.

### E. Daha geniş sektör keşfi ve zaman serisi

İlk sürüm sonrası ayrı kapsam: KYC'den sektör/alt sektör/ülke/dil seçimi, düzenlenebilir marka bağımsız soru paneli, sabit prompt_set_version, periyodik ölçümler, karşılaştırılabilir koşular arasında trend. Bunun için yeni ölçüm maliyeti, kota ve saklama tasarımı gerekir. Native platform veri sağlayıcısı entegrasyonu da ayrı bir karardır.

## 6. Doğrulama ve kapsam dışı

Gerekli testler: duplicate URL; aynı alana ait farklı sayfalar; model filtresi paydası; sıfır payda; malformed URL; kaynak-rank uyuşmazlığı; simülasyon/mock/unknown köken; subdomain sahipliği; unknown marka anılması; çapraz organizasyon erişimi; kanıt detayı; filtreli CSV tutarlılığı ve güvenliği. Hedefli backend/API testleri, ilgili frontend testleri ve tip/lint kontrolleri çalıştırılır.

İlk sürümde yok: küresel sektör indeksi, tahmini AI arama hacmi, trafik tahmini, otomatik içerik üretimi, outreach, zaman trendi ve ölçülmemiş native platform rozetleri.

**Önerilen ilk implementasyon dilimi:** A + B + C. Ardından D; E ayrı planlanır. İlk planın uygulama durumu aşağıdaki güncellemede kayıtlıdır.

## 7. Uygulanan ilk sürüm — 2026-09-17

- A–D uygulandı: kanıt doğrulama, dry_run köken kaydı, rapor API’si, Pages/Domains, filtreler, yanıt detayları, fırsat filtresi ve CSV.
- Rapor, GeoRecord ile aynı verinin aslı olan Response.audit üzerinden hesaplanıyor; iki kopya birlikte sayılmıyor.
- Model ve soru kimlikleri Response üzerinden geliyor. geo_run metadatası yeni raporun scope alanında açıklanıyor; GeoOut değiştirilmedi.
- Rakip alan adları kullanıcı tarafından giriliyor; KYC’deki marka isimlerinden domain tahmin edilmiyor.
- Kökeni eksik eski analizler bilinmiyor olarak dışlanıyor. Yeni measured analiz gerekiyor; geçmiş sonuçlar değiştirilmedi.
- Inline [1] veya [1, 2] referansı olmayan kaynaklar sayılmıyor.
- E (geniş sektör keşfi ve trend) bu sürüme dahil değil. Üretime yayın yapılmadı.
- Doğrulama ve kod haritası: [oturum kaydı](sessions/2026-09-17-01.md).
