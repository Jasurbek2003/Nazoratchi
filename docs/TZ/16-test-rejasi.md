# 16. Test rejasi va qabul mezonlari

## 16.1. Strategiya

Monitoring tizimida eng xavfli nuqson — **"jim nosozlik"**: tizim ishlayotgandek ko'rinadi,
lekin alert chiqarmaydi. Shu sababli test strategiyasi oddiy funksional tekshiruvdan tashqari
quyidagilarga alohida e'tibor beradi:

1. **Alert to'g'riligi** (to'g'ri vaqtda, to'g'ri qamrovda, takrorlanmasdan).
2. **Ma'lumot to'liqligi** (uzilishda yo'qolmaslik, takrorlanmaslik).
3. **Nosozlik holatida xatti-harakat** (baza, Redis, tarmoq, Telegram, soat).
4. **Xavfsizlik chegaralari** (SSRF, RBAC, token, imzo).

### 16.1.1. Test piramidasi

| Daraja | Ulushi | Vositalar | Qachon ishga tushadi |
|---|---|---|---|
| Birlik (unit) | ~65% | `pytest`, `vitest`, `go test` | Har commit (CI) |
| Integratsiya | ~25% | `pytest` + haqiqiy Timescale/Redis (Docker), `testcontainers` | Har PR (CI) |
| E2E (brauzer + agent + core) | ~8% | Playwright; agent simulyatori | Har PR (asosiy oqimlar), kechasi (to'liq) |
| Yuklama, chaos, xavfsizlik | ~2% (lekin muhim) | `k6`, qo'lda stsenariylar, ZAP | Har reliz oldidan |

### 16.1.2. Qamrov maqsadlari

| Komponent | Qator qamrovi |
|---|---|
| Alert dvigateli (`alerts`) | ≥ 90% |
| Zaxira tahlili (`backups`), DNS holat tasnifi (`probes`) | ≥ 90% |
| Ingest (`ingest`), Kripto (`core.crypto`) | ≥ 90% |
| Qolgan backend | ≥ 70% |
| Agent kollektorlari | ≥ 75% (fixtures bilan) |
| Frontend (mantiq va komponentlar) | ≥ 60% |
| Umumiy backend | ≥ 80% (NFR-MNT-001: mantiq uchun ≥ 85%) |

## 16.2. Birlik testlari (majburiy ro'yxat)

### 16.2.1. Alert dvigateli

| № | Test | Kutilgan |
|---|---|---|
| T-U-ALR-01 | `threshold`: qiymat chegaradan o'tdi, `for` o'tmadi | holat `pending`, xabar yo'q |
| T-U-ALR-02 | `threshold`: `for` o'tdi | `firing`, incident ochildi |
| T-U-ALR-03 | `firing` → shart yolg'on → `resolve_after` o'tmaguncha | `resolving`, xabar yo'q |
| T-U-ALR-04 | `resolving` ichida shart yana rost | `firing` ga qaytadi, yangi xabar yo'q |
| T-U-ALR-05 | `absent`: oxirgi namuna `max_age_s` dan eski | Rost |
| T-U-ALR-06 | `rate`: counter qayta boshlandi (qiymat kamaydi) | Noto'g'ri musbat yo'q (reset hisobga olinadi) |
| T-U-ALR-07 | `forecast`: chiziqli o'sish | `eta` ±5% aniqlikda |
| T-U-ALR-08 | `forecast`: R² < 0.5 | Hisoblanmaydi (alert yo'q) |
| T-U-ALR-09 | `forecast`: band < 50% | Hisoblanmaydi |
| T-U-ALR-10 | `and`/`or`/`not` birlashmalari (chuqurlik 3) | To'g'ri mantiq jadvali |
| T-U-ALR-11 | Bostirish: host `down` → shu hostdagi konteyner alerti | Alohida xabar yo'q, incident ro'yxatida |
| T-U-ALR-12 | Bostirish tugagach shart hamon rost | Yangi alert chiqadi |
| T-U-ALR-13 | Silence matcher: `server="main-2"`, `severity!="critical"` | Faqat mos kelganlar bostiriladi |
| T-U-ALR-14 | Maintenance oynasi tugashi | Hal bo'lmagan alertlar yuboriladi |
| T-U-ALR-15 | Titrash: 1 soatda 6 o'tish | "Beqaror" belgisi, xabarlar kamaytirildi |
| T-U-ALR-16 | Guruhlash: 60 s ichida 5 alert | 1 xabar |
| T-U-ALR-17 | Incident: xuddi shu `scope_key` bo'yicha ikkinchi alert | Mavjud incidentga qo'shiladi |
| T-U-ALR-18 | Incident yopilishi: hamma alert `ok` + 60 s | `resolved` |
| T-U-ALR-19 | Qayta ishga tushish: holat bazadan tiklanadi | Takroriy "yangi" xabar yo'q |
| T-U-ALR-20 | Takroriy eslatma jadvali (`critical`) | 30 daq, 6 marta, keyin 2 soat |
| T-U-ALR-21 | Sokin soatlar: `warning` | Xabar kechiktirildi, 07:00 yig'ma |
| T-U-ALR-22 | Vaqt zonasi: sokin soat Asia/Tashkent bo'yicha (UTC+5) | To'g'ri chegara |
| T-U-ALR-23 | Ikkita evaluator nusxasi (advisory lock) | Faqat bittasi ishlaydi |

### 16.2.2. Zaxira tahlili

| № | Test | Kutilgan |
|---|---|---|
| T-U-BKP-01 | `state.json` ok, fayl mos | `ok` |
| T-U-BKP-02 | `state.json` ok, fayl yo'q | `suspicious` + `backup_state_mismatch` |
| T-U-BKP-03 | `state.json` yo'q, fayl bor (skaner) | Skaner manbasi bilan `ok`/`stale` |
| T-U-BKP-04 | Yosh 25.9 s / 26.1 s chegara | `ok` / `stale` |
| T-U-BKP-05 | Hajm median×0.49 / ×0.51 | `suspicious` / `ok` |
| T-U-BKP-06 | Tarix 7 dan kam | Faqat `size_floor_bytes` tekshiriladi |
| T-U-BKP-07 | `.tmp` fayl | Hisobga olinmaydi |
| T-U-BKP-08 | Offsite: nom mos, hajm mos | `in_sync` |
| T-U-BKP-09 | Offsite: hajm farqli, 29 daq / 31 daq | Alert yo'q / AL-078 |
| T-U-BKP-10 | Offsite'da ko'proq fayl (`--delete` yo'q) | Normal |
| T-U-BKP-11 | Drill muddati: 75 / 91 / 101 kun | `ok` / `due` / `overdue` |
| T-U-BKP-12 | Bir nechta muammo birga | Hammasi ro'yxat, rang — eng og'iri |
| T-U-BKP-13 | `baseline_reset` | Median tarixi qayta boshlanadi |

### 16.2.3. DNS va TLS tasnifi

| № | Test | Kutilgan |
|---|---|---|
| T-U-DNS-01 | NS ham, resolverlar ham kutilgan IP | `match` |
| T-U-DNS-02 | NS yangi, resolverlar eski | `propagating`, alert yo'q |
| T-U-DNS-03 | NS eski (kutilmagan) 10 daq+ | `mismatch` |
| T-U-DNS-04 | A yozuvi `retired_ips` ichida | `retired_ip` (AL-063) |
| T-U-DNS-05 | NXDOMAIN | `nxdomain`, `critical` |
| T-U-DNS-06 | NS to'g'ri, resolver 30 daq+ boshqa | `resolver_disagree` |
| T-U-TLS-01 | Qolgan kun 22 / 21 / 8 / 7 / 4 / 3 / 0 / −1 | Chegaralar bo'yicha to'g'ri daraja |
| T-U-TLS-02 | SAN da hostname yo'q | `hostname_ok = false` |
| T-U-TLS-03 | Wildcard SAN (`*.avlo.ai`) `nazar.avlo.ai` ga | Mos |
| T-U-TLS-04 | Agent yangi sertifikat, prober eski | "reload qilinmagan" (AL-061) |

### 16.2.4. Ingest va ma'lumot

| № | Test | Kutilgan |
|---|---|---|
| T-U-ING-01 | To'g'ri paket | `200`, namunalar yozildi, `series_latest` yangilandi |
| T-U-ING-02 | Takroriy `batch_id` | `200 duplicate=true`, ikkilanmagan |
| T-U-ING-03 | Bir xil `(series_id, time)` ikki marta | `ON CONFLICT DO NOTHING`, xato yo'q |
| T-U-ING-04 | Agent soati 11 daqiqa orqada (`sent_at` va namunalar birga) | Butun paket farqqa surildi, `clock_skew` |
| T-U-ING-05 | Qiymat diapazondan tashqari (`cpu_busy_percent = 140`) | Namuna rad etildi, hisoblagich oshdi |
| T-U-ING-06 | `NaN`/`Inf` qiymat | Rad etildi |
| T-U-ING-07 | Kardinallik: 1 001-series | Rad etildi, `agent_series_dropped` signali |
| T-U-ING-08 | Token noto'g'ri / bekor | `401` |
| T-U-ING-09 | Paket > 1 MB | `413` |
| T-U-ING-10 | gzip buzuq | `400` |
| T-U-ING-11 | `labels` da taqiqlangan kalit (masalan, `url`) | Rad etildi |
| T-U-ING-12 | Core 14 daqiqa o'chib qaytdi: bufer namunasi 14 daqiqa eski | O'z vaqti bilan yoziladi, `clock_skew` yo'q |
| T-U-ING-13 | 1 soatdan eski yoki 5 daqiqa kelajakdagi namuna | Rad etildi |
| T-U-ING-14 | `sent_at` yo'q yoki noto'g'ri | `400 validation_error` |
| T-U-DAT-01 | Agregat: `metric_1m` yig'indisi xom bilan mos | `sum/n` teng |
| T-U-DAT-02 | Ierarxik agregat 5m = 5 ta 1m dan | Mos |
| T-U-DAT-03 | So'rov marshrutizatsiyasi (oraliq → jadval) | 8.4.3 jadvaliga mos |
| T-U-DAT-04 | Retention: 15 kunlik xom | O'chirilgan, agregat saqlangan |

### 16.2.5. Kripto va xavfsizlik birlik testlari

| № | Test | Kutilgan |
|---|---|---|
| T-U-SEC-01 | AES-GCM: shifrlash → ochish | Teng; `nonce` har safar farqli |
| T-U-SEC-02 | AES-GCM: `aad` boshqa kanal ID | Ochish xato |
| T-U-SEC-03 | Kalit rotatsiyasi | Hamma maydon yangi kalit bilan ochiladi |
| T-U-SEC-04 | SSRF filtri: `127.0.0.1`, `10.x`, `169.254.169.254`, `::1`, `localhost` | Rad etildi |
| T-U-SEC-05 | SSRF: DNS rebinding (birinchi ochiq IP, ikkinchi ichki) | Aniqlangan IP ga ulaniladi; ichki rad |
| T-U-SEC-06 | SSRF: yo'naltirish ichki IP ga | Rad etildi |
| T-U-SEC-07 | Login timing: mavjud/mavjud emas login | Vaqt farqi ≤ 20 ms (o'lchovda) |
| T-U-SEC-08 | Log maskalash: token, parol | Logda ko'rinmaydi |
| T-U-SEC-09 | RBAC matritsasi (3.2) barcha endpointlar | Mos `200/403` |
| T-U-SEC-10 | Viewer: boshqa loyiha ID | `404` |
| T-U-SEC-11 | Agent yangilanishi: imzo mos emas | Rad etiladi. **S11:** `agent/internal/update` birlik testlari (begona kalit, almashtirilgan binar/`VERSION`, orqaga qaytarish, buzilgan staged, symlink) va `deploy/agent/test/update-in-container.sh` e2e (haqiqiy `minisign`, rollback, fallback) |
| T-U-SEC-12 | Agent yangilanishi: versiya pasayishi | Rad etiladi |

### 16.2.6. Agent birlik testlari

| № | Test | Kutilgan |
|---|---|---|
| T-U-AGT-01 | `/proc/stat` fixtures bo'yicha CPU foizi | Ma'lum javobga teng |
| T-U-AGT-02 | `/proc/meminfo` bo'yicha `mem_used_percent` | `free` formulasiga mos |
| T-U-AGT-03 | `statfs` bo'yicha `fs_used_percent` | `df` ga mos (±0.1%) |
| T-U-AGT-04 | `tmpfs/overlay/squashfs` e'tiborsiz | Metrika yaratilmaydi |
| T-U-AGT-05 | `/proc/diskstats` farqlari → IOPS, await | To'g'ri |
| T-U-AGT-06 | `/proc/net/dev` → bayt/s; counter reset | Manfiy tezlik yo'q |
| T-U-AGT-07 | Docker API javobi (fixtures) → metrikalar | To'g'ri; `compose` labellari |
| T-U-AGT-08 | `state.json` o'qish: ok / fail / buzuq JSON | Xato bilan yiqilmaydi, `unknown` |
| T-U-AGT-09 | Kollektor panic | Qolgan kollektorlar ishlaydi (FR-AGT-014) |
| T-U-AGT-10 | Bufer: to'lganda eng eskisini o'chirish | 20 MB chegarasi |
| T-U-AGT-11 | Sender: 5xx → backoff jadvali | 1,2,4,8,16,30 s ± jitter |
| T-U-AGT-12 | Konfig xato (noto'g'ri YAML) | Ishga tushmaydi, aniq xabar |
| T-U-AGT-13 | Token faylidagi ruxsat 0644 | Ogohlantirish / rad |

## 16.3. Integratsiya testlari

| № | Test | Kutilgan |
|---|---|---|
| T-I-01 | Agent simulyatori → `ingest` → bazada metrika → API `query` | Qiymatlar mos, vaqt mos |
| T-I-02 | `heartbeat` to'xtashi → evaluator → incident → Telegram (soxta server) | Xabar 10 s ichida (NFR-PRF-004) |
| T-I-03 | HTTP probe soxta serverga: 200 → 500 → 200 | `up → down → up`, tasdiqlash qoidasi (3 xato) |
| T-I-04 | TLS probe: sinov sertifikatlari (1/3/7/21/40 kun) | Mos alertlar |
| T-I-05 | DNS probe: sinov DNS server (A yozuvini o'zgartirish) | Holatlar 11.4.2 ga mos |
| T-I-06 | Zaxira: `appctl` bilan haqiqiy `backup` (test loyiha) → agent → core | Kartada ko'rinadi |
| T-I-07 | Telegram webhook: `ack` callback | Incident `acknowledged`, audit yozuvi |
| T-I-08 | Telegram callback noto'g'ri imzo / begona chat | Hech narsa bo'lmaydi, `200` qaytadi |
| T-I-09 | SSE: yangi incident → brauzer | ≤ 5 s ichida UI'da |
| T-I-10 | Sokin soatlar + `critical` | Darrov keladi |
| T-I-11 | Retention vazifasi | Eski ma'lumot o'chirildi, agregat saqlandi |
| T-I-12 | Reyestr import/eksport aylanishi | Bir xil natija (diff yo'q) |
| T-I-13 | Heartbeat endpoint (`/hb/<token>`) ok/fail/yo'q | AL-048 / AL-047 |
| T-I-14 | Maintenance oynasi + incident | Xabar yo'q → oyna tugagach yuboriladi |
| T-I-15 | Kanal xatosi → email zaxira | Email yuborildi, AL-086 |

## 16.4. End-to-end (E2E) stsenariylar

Brauzer (Playwright) va haqiqiy agent (test konteynerida):

| № | Stsenariy | Qadamlar | Kutilgan |
|---|---|---|---|
| T-E-01 | UC-01: yangi server qo'shish | Panelda yaratish → buyruqni test konteynerida ishga tushirish | Server "Onlayn" ≤ 60 s |
| T-E-02 | UC-02: server o'chdi | Test agent konteynerini to'xtatish | 2–3 daq ichida incident; Telegram (soxta) xabari |
| T-E-03 | UC-03: disk bashorati | Sun'iy o'sish (generator) | AL-022 keyin AL-023 |
| T-E-04 | UC-04: zaxira muvaffaqiyatsiz | `state.json: fail` | AL-070; xabarda xato matni |
| T-E-05 | UC-07/11.4.4: kesib o'tish | Soxta DNS'da A yozuvini o'zgartirish | "tarqaldi" xabari |
| T-E-06 | UC-08: maintenance | Oyna yaratish → alert chiqarish | Xabar yo'q → oyna tugagach keladi |
| T-E-07 | UC-09: incident bilan ishlash | Ack → izoh → hal bo'lishi | Vaqt chizig'i to'liq |
| T-E-08 | UC-10: yangi loyiha qo'shish | Forma → avtomatik tekshiruvlar | 1 daqiqada tekshiruvlar ishlaydi |
| T-E-09 | UC-11: restore drill kiritish | Forma | Kartada yangilandi, eslatma qayta boshlandi |
| T-E-10 | UC-12: watchdog | Core'ni to'xtatish | 5–6 daqiqada watchdog xabari |
| T-E-11 | Kirish + 2FA + chiqish | | Sessiya xavfsizligi (cookie xususiyatlari) |
| T-E-12 | Viewer cheklovi | | Faqat o'z loyihasi |

## 16.5. Unumdorlik (yuklama) testi

### 16.5.1. Vositalar va ma'lumot

- Agent simulyatori (Go yoki `k6`): har virtual agent haqiqiy paket hajmi/ketma-ketligi bilan
  (7.4 katalogi, ~243 qator/host) har 15 s yuboradi.
- Ma'lumot generatori (16.9): real naqshlar (kunlik tsikl, spayk, sekin o'sish).

### 16.5.2. Stsenariylar

| № | Stsenariy | Parametrlar | Muvaffaqiyat mezoni |
|---|---|---|---|
| T-P-01 | Barqaror yuklama (maqsad miqyosi) | 10 agent, 1 soat | Ingest p95 ≤ 300 ms (NFR-PRF-001), xato 0%, CPU ≤ 40% |
| T-P-02 | Barqaror yuklama (zaxira miqyosi) | 30 agent, 4 soat | p95 ≤ 300 ms, p99 ≤ 1 s, navbat o'smaydi |
| T-P-03 | Chegara: 60 agent | 60 agent, 30 daqiqa | Qachon buzilishini aniqlash (bilish uchun, mezon yo'q) |
| T-P-04 | Spayk: 30 agent bir vaqtda qayta ulandi (core qaytdi, buferdan yuboradi) | 30 × 15 daq. bufer | Hammasi 5 daqiqada qabul qilindi, bo'shliq yo'q |
| T-P-05 | 7 kunlik tarix grafigi so'rovi | 30 host, 90 kunlik ma'lumot | p95 ≤ 2 s (NFR-PRF-006) |
| T-P-06 | Dashboard (50 loyiha, 10 server) | 20 parallel foydalanuvchi | LCP ≤ 2 s, API p95 ≤ 500 ms |
| T-P-07 | 450 faol tekshiruv | 60 s interval, 24 soat | Prober CPU ≤ 30% (NFR-PRF-010); kechikish ≤ 5 s |
| T-P-08 | Alert hisoblash vaqti | 89 qoida × 30 host | Bir tick ≤ 3 s (interval 15 s) |
| T-P-09 | Baza hajmi o'sishi | 30 agent × 3 kun | Bashorat (5.1.3) bilan ±30% |
| T-P-10 | Agent resurslari | 24 soat | CPU ≤ 1%, RAM ≤ 60 MB (NFR-PRF-007) |

T-P-09 natijasi bilan 5.1.3 dagi siqish koeffitsiyentlari tuzatiladi (xavf R-104).

## 16.6. Chaos va nosozlik testlari

Maqsad: nosozlikda tizim yolg'on xabar bermasligi va ma'lumotni yo'qotmasligi.

| № | Nosozlik | Kutilgan xatti-harakat |
|---|---|---|
| T-C-01 | `db` konteynerini 5 daqiqaga to'xtatish | `/healthz` 503; ingest navbatga yoziladi; tiklangach ma'lumot yo'qolmaydi; UI "kechikmoqda" |
| T-C-02 | `redis` ni to'xtatish | Ingest ishlaydi (kesh yo'qolsa ham); SSE → polling; Celery vazifalari kechikadi, tiklangach bajariladi |
| T-C-03 | `evaluator` jarayonini `kill -9` | Docker avto-restart; holat bazadan tiklandi; takroriy xabar yo'q; AL-084 vaqtincha |
| T-C-04 | `prober` ni to'xtatish | AL-085 3 daqiqada; boshqa funksiyalar ishlaydi |
| T-C-05 | Telegram API'ga chiqishni bloklash | Qayta urinish; email zaxira; AL-086 |
| T-C-06 | Core ↔ agent tarmog'ini uzish (15 daq) | Agent buferlaydi; tiklangach yuboradi; core "aloqa yo'q" belgilaydi |
| T-C-07 | Core soatini 10 daqiqa siljitish | Namunalar `clock_skew` bilan; qoidalar buzilmaydi |
| T-C-08 | Agent soatini 1 soat siljitish | Namunalar core vaqti bilan almashtiriladi; AL-007 |
| T-C-09 | Core diskini to'ldirish (95%) | AL-021; yozishda xato — tizim yiqilmaydi, retention yordam beradi |
| T-C-10 | Agentga `SIGKILL` | systemd 5 s da qayta ishga tushiradi; AL-002 kechikish < 2 daq bo'lsa chiqmaydi |
| T-C-11 | Agent diskini to'ldirish | Bufer yozolmaydi, xotira buferi; yiqilmaydi |
| T-C-12 | Docker daemon to'xtashi (kuzatiladigan hostda) | `docker` kollektori xato, boshqalar ishlaydi (FR-AGT-014) |
| T-C-13 | Chiqish tarmog'i sekin (3 s kechikish, 5% yo'qotish) | Agent backoff; ma'lumot yo'qolmaydi |
| T-C-14 | 2 ta evaluator nusxasi ataylab | Bittasi "leader" (advisory lock) |
| T-C-15 | Retention paytida yuklama | Ingest p95 buzilmaydi |
| T-C-16 | Core reboot (to'liq server) | 3 daqiqada hammasi tiklandi (T-DEP-02) |
| T-C-17 | Buzuq paket oqimi (fuzz) | `400`; yiqilish yo'q; log hajmi o'smaydi |

## 16.7. Xavfsizlik testlari

14.13 dagi ro'yxatdan tashqari:

| № | Test | Kutilgan |
|---|---|---|
| T-S-01 | OWASP ZAP (faol skaner) — autentifikatsiyalangan | Jiddiy/yuqori topilma yo'q |
| T-S-02 | Token taxmin qilish (tezlik chegarasi ostida 10 000 urinish) | Hammasi `401`, chegara ishladi |
| T-S-03 | Bruteforce login | 5 urinishdan keyin blok |
| T-S-04 | Sessiya: cookie xususiyatlari | `HttpOnly; Secure; SameSite=Lax; __Host-` |
| T-S-05 | CSRF (cookie bilan POST, token yo'q) | `403` |
| T-S-06 | XSS: loyiha nomiga `<script>`, izohga `<img onerror>` | Escaped / tozalangan |
| T-S-07 | SQLi: filtr parametrlariga payload | Xato yoki bo'sh natija; so'rov buzilmaydi |
| T-S-08 | IDOR: boshqa viewer loyihasi ID si | `404` |
| T-S-09 | Agent: buzuq imzoli yangilanish | Rad etildi, voqea yuborildi |
| T-S-10 | Agent: `docker run` urinishi (proksi orqali) | `403` |
| T-S-11 | `db`/`redis` tashqaridan | `nmap`: yopiq |
| T-S-12 | TLS: `testssl.sh` | A daraja |
| T-S-13 | Zaxira fayllarida maxfiy ma'lumot | Nazoratchi zaxirasida `master.key` yo'q |
| T-S-14 | Maxfiy qiymatlar API javoblarida | Hech qachon to'liq |

## 16.8. Qabul sinovlari (UAT) — umumiy yig'ma

Buyurtmachi (Owner) tomonidan o'tkaziladi. Tizim **qabul qilingan** deb hisoblanadi, agar
quyidagilar bajarilsa:

| № | Mezon | Tekshiruv |
|---|---|---|
| UAT-01 | Barcha M (Must) talablar bajarilgan | Traceability matritsasi (16.12), har qatorda "o'tdi" |
| UAT-02 | F1 uchun belgilangan testlarning 100% muvaffaqiyatli | CI + qo'lda |
| UAT-03 | 3 ta haqiqiy server (S-00, S-01, S-02) 14 kun uzluksiz kuzatuvda | Ma'lumot bo'shliqlari yo'q; agent resurs mezonlari |
| UAT-04 | Haqiqiy sinov: serverlardan birini (test uchun) ataylab to'xtatish | AL-001 ≤ 2 daqiqada, Telegram'da |
| UAT-05 | Haqiqiy sinov: zaxira cron'ini 27 soat to'xtatish (yoki vaqt siljitish) | AL-068 |
| UAT-06 | Haqiqiy sinov: sinov sertifikat/domen | Muddat ogohlantirishi |
| UAT-07 | 14 kunlik soxta alertlar ulushi | ≤ 5% (qo'lda belgilanadi) |
| UAT-08 | Barcha seed loyihalar uchun tekshiruvlar ishlayapti | 11.2.5 jadvaliga mos |
| UAT-09 | Birinchi restore drill'lar kamida 2 ta loyiha uchun bajarilgan va qayd etilgan | Kartada ko'rinadi |
| UAT-10 | Nazoratchi'ni tiklash mashqi (15.9) RTO ichida | Vaqt qayd etilgan |
| UAT-11 | Hujjatlar: README, runbook'lar (18.2), o'rnatish yo'riqnomasi | Mavjud va tekshirilgan |
| UAT-12 | Xavfsizlik ro'yxati (14.13) | Barcha bandlar o'tdi |

## 16.9. Sinov ma'lumotlari generatori

Generator — alohida kichik dastur (`tools/simulator`, F1 S10 da `simulate.py`: stdlib, token ro'yxati bo'yicha
virtual agentlar, p50/p95/p99 va mezon tekshiruvi), konfiguratsiya fayli bo'yicha virtual
hostlarni yaratadi.

**Holat (2026-10-28, F1 S10):** xavfsizlik, chaos va unumdorlik testlarining bajarilgan va kutilayotgan qismi
`docs/sinov/B13-natijalar.md` da. Avtomatik: `backend/tests/test_security.py` (T-S-04..08, 14; S-09, S-10),
`backend/tests/test_chaos.py` (T-C-02, 14, 17); real: T-C-01 va T-P-01 (qisqartirilgan). Haqiqiy serverni talab
qiladigan bandlar (ZAP, testssl, T-C-03..13, T-P-02..10) UAT oldidan S-01 da bajariladi.

| Naqsh | Tavsifi |
|---|---|
| `steady` | Doimiy CPU ~10–20%, shovqin bilan |
| `daily` | Kunlik tsikl (kunduzi yuqori, kechasi past) |
| `spike` | Qisqa spayk (2–3 daqiqa, 95%) — alert **bermasligi** kerak (`for` testi) |
| `sustained_high` | 12 daqiqa 93% — alert **berishi** kerak |
| `mem_leak` | RAM sekin o'sadi (+1%/soat) → 90% ga yetadi |
| `disk_growth` | Disk +2 GB/kun → forecast |
| `flapping` | Konteyner har 2 daqiqada tushib-ko'tariladi |
| `crash_loop` | Restart soni tez oshadi |
| `backup_ok` / `backup_fail` / `backup_small` / `backup_stale` | `state.json` va fayllar yaratadi |
| `silent` | Heartbeat to'xtaydi (host o'chdi) |
| `clock_skew` | Agent vaqti siljigan |
| `high_cardinality` | Ko'p noyob label (kardinallik chegarasi testi) |

Generator deterministik (`--seed`) bo'lishi kerak: bir xil seed — bir xil natija (testlar
takrorlanishi uchun).

## 16.10. Nuqsonlar va reliz mezonlari

### 16.10.1. Nuqson darajalari

| Daraja | Ta'rif | Misol | Reaksiya |
|---|---|---|---|
| S1 — kritik | Alert yo'qoladi, ma'lumot yo'qoladi, xavfsizlik teshigi, tizim ishlamaydi | Server o'chganda alert chiqmaydi | Reliz bloklanadi; zudlik bilan tuzatish |
| S2 — yuqori | Asosiy funksiya noto'g'ri, lekin aylanib o'tish mumkin | Disk bashorati 2 baravar xato | Reliz oldidan tuzatiladi |
| S3 — o'rta | Qulaylik, kosmetik, kam uchraydigan | Tarjima xatosi | Keyingi relizga ruxsat |
| S4 — past | Takomillashtirish | Rang nuanslari | Ro'yxatda |

### 16.10.2. Reliz chiqish mezonlari (exit criteria)

- S1 va S2 nuqsonlar: 0 ta ochiq.
- F-bosqich uchun belgilangan hamma test o'tgan; CI yashil.
- Yuklama testi (T-P-01, T-P-02, T-P-10) mezonlari bajarilgan.
- Xavfsizlik ro'yxati (14.13) o'tgan.
- Zaxira va tiklash sinovi bajarilgan (T-DEP-05).
- Hujjatlar yangilangan; o'zgarishlar jurnali (CHANGELOG).

### 16.10.3. Regressiya

- Har S1/S2 nuqsonga **regressiya testi** yoziladi (test avval muvaffaqiyatsiz, tuzatishdan keyin o'tadi).
- Har yangi alert qoidasi uchun kamida 2 ta test (rost va yolg'on holat).
- Har o'tgan hodisadan (post-mortem) chiqqan qoida — avtomatik testga aylanadi.

## 16.11. Tugallangan deb hisoblash (Definition of Done)

Har vazifa (user story / talab) tugallangan hisoblanadi, agar:

1. Kod yozilgan va ko'rib chiqilgan (kamida 1 ko'rik; yolg'iz ishlasa — o'z-o'zini ko'rib chiqish
   ro'yxati bo'yicha, 17.6).
2. Birlik/integratsiya testlari yozilgan va o'tgan; qamrov kamaymagan.
3. Statik tahlil toza (`ruff`, `mypy`, `eslint`, `tsc`, `go vet`).
4. Xavfsizlik jihati ko'rib chiqilgan (kirish tekshiruvi, ruxsat, log).
5. Migratsiya (bo'lsa) qaytariladigan va sinovdan o'tgan.
6. Matnlar `uz` (va `ru`, `en`) tarjimasi qo'shilgan.
7. Hujjat (API sxemasi avtomatik, runbook, TZ da o'zgarish) yangilangan.
8. Tegishli talab ID si PR tavsifida ko'rsatilgan.
9. Staging/dev da qo'lda tekshirilgan.

## 16.12. Izlanuvchanlik matritsasi (traceability) — modul bo'yicha

To'liq "talab → test" jadvali loyiha davomida avtomatik hosil qilinadi (har testda
`@requirement("FR-XXX-NNN")` belgisi; skript hisobot yaratadi). Quyida modul darajasidagi
xulosa:

| Modul | Talablar | Asosiy testlar |
|---|---|---|
| REG | FR-REG-001..012 | T-I-12, T-E-08, T-U-SEC-10 |
| HST | FR-HST-001..017 | T-U-AGT-01..06, T-P-10, T-E-02, T-E-03 |
| AGT | FR-AGT-001..014 | T-U-AGT-*, T-E-01, T-C-06, T-C-10, T-C-11, T-DEP-06 |
| DKR | FR-DKR-001..010 | T-U-AGT-07, T-SVC-02, T-SVC-09 |
| SVC | FR-SVC-001..006 | T-SVC-03, T-I-13 |
| HTTP | FR-HTTP-001..010 | T-I-03, T-SVC-01, T-P-07 |
| TLS | FR-TLS-001..008 | T-U-TLS-*, T-I-04, T-SVC-04 |
| DNS | FR-DNS-001..009 | T-U-DNS-*, T-I-05, T-E-05, T-SVC-05, T-SVC-06 |
| BKP | FR-BKP-001..020 | T-U-BKP-*, T-BKP-01..10, T-E-04, T-E-09 |
| ALR | FR-ALR-001..020 | T-U-ALR-*, T-ALR-01..13, T-I-02, T-I-14 |
| NTF | FR-NTF-001..009 | T-I-07, T-I-08, T-I-10, T-I-15, T-ALR-09, T-ALR-11 |
| UI | FR-UI-001..019 | T-UI-01..10, T-E-11, T-E-12 |
| AUTH | FR-AUTH-001..008 | T-S-02..05, T-E-11, T-U-SEC-07 |
| AUD | FR-AUD-001..004 | T-U-SEC-09, T-I-07 |
| INT | FR-INT-001..006 | T-I-06, T-I-13, T-BKP-01 |
| SYS | FR-SYS-001..006 | T-E-10, T-C-01..04, T-DEP-05 |
| NFR-PRF | NFR-PRF-* | T-P-01..10 |
| NFR-REL | NFR-REL-* | T-C-*, T-DEP-02, T-DEP-08 |
| NFR-SEC | NFR-SEC-* | T-S-*, T-U-SEC-* |
| NFR-USA | NFR-USA-* | T-UI-02..04, T-UI-07 |
| NFR-MNT | NFR-MNT-* | CI hisobotlari (qamrov, lint) |
