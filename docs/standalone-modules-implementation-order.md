# Standalone modules — implementation order (tracker)

**Branch:** `feat/standalone-modules-phase-a`  
**Detailed steps:** Cursor canvas `standalone-modules-action-plan.canvas.tsx`  
**Task checklist:** `standalone-modules-progress.canvas.tsx`

## Tamamlanan işler — özet rapor (Oct 2026)

Genel odaklı liste; teknik görev numaraları tracker tablosunda.

- **Ürün mimarisi netleştirildi** — Her modülün kendi “başlat → bekle → sonuç al” döngüsü var; bir modülün çalışması diğerini otomatik tetiklemiyor. Kararlar ve faz planı yazıldı, çift kayıtlar temizlendi, ilerleme canvas’ları güncellendi.
- **Kalıcı marka profili** — Marka bilgisi artık tek bir analize kilitli değil; profil oluşturma, okuma, güncelleme ve isteğe bağlı yeniden çıkarma (URL’den) ayrı akışlar. Eski analizlerdeki profil verisi için toplu eşleme script’i ve “oluştur vs. arka planda çıkar” kuralları dokümante edildi.
- **Yapay zeka görünürlüğü (GEO) tek başına** — Tam analiz paketi olmadan, seçilen prompt’larla GEO ölçümü başlatılıp sonuçları izlenebiliyor.
- **Arama sonuçları (SERP) görünürlüğü tek başına** — SERP ölçümü ayrı başlatılıp kontrol edilebiliyor (canlı sağlayıcı doğrulaması operasyon/kredi ile kaldı).
- **Ortak “arka plan işi” takibi** — KYC çıkarma, GEO, SERP gibi farklı iş türleri için tek tip durum sorgusu; modül bazlı detay rotaları da duruyor.
- **İş kuyruğu hızlandırma** — Redis yalnızca “sıradaki iş kim?” için; asıl durum ve sonuçlar veritabanında. Analiz, modül ve site denetimi kuyrukları bu modele geçirildi; Redis yoksa eski davranış korunuyor. Takılı kalan modül işleri için yeniden kuyruğa alma runbook’u var.
- **Paket analiz esnekliği** — Klasik “tek POST /analyses” hâlâ var; isteğe bağlı adım seçimi ve mevcut marka profiline bağlama eklendi.
- **Backlink fırsat listesi şeffaflığı** — “Markadan bahsedip link vermeyen sayfalar” artık istenirse belirli GEO/SERP çalışmalarına göre filtreleniyor; domain genelinde sessiz tarama zorunlu değil.
- **Site denetimi bağımsız giriş** — SEO projesi altındaki denetim akışına ek, modül odaklı başlatma/okuma uç noktası.
- **Geçiş planı** — Eski analiz girişi ile yeni modül girişlerinin birlikte yaşayacağı dönem ve sonrası için zaman çizelgesi tablosu.
- **Modül sihirbazı (ilk sürüm)** — Arayüzde URL → profil → GEO çalıştırması → sonuç; arka planda iki ayrı API çağrısı.
- **Backlink sağlayıcı hazırlığı** — DataForSEO backlinks için kod yuvası ve açma anahtarı; gerçek API çekimi henüz kapalı (lisans/endpoint sonrası).

## Sprint sequence

Execute in this order (action-plan item numbers in parentheses):

1. ~~**Tracker sync (4)**~~ — progress canvas + this doc reflect repo reality.
2. ~~**rq-3 (5–8)**~~ — `module_runs` LPUSH + worker pop `queue:module` (ops below).
3. ~~**mod-4 API (9–12)**~~ — `POST/GET /api/v1/ai-visibility/runs` + `GET …/geo`.
4. ~~**Module poll (16–17)**~~ — `GET /api/v1/background-jobs/{id}` + `ModuleRunOut` fields.
5. ~~**mod-3 API (13–14)**~~ — `POST/GET /api/v1/serp/runs` + `GET …/checks`. Item **15** (DataForSEO live smoke) when credits available.
6. ~~**Doc cleanup (1–3)**~~ — plan dedupe, ADR-53 citation renumber, progress canvas sync.
7. ~~**18+ backlog**~~ — see status snapshot; ops smoke (15) remains.

## Status snapshot (Oct 2026)

