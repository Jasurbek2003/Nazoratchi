# 5. Nofunksional talablar

## 5.1. Hisob-kitob asoslari (o'lchamlar)

Talablardagi raqamlar quyidagi taxminiy hisoblarga asoslangan. Ular loyiha davomida
haqiqiy o'lchovlar bilan tekshiriladi (17-bo'lim, xavf R-104).

### 5.1.1. Miqyos

| Parametr | Joriy (2026-10) | Maqsad (1 yil) | Zaxira (3x) |
|---|---|---|---|
| Serverlar | 3 (+1 core) | 10 | 30 |
| Loyihalar | 7 ishlayapti + ~15 ko'chirilmagan | 30 | 90 |
| Domenlar | ~20 | 50 | 150 |
| Konteynerlar (jami) | ~60 | 150 | 450 |
| Faol tekshiruvlar (HTTP/TLS/DNS) | 0 | 150 | 450 |
| Foydalanuvchilar | 1–3 | 5 | 15 |

Tizim **maqsad miqyosida** (10 server) hech qanday sozlamasiz, **zaxira miqyosida**
(30 server) esa faqat resurs oshirilishi bilan ishlashi kerak. Arxitektura o'zgarishi talab
qilinmasligi kerak.

### 5.1.2. Ma'lumot oqimi hajmi (zaxira miqyosi: 30 server)

Bir hostdan intervalga ko'ra namunalar soni (7-bo'limdagi katalog asosida, taxminan):

| Guruh | Qatorlar (series) | Interval | Namuna/soniya (1 host) |
|---|---|---|---|
| Tizim (CPU: 8 yadro × 4 rejim + umumiy, load, RAM, swap) | ~60 | 15 s | 4.0 |
| Disk (3 bo'lim × 5 + 2 blok qurilma × 6) | ~27 | 15 s | 1.8 |
| Tarmoq (2 interfeys × 8) | ~16 | 15 s | 1.1 |
| Docker (15 konteyner × 8) | ~120 | 30 s | 4.0 |
| Servislar, jarayonlar, boshqa | ~20 | 30 s | 0.7 |
| **Jami 1 host** | **~243** | | **~11.6** |

30 host × 11.6 ≈ **350 namuna/soniya** → kuniga ≈ **30 million** namuna, yiliga ≈ 11 milliard
(xom). Shu sababli xom ma'lumot qisqa saqlanadi va siyraklashtiriladi (8-bo'lim).

### 5.1.3. Saqlash hajmi bahosi

Asos: 30 host × ~243 qator = **7 290 qator (series)**. Taxminiy yozuv hajmi (TimescaleDB siqishdan
keyin): xom namuna ~12 bayt, agregat yozuv (min/avg/max/count) ~20 bayt.

| Daraja | Saqlash | Yozuv/kun (7 290 qator) | Hajm bahosi (30 host, hamma metrika) |
|---|---|---|---|
| Xom (15–30 s) | 14 kun | 30.2 mln | 30.2M × 14 × 12 B ≈ 5.1 GB |
| 1 daqiqalik agregat | 90 kun | 7 290 × 1 440 = 10.5 mln | 10.5M × 90 × 20 B ≈ 18.9 GB |
| 5 daqiqalik agregat | 1 yil | 7 290 × 288 = 2.1 mln | 2.1M × 365 × 20 B ≈ 15.3 GB |
| 1 soatlik agregat | 3 yil | 7 290 × 24 = 0.175 mln | 0.175M × 1 095 × 20 B ≈ 3.8 GB |
| **Jami (yuqori chegara)** | | | **≈ 43 GB** |

Maqsad miqyosida (10 server) yuqori chegara ≈ **14 GB**. Agregat darajalar uchun faqat
**muhim metrikalar** (CPU, RAM, disk, tarmoq umumiy) saqlansa, agregat hajmi taxminan 3 baravar
kamayadi va maqsad miqyosidagi kutilgan jami hajm **~6 GB** bo'ladi.

