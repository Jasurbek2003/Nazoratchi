# P-02 — Protokol prototipi va TimescaleDB sinovi

Sana: 2026-10-26 · Muhit: TimescaleDB 2.17.2 (PostgreSQL 16.6), Python 3.13, Windows 11 (agent)
Reja: F0, P-02 (TZ 17.3.1). Chiqish mezoni: "Metrika grafikda; agregatlar ishlaydi; R-102 baholandi".

## Xulosa

**Mezonlar bajarildi, R-102 hal bo'ldi.** Ierarxik va `JOIN` li agregatlar, siqish va siyosatlar
kutilganidek ishlaydi; zaxira reja (oddiy partitsiya + Celery) kerak emas. Sinov uch ta TZ
nomuvofiqligini ochdi (pastda) va TZ shunga ko'ra v1.3 ga yangilandi.

## Nima qilindi

| Qism | Joyi | Tarkibi |
|---|---|---|
| Ingest | `backend/apps/ingest/` | `POST /ingest/v1/metrics`: Bearer token (xesh), gzip, 1 MB chegara, zip-bomba himoyasi, sxema/diapazon/belgi tekshiruvi, kardinallik chegarasi (1000), `unnest` bilan paketli yozuv, idempotent |
| Ma'lumot modeli | `backend/apps/{registry,metrics}/` | `Server`, `AgentToken`, `Series`, `SeriesLatest`; `metric_samples` gipertablitsasi va agregatlar migratsiyada (`0002_timescale.py`) |
| So'rov | `backend/apps/metrics/query.py` | Oraliqqa qarab xom/1m/5m/1h tanlash (TZ 8.4.3), `max_points` bo'yicha siyraklash |
| Grafik | `backend/apps/metrics/proto/index.html` | `/proto/` (faqat `DEBUG`): server, metrika, oraliq, 5 s yangilanish, uzilgan joyda chiziq tutashmaydi |
| Agent | `prototype/agent/` | Python/`psutil`: cpu, load, ram, swap, disk, tarmoq tezligi, uptime; gzip yuborish; xotirada 15 daqiqalik bufer; backoff 1-2-4-8-16-30 s |

Testlar: backend 47 ta (qamrov 95%), agent 22 ta (qamrov 87%).

## R-102 natijalari

| Savol | Natija |
|---|---|
| Ierarxik agregat (1m → 5m → 1h) ishlaydimi? | **Ha.** 3 soat × 15 s = 720 namuna: xom, 1m, 5m, 1h yig'indilari va sonlari bir xil |
| `rollup=false` qatorlarni agregatdan chiqarish (`JOIN series`) | **Ha.** `metric_1m` `JOIN ... WHERE rollup` bilan yaratiladi, 5m/1h unga ierarxik bog'lanadi; faqat `rollup` seriyalar materiallashadi |
| Gipertablitsa, siqish (2 kun), retention (14 kun / 90 / 365 / 1095), agregat yangilash siyosatlari | **Ha.** Ishlar `timescaledb_information.jobs` da: 1 siqish, 4 retention, 3 yangilash |
| Migratsiya (`atomic = False`, `CREATE EXTENSION`) | **Ha.** `migrate` va qaytarish (`migrate metrics 0001`) ishlaydi |
| Siqilgan bo'lakka `ON CONFLICT DO NOTHING` | **Dublikat yaratadi** (41 → 82). TZ 8.4.1 taxmini tasdiqlandi, chora ingest'da (pastda) |
| Siqilgan bo'lakdan `DELETE` | **Cheklangan:** `max_tuples_decompressed_per_dml_transaction` = 100 000. Eski ma'lumot faqat retention bilan o'chadi |
| Saqlash hajmi | **6.9 bayt/namuna** siqilgan (siqilmagan 91; 13× siqish). Namuna: 120 qator × 24 soat × 15 s. TZ taxmini 12 bayt edi |