| ID | Status | Notes |
|----|--------|--------|
| mod-0 … mod-6 | Done | Phase A + B run APIs + worker kinds |
| mod-7 | Done | Explicit `analysis_ids` / `module_run_ids` on backlink opportunities |
| mod-8 | Done | `POST /analyses` `steps` + `brand_context_id`; migration `0029` |
| mod-9 | Done | `/ai-visibility/wizard` + `frontend/lib/moduleRunsApi.ts` |
| mod-10 | Partial | `app/backlink/dataforseo.py` seam; live API fetch not wired |
| mod-11 | Done | `/api/v1/site-audit/runs` |
| mod-12 | Done | Deprecation table in `standalone-modules-plan.md` |
| mod-18–19 | Done | Backfill script + KYC create/extract policy doc |
| rq-0, rq-2, rq-5 | Done | ADR-54, `broker.py`, site audit Redis hint |
| rq-1, rq-3, rq-4 | Done | Redis dispatch |
| Item 15 | Ops | SERP live smoke when credits available |

## Yapılacaklar (To do)

Standalone modül kodundan bağımsız veya operasyonla kapanan maddeler. Altyapı detayı: [jira-geo-worker-replicas.md](./jira-geo-worker-replicas.md) · canvas `geo-worker-replicas.canvas.tsx`.

### Ürün ve operasyon

- **SERP canlı doğrulama** — Staging’de gerçek arama sağlayıcısı ile uçtan uca deneme (API kredisi gerekir).
- **Backlink canlı DataForSEO** — Lisans ve endpoint netleşince gerçek backlink verisi çekimi (`BACKLINK_DATAFORSEO_ENABLED` sonrası API wiring).

### Altyapı (infra)

- **Worker kapasitesi araştırması** — Tek worker havuzunda GEO/modül/analiz işlerinin ne kadar sürede tıkandığını ölç; hedef eşzamanlı kapasite (N) tanımla. *(inf-wr-1)*
- **Replica sayısı kararı** — Maliyet / fayda ile kaç worker kopyası çalışacağına karar ver; sadece kuyruk adaleti değil yatay kapasite gerekir. *(inf-wr-2)*
- **Worker scale-out** — Compose/prod’da birden fazla worker (ve gerekirse ayrı site-audit worker) süreçleri, deploy ve operasyon runbook’u. *(inf-wr-3)*
- **Çok kiracılı staging smoke** — İki org’un işlerinin paralel ilerlediğini staging’de doğrula; bir müşterinin kuyruğu diğerini bloklamamalı. *(inf-wr-4)*
- **Redis / Valkey prod sertleştirme** — Kuyruk için kalıcılık (AOF), bellek limitleri ve izleme; kesinti sonrası “queued ama işlenmiyor” senaryosu için runbook (modül + site audit redispatch).
- **Site denetimi worker’ının prod’da açılması** — API ve kuyruk hazır; feature flag açık ortamda crawl worker’ının gerçekten drain ettiğini doğrula.

**Not:** GEO worker replica initiative, standalone modules sprint’inden **ayrı** epic (Infrastructure); fair-FIFO tek başına cross-tenant blokajı çözmez.

## Ops — re-dispatch queued module runs (item 8)

If Postgres shows `module_runs.status = queued` but workers never pick them up (Redis was down at enqueue, or `REDIS_URL` was added later):

```bash
cd backend && uv run python ../scripts/redispatch_module_runs.py --dry-run
cd backend && uv run python ../scripts/redispatch_module_runs.py
```

KYC extract (`POST …/kyc/profiles/{id}/extract`) calls `notify_module_run_enqueued` after commit when Redis is configured. Without Redis, behavior is unchanged: worker uses `claim_next_module_run` only.

## Ops — backfill BrandContext from analyses (item 18)

```bash
cd backend && uv run python ../scripts/backfill_brand_contexts.py --dry-run
cd backend && uv run python ../scripts/backfill_brand_contexts.py
```

Re-runnable: only rows with `brand_context_id IS NULL` and mappable `kyc` are processed.

## Jira

- Workstream **standalone** — `mod-*` / `rq-*` (bu doc ve plan).
- Workstream **infra** — `inf-wr-*`, labels `infra`, `worker-replicas` ([import CSV](./jira-geo-worker-replicas-import.csv)).