> Muhim: siqish koeffitsiyenti (12 va 20 bayt) TimescaleDB hujjatlaridagi tipik natijaga
> asoslangan taxmin edi. **P-02 o'lchovi** (sintetik, lekin real naqshli: 120 qator × 24 soat × 15 s =
> 691 200 namuna): siqilmagan 91 bayt, siqilgan **6.9 bayt/namuna** (13× siqish), ya'ni xom
> ma'lumot uchun taxmin konservativ. Real ma'lumot (spayklar, ko'p kasr xonali) sekinroq siqilishi
> mumkin; F1 oxirida haqiqiy hajm bilan qayta o'lchanadi (xavf R-104).

## 5.2. PRF — Unumdorlik

| ID | Talab | Ust. | Faza | O'lchash usuli |
|---|---|---|---|---|
| NFR-PRF-001 | **Qabul qilish kechikishi.** Ingest endpoint so'rovga 95-persentilda ≤ 300 ms, 99-persentilda ≤ 1 s javob beradi (30 host, har 15 s) | M | F1 | Yuklama testi (`k6`/`locust`), 30 virtual agent |
| NFR-PRF-002 | **Ma'lumot yangiligi (freshness).** Agent namunani yig'ganidan boshlab panelda ko'rinishigacha ≤ 30 soniya (95-persentil) | M | F1 | Test namunaning vaqt tamg'asi va paneldagi vaqtini solishtirish |
| NFR-PRF-003 | **Alert hisoblash kechikishi.** Shart paydo bo'lgandan alert yaratilgunga qadar: `for` davomiyligi + ≤ 30 s | M | F1 | Sun'iy hodisa bilan stopwatch |
| NFR-PRF-004 | **Bildirishnoma yetkazilishi.** Incident yaratilgandan Telegram'da paydo bo'lishigacha ≤ 10 soniya (95-persentil), kanal ishlaganda | M | F1 | Sinov alertlari, 50 ta o'lchov |
| NFR-PRF-005 | **Dashboard yuklanishi.** Bosh sahifa to'liq ko'rinishi ≤ 2 s (10 server, 30 loyiha, tezkor internet, kesh bilan ≤ 1 s) | M | F1 | Lighthouse / qo'lda o'lchov |
| NFR-PRF-006 | **Grafik so'rovlari.** 24 soatlik grafik ≤ 1 s; 7 kunlik ≤ 1.5 s; 30 kunlik ≤ 2 s; 90 kunlik ≤ 3 s (tegishli agregat jadvaldan) | M | F1 | So'rov vaqtini yozish, 100 ta o'lchov medianasi |
| NFR-PRF-007 | **Agent resurslari.** O'rtacha CPU ≤ 1%, maksimal RAM ≤ 60 MB, disk yozuvi ≤ 5 MB/soat (bufer ishlamaganda) | M | F1 | 24 soatlik o'lchov (`pidstat`) |
| NFR-PRF-008 | **Core resurslari.** 10 server yuklamasida core (backend + baza + redis) o'rtacha ≤ 40% CPU va ≤ 1.5 GB RAM, 2 vCPU/4 GB da | M | F1 | Yuklama testi |
| NFR-PRF-009 | **Frontend hajmi.** Dastlabki yuklanadigan JS+CSS ≤ 400 KB (gzip); grafik kutubxonasi kechiktirib yuklanadi (lazy) | S | F2 | Build hisoboti |
| NFR-PRF-010 | **Faol tekshiruvlar sig'imi.** Bitta prober jarayoni 450 tekshiruvni (60 s interval) bir vaqtda, 1 vCPU ning ≤ 30% bilan bajaradi | S | F2 | Sun'iy 450 tekshiruv |

## 5.3. CAP — Sig'im va masshtablash

| ID | Talab | Ust. | Faza | O'lchash usuli |
|---|---|---|---|---|
| NFR-CAP-001 | **Serverlar soni.** 30 serverni qo'llab-quvvatlaydi (5.1.1); 100 serverga o'tish uchun faqat gorizontal bo'lmagan masshtablash (resurs oshirish) yetarli | M | F2 | Yuklama testi 30 va 60 virtual agent bilan |
| NFR-CAP-002 | **Saqlash byudjeti.** Maqsad miqyosida (10 server) jami baza hajmi ≤ 25 GB (1 yil; kutilgan 6–14 GB, 5.1.3); 3 yilda ≤ 60 GB | M | F2 | `pg_total_relation_size` kuzatuvi |
| NFR-CAP-003 | **Indeks va so'rov rejalari.** Hech bir asosiy so'rov (7 ta kritik, 8.8-bo'lim) ketma-ket skanerlashga (seq scan) tushmaydi | S | F2 | `EXPLAIN` tekshiruvi testda |
| NFR-CAP-004 | **Namuna shakli bilan masshtab.** Yangi metrika turi qo'shish bazaga sxema o'zgartirishni talab qilmaydi (uzun/tor jadval modeli) | M | F1 | Yangi metrika kodsiz/migratsiyasiz qabul qilinadi |
| NFR-CAP-005 | **Gorizontal ingest.** Ingest xizmati holatsiz (stateless): bir nechta nusxa ishlashi mumkin | C | F3 | Ikkita nusxa bilan test |

## 5.4. REL — Ishonchlilik va chidamlilik

| ID | Talab | Ust. | Faza | O'lchash usuli |
|---|---|---|---|---|
| NFR-REL-001 | **Core mavjudligi.** Oylik ≥ 99.5% (≈ 3.6 soat/oy ruxsat etilgan to'xtash) | M | F2 | Tashqi watchdog hisobi |
| NFR-REL-002 | **Ma'lumot yo'qolmasligi.** Core 15 daqiqagacha mavjud bo'lmasa ham agent buferi tufayli grafikda bo'shliq (> 1 namuna) yo'q | M | F1 | Core to'xtatilib qayta yoqilgan test |
| NFR-REL-003 | **Idempotent qabul.** Bir paket takror yuborilsa, ma'lumot ikkilanmaydi (paket ID va namuna kaliti bo'yicha) | M | F1 | Bir paketni 3 marta yuborib hisoblash |
| NFR-REL-004 | **Yumshoq degradatsiya.** Baza vaqtincha o'chsa, core navbatga (Redis) yozadi (15 daqiqagacha), UI esa "ma'lumot kechikmoqda" ko'rsatadi; alert hisoblash to'xtamasdan kechiktiriladi | S | F2 | Bazani to'xtatib sinash |
| NFR-REL-005 | **Bildirishnoma ishonchliligi.** Telegram API vaqtincha ishlamasa, 24 soat ichida kamida 99.9% xabar yetkaziladi (qayta urinish va zaxira kanal bilan) | M | F2 | Sinov (Telegram'ni bloklab) |
| NFR-REL-006 | **Tiklash vaqti (RTO).** Nazoratchi'ni to'liq yangi serverga zaxiradan tiklash ≤ 1 soat | M | F2 | Yiliga 1 marta sinov (drill) |
| NFR-REL-007 | **Tiklash nuqtasi (RPO).** Nazoratchi sozlamalari va reyestr uchun ≤ 24 soat; vaqt qatorlari uchun yo'qotish qabul qilinadi (agent qayta yuboradi) | M | F1 | Zaxira jadvali |
| NFR-REL-008 | **Vaqt va vaqt zonalari.** Ichkarida hamma vaqt UTC (`timestamptz`); UI da foydalanuvchi zonasi (standart `Asia/Tashkent`) | M | F1 | Kod ko'rigi va test |
| NFR-REL-009 | **Qayta ishga tushishga chidamlilik.** Core konteynerlari `restart: unless-stopped`; server reboot'dan keyin 3 daqiqada hammasi ishlaydi, qo'lda aralashuvsiz | M | F1 | Reboot sinovi |
| NFR-REL-010 | **Soxta alertlarni kamaytirish.** Tekshiruvlar tasdiqlash qoidasi (3 ketma-ket xato) va gisterezis bilan; oylik soxta alert ulushi ≤ 5% | M | F2 | 90 kunlik qo'lda baholash |

## 5.5. SEC — Xavfsizlik (qisqa; batafsili 14-bo'limda)

| ID | Talab | Ust. | Faza | O'lchash usuli |
|---|---|---|---|---|
| NFR-SEC-001 | **Barcha aloqa shifrlangan.** Brauzer↔core, agent↔core, core↔Telegram: TLS 1.2+; agent sertifikatni tekshiradi (o'zini-o'zi imzolagan sertifikat bo'lsa, qotirilgan (pinned) CA) | M | F1 | `testssl.sh` / agent testi |
| NFR-SEC-002 | **Maxfiy ma'lumotni saqlash.** Telegram bot tokeni, SMTP paroli, tekshiruv sarlavhalari: bazada shifrlangan (AES-256-GCM, kalit `.env`/fayl orqali, bazada emas) | M | F1 | Bazadan to'g'ridan-to'g'ri o'qib ko'rish: ochiq matn yo'q |
| NFR-SEC-003 | **Tokenlar.** Agent/API tokenlari kamida 256 bit tasodifiy; bazada faqat SHA-256 xesh | M | F1 | Kod ko'rigi |
| NFR-SEC-004 | **Eng kam huquq.** Agent `root`siz; Docker o'qish proksisi; backend bazaga cheklangan foydalanuvchi bilan | M | F1 | Konfiguratsiya tekshiruvi |
| NFR-SEC-005 | **Veb-zaifliklardan himoya.** OWASP ASVS 4.0 L1 talablari to'liq, L2 ning asosiy qismi (autentifikatsiya, sessiya, kirishni tekshirish, XSS/CSRF/SQLi) | M | F2 | Xavfsizlik tekshiruv ro'yxati va avtomatik skanerlash (ZAP) |
| NFR-SEC-006 | **Bog'liqliklar xavfsizligi.** `pip-audit`, `npm audit`, `govulncheck` CI da; kritik zaiflik bo'lsa build to'xtaydi | S | F2 | CI hisoboti |
| NFR-SEC-007 | **Tezlik cheklovi.** Ingest: token bo'yicha daqiqada ≤ 30 so'rov; login: 5 xato/15 daqiqa; API: foydalanuvchi bo'yicha 120 so'rov/daqiqa | M | F1 | Test |
| NFR-SEC-008 | **Loglarda maxfiy ma'lumot yo'q.** Token, parol, `Authorization` sarlavhalari, `.env` qiymatlari hech qachon logga yozilmaydi | M | F1 | Log namunalarini avtomatik skanerlash (regex) |
| NFR-SEC-009 | **Xavfsizlik sarlavhalari.** `Strict-Transport-Security`, `Content-Security-Policy`, `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options: DENY` | M | F1 | `securityheaders.com` darajasi ≥ A |
| NFR-SEC-010 | **O'z zaxirasi shifrlanishi.** Nazoratchi'ning o'z zaxirasi Telegram'ga yuborilishidan oldin `age` bilan shifrlanadi; ochiq kalit core'da, maxfiy kalit faqat Owner'da (parol menejeri) | M | F1 | Telegram'dagi fayl shifrlangan; maxfiy kalitsiz ochilmaydi |
| NFR-SEC-011 | **Ma'muriy kirishni cheklash.** `/admin` va sozlamalar uchun ixtiyoriy IP ro'yxati (allowlist) va 2FA | S | F2 | Konfiguratsiya testi |
| NFR-SEC-012 | **Imzolangan yangilanishlar.** Agent yangilanishi faqat CI maxfiy kaliti bilan imzolangan va agent binariga joylangan ochiq kalit bilan tekshirilgan bo'lsa qabul qilinadi; imzo kaliti core serverda saqlanmaydi; versiya pasaytirish (downgrade) rad etiladi (14.5.4) | M | F1 | Buzuq/imzosiz binar bilan yangilash rad etiladi (test) |

## 5.6. USA — Qulaylik va til

| ID | Talab | Ust. | Faza | O'lchash usuli |
|---|---|---|---|---|
| NFR-USA-001 | **Til.** Standart til — o'zbek (lotin, to'g'ri imlo: o', g', sh, ch, ng); qo'shimcha: rus, ingliz. Barcha matnlar tarjima fayllarida; kodda qattiq yozilgan matn yo'q | M | F1 | Kod ko'rigi, til almashtirish testi |
| NFR-USA-002 | **Mobil moslashuv.** Interfeys 360 px kenglikdan boshlab to'liq ishlaydi; asosiy ekranlar (dashboard, incidentlar) telefonda qulay | M | F1 | Qurilma/emulyator tekshiruvi |
| NFR-USA-003 | **Foydalanish imkoniyati (a11y).** WCAG 2.1 AA: kontrast, klaviatura bilan boshqarish, rang bilan birga belgi/matn (rang ko'rlik uchun) | S | F2 | `axe` skaneri, qo'lda tekshiruv |
| NFR-USA-004 | **Tushunarli xabarlar.** Har xato va alert xabari: nima bo'ldi, qayerda, nima qilish kerak — texnik jargonsiz emas, lekin aniq | M | F1 | Namuna xabarlarni ko'rib chiqish |
| NFR-USA-005 | **Vaqt formati.** UI da vaqt `Asia/Tashkent` zonasida, `2026-10-22 14:35` formatida; nisbiy vaqt ("5 daqiqa oldin") tooltip bilan aniq vaqtni ko'rsatadi | S | F2 | Ko'rik |
| NFR-USA-006 | **Birinchi sozlash vaqti.** Yangi o'rnatilgan tizimda birinchi serverni qo'shib, birinchi alertni olishgacha ≤ 15 daqiqa | S | F1 | Yangi odam bilan sinov |
| NFR-USA-007 | **Ranglar semantikasi.** Yashil — sog'lom, sariq — ogohlantirish, to'q sariq — yuqori, qizil — kritik, kulrang — noma'lum/pauza. Hammasi ikkala mavzuda | M | F1 | Dizayn tekshiruvi |

## 5.7. MNT — Qo'llab-quvvatlash va sifat

| ID | Talab | Ust. | Faza | O'lchash usuli |
|---|---|---|---|---|
| NFR-MNT-001 | **Test qamrovi.** Biznes mantiq (alert hisoblash, bashorat, bostirish, zaxira tahlili) uchun qator qamrovi ≥ 85%; umumiy ≥ 70% | M | F2 | `coverage` hisoboti CI da |
| NFR-MNT-002 | **Statik tahlil.** Python: `ruff` + `mypy` (qat'iy rejim asosiy modullarda); TypeScript: `strict`; Go: `go vet` + `staticcheck`. CI da xato bo'lsa birlashtirib bo'lmaydi | M | F1 | CI |
| NFR-MNT-003 | **CI/CD.** Har commit'da: lint, test, build; main shoxda — konteyner image'lari (versiya tegi bilan) chiqariladi | M | F1 | Pipeline |
| NFR-MNT-004 | **Sozlama muhit o'zgaruvchilari orqali.** 12-factor: kod ichida qattiq yozilgan sozlama yo'q; `.env.example` to'liq | M | F1 | Kod ko'rigi |
| NFR-MNT-005 | **Strukturalangan loglar.** JSON log (`ts`, `level`, `msg`, `request_id`, `component`); sathlari sozlanadi | M | F1 | Log namunasi |
| NFR-MNT-006 | **Migratsiyalar.** Sxema o'zgarishi faqat versiyalangan migratsiya orqali; har migratsiya testda ikki marta (oldinga/orqaga) o'tadi | M | F1 | CI |
| NFR-MNT-007 | **Hujjatlar.** `README`, o'rnatish yo'riqnomasi, arxitektura qisqacha, runbook'lar, API OpenAPI sxemasi (avtomatik) | M | F2 | Hujjat ro'yxati |
| NFR-MNT-008 | **Modulli tuzilma.** Backend `apps/` bo'yicha mustaqil modullarga bo'lingan (6-bo'lim); modullar orasidagi bog'liqlik bir yo'nalishli | S | F1 | Import grafi tekshiruvi |
| NFR-MNT-009 | **Versiyalash.** Semantik versiyalash; agent va core o'rtasida protokol versiyasi (`/v1/`); eski agent kamida 2 ta minor versiya davomida ishlaydi | M | F1 | Moslik testi |

## 5.8. POR — Ko'chma va o'rnatish

| ID | Talab | Ust. | Faza | O'lchash usuli |
|---|---|---|---|---|
| NFR-POR-001 | **Core — Docker Compose.** Bitta `docker compose up -d` bilan butun core ko'tariladi | M | F1 | Toza serverda sinov |
| NFR-POR-002 | **Agent platformalari.** Linux amd64 va arm64 (Ubuntu 22.04, 24.04); statik binar, tashqi bog'liqliksiz | M | F1 | Ikkala arxitekturada sinov |
| NFR-POR-003 | **Provayderga bog'liq emas.** Hech qanday bulut provayderning xizmatiga (GCP, AWS) bog'lanmaydi; Contabo, Hetzner, boshqa VPS da bir xil ishlaydi (eski serverdagi GCP agentlari bilan bog'liq saboq) | M | F1 | Kod ko'rigi |
| NFR-POR-004 | **Minimal xost talablari.** Core: 2 vCPU, 4 GB RAM, 40 GB SSD; Ubuntu 24.04 + Docker; qo'shimcha dasturlar talab qilinmaydi | M | F1 | Spetsifikatsiya |
| NFR-POR-005 | **Oflayn o'rnatish imkoniyati.** Agent binari core'ning o'zidan yuklab olinadi (GitHub'ga bog'liq emas) | S | F2 | Tashqi internetsiz sinov |

## 5.9. OBS — Kuzatiluvchanlik (tizimning o'zi)

| ID | Talab | Ust. | Faza | O'lchash usuli |
|---|---|---|---|---|
| NFR-OBS-001 | **Ichki metrikalar.** Core Prometheus formatida `/metrics` (faqat ichki tarmoq/token bilan) beradi: so'rovlar, xatolar, navbat, alert hisoblash vaqti | S | F2 | `curl /metrics` |
| NFR-OBS-002 | **So'rov kuzatuvi.** Har HTTP so'rovga `request_id`; xato javobida u ko'rsatiladi | S | F2 | Test |
| NFR-OBS-003 | **Xato to'plash.** Kutilmagan istisnolar (exception) `ERROR` darajasida, to'liq stek bilan logga; ixtiyoriy Sentry (o'z-hosting) | C | F3 | Log namunasi |

## 5.10. DAT — Ma'lumot va maxfiylik

| ID | Talab | Ust. | Faza | O'lchash usuli |
|---|---|---|---|---|
| NFR-DAT-001 | **Yig'ilmaydigan ma'lumot.** Agent: fayl mazmuni, ilova ma'lumoti, foydalanuvchi shaxsiy ma'lumoti, buyruq argumentlari (parol bo'lishi mumkin), muhit o'zgaruvchilari — yig'maydi. Jarayon nomi faqat bajariladigan fayl nomi (argumentsiz) | M | F1 | Kod ko'rigi, paket namunasi tekshiruvi |
| NFR-DAT-002 | **Saqlash siyosati hujjatlashtirilgan.** Retention qiymatlari sozlamalarda ko'rinadi va o'zgartiriladi | S | F2 | Sozlamalar sahifasi |
| NFR-DAT-003 | **Ma'lumot eksporti.** Egasi barcha ma'lumotini (reyestr, incident, audit) standart formatda (JSON/CSV) yuklab oladi | S | F2 | Eksport sinovi |
| NFR-DAT-004 | **Mijoz ma'lumoti.** Mijozga (masalan, wmg.uz) faqat o'z loyihasi ma'lumoti ko'rsatiladi (FR-AUTH-005); serverning umumiy tuzilmasi yashirin | C | F3 | Cheklangan viewer testi |

## 5.11. Nofunksional talablar xulosasi

| Toifa | Soni |
|---|---|
| PRF | 10 |
| CAP | 5 |
| REL | 10 |
| SEC | 12 |
| USA | 7 |
| MNT | 9 |
| POR | 5 |
| OBS | 3 |
| DAT | 4 |
| **Jami NFR** | **65** |