Eslatma: hajm o'lchovi sintetik ma'lumotda (foizlar 1 kasr xonali, bayt hisoblagichlari butun, tezliklar
shovqinli). Real ma'lumot sekinroq siqilishi mumkin; F1 oxirida qayta o'lchanadi (R-104).

## Uchidan-uchiga sinov (shu kompyuterda)

- Agent (5 s oraliq, 30 paket × 26 namuna) → ingest → grafik: **ishladi**, namunalar rad etilmadi.
- **Core o'chib qaytishi (NFR-REL-002):** agent 4 paketni buferda ushladi (xato `WinError 10061`),
  core qaytgach hammasini tartib bilan yubordi. Bazada ketma-ket namunalar orasidagi eng katta farq
  **3.001 s** (agent oralig'i 3 s): bo'shliq yo'q.

## TZ nomuvofiqliklari va ularning yechimi (TZ v1.3 da)

1. **Soat siljishi qoidasi buferni buzardi.** TZ 6.10: `|t − now| > 10 daqiqa` bo'lsa namuna vaqti
   core vaqti bilan almashtiriladi. Lekin FR-AGT-007 agent buferini 15 daqiqa ushlaydi, ya'ni core 12
   daqiqa o'chib qaytsa, kechikkan haqiqiy namunalar "soat siljishi" deb hisoblanib, barchasi bitta
   vaqtga yozilardi. **Yechim:** siljish `sent_at` (agent soati, har yuborishda yangilanadi) bilan
   aniqlanadi; siljigan bo'lsa butun paket farqqa suriladi, aks holda namuna vaqti saqlanadi. 1 soatdan
   eski va 1 daqiqadan ilgari namunalar rad etiladi. `sent_at` majburiy.
2. **Log maskalash regexi tokenni yopmasdi.** TZ 14.9 dagi regex `Authorization: Bearer agt_…` da
   faqat "Bearer" ni yopib, tokenning o'zini logda qoldirgan. **Yechim:** `Bearer`/`Basic` dan keyingi
   qiymat ham yopiladi (`backend/apps/core/logging.py`, testlar bilan).
3. **Siqilgan bo'lak va takror paket.** Taxmin (8.4.1) tasdiqlandi, lekin uni kafolatlovchi qoida TZ da
   yo'q edi. **Yechim:** ingest 1 soatdan eski namunani yozmaydi (`MAX_SAMPLE_AGE_S`); xarakterlovchi
   test (`test_duplicate_into_compressed_chunk_is_not_deduplicated`) TimescaleDB yangilanganda
   xatti-harakat o'zgarsa yiqiladi.

## Ma'lum cheklovlar (keyingi ishlar)

- Prototip so'rov endpointlari (`/proto/`, `/api/v1/…`) autentifikatsiyasiz va faqat `DEBUG` da ochiq;
  prod'da 404. Autentifikatsiya B1 da.
- Enroll oqimi yo'q: token `manage.py create_server` bilan beriladi (B3 da).
- Agent buferi xotirada (F1 Go agentida diskda, 20 MB). Agent qayta ishga tushsa bufer yo'qoladi.
- Agregatlar `materialized_only` (standart): oxirgi ≥ 1 daqiqa agregatda ko'rinmaydi. Marshrutizatsiya
  agregatni faqat 6 soatdan uzun oraliqlarda ishlatgani uchun grafikka ta'sir qilmaydi.
- `uuid` v4 (TZ 8.1 v7 talab qiladi; Python 3.13 da yo'q), B1 da almashtiriladi.
- Yuklama (T-P-01/02) va hajm (T-P-09) o'lchovlari F1 da, Go agent bilan.

## Qayta ishlatish

```bash
docker compose -f deploy/docker-compose.dev.yml up -d
cd backend && uv run python manage.py migrate
uv run python manage.py create_server demo-pc          # tokenni bir marta ko'rsatadi
uv run python manage.py runserver 127.0.0.1:8000 --noreload
cd ../prototype/agent
NAZORATCHI_TOKEN=agt_... uv run python -m proto_agent --interval 5   # keyin http://127.0.0.1:8000/proto/
```
