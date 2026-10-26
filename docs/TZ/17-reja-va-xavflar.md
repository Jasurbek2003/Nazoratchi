# 17. Loyiha rejasi, resurslar va xavflar

## 17.1. Yondashuv

- **Iterativ (qisqa sikllar).** 2 haftalik sprintlar; har sprint oxirida ishlaydigan natija va
  qisqa demo (Owner bilan).
- **Vertikal kesimlar.** Avval "yupqa, lekin to'liq" yo'l (agent → core → alert → Telegram),
  keyin kengaytirish. Birinchi haftalarda Telegram'ga haqiqiy alert kelishi kerak.
- **Eng katta xavfni erta yo'qotish.** Protokol, Timescale agregatlari va `appctl` o'zgartirishlari
  F0 da sinab ko'riladi.
- **Rollar.** Owner (mahsulot egasi, qabul qiluvchi); Dasturchi(lar) (backend/agent/frontend);
  Operator (sinov va ekspluatatsiya). Kichik jamoada bir kishi bir necha rolni bajaradi.

## 17.2. Fazalar

| Faza | Maqsad | Asosiy natija | Chiqish mezoni |
|---|---|---|---|
| **F0 — Tayyorgarlik** | Texnik xavflarni kamaytirish, poydevor | Repo + CI; Python prototip agent va minimal ingest; `appctl` o'zgartirishlari (E-01..E-03); Timescale agregatlari sinovi | Prototipda 1 server metrikasi grafikda ko'rinadi; `appctl backup` `state.json` yozadi |
| **F1 — MVP** | Eng muhim ehtiyojni yopish: server o'chsa, disk to'lsa, sayt tushsa, zaxira buzilsa, sertifikat tugasa — Telegram'da xabar | 4–5-bo'limlardagi F1 talablar (18.7); 32 ta F1 alert; asosiy panel | UAT-01..UAT-12 (16.8) |
| **F2 — Kengaytirilgan** | To'liqlik va qulaylik | F2 talablar: 2FA, hisobotlar, kengaytirilgan zaxira/drill, cut-over yordamchisi, qoidalar UI, ru/en, staging va yuklama testlari | F2 testlari; soxta alert ≤ 5% (90 kun) |
| **F3 — Yetuklik** | Qo'shimcha imkoniyatlar | Viewer cheklovi, status sahifa, ko'p lokatsiyali tekshiruv, avto-drill, eskalatsiya, supply-chain | F3 testlari |

## 17.3. Ish paketlari va baho (kishi-kun)

Baho — bir tajribali dasturchi uchun taxminiy, ±30%. Kishi-kun = 1 ta to'liq samarali ish kuni
(uchrashuv, kod ko'rigi, nosozlik tuzatish ichida).

### 17.3.1. F0 — Tayyorgarlik (7.5 kun)

| ID | Ish | Kun | Natija |
|---|---|---|---|
| E-01 | `appctl`: `state.json`, `_run.json` (10.3.1–10.3.3) | 1.0 | Zaxira natijasi mashinada o'qiladi |
| E-02 | `appctl`: `list --json`, `status --json` (18.1) | 1.0 | JSON chiqish (bajarildi 2026-10-26) |
| E-03 | `setup.sh`/cron: heartbeat chaqiruvi (10.3.5, 9.14) | 0.5 | Cron signal yuboradi (bajarildi 2026-10-26) |
| P-01 | Repozitoriy, CI skeleti (lint, test), `docker-compose.dev.yml` | 2.0 | Yashil CI |
| P-02 | Protokol prototipi: Python agent (`psutil`) + minimal ingest + Timescale agregat sinovi | 3.0 | Metrika grafikda; agregatlar ishlaydi; R-102 baholandi |

### 17.3.2. F1 — MVP (80 kun)

| ID | Ish paketi | Tarkibi | Kun |
|---|---|---|---|
| B1 | Core skeleti | Django loyiha, sozlamalar, modellar (8-bo'lim asosiy), migratsiyalar, foydalanuvchi/autentifikatsiya, audit asosi, Docker | 5 |
| B2 | Reyestr | Server/Loyiha/Domen CRUD, seed, port tekshiruvi, arxiv | 4 |
| B3 | Ingest | Enroll, metrika qabul qilish, series kesh, `COPY`, `series_latest`, heartbeat, tezlik chegarasi | 4 |
| B4 | Metrika so'rovlari | Query API, agregat marshrutizatsiyasi, caggs, retention | 3 |
| B5a | Agent: tizim | Go: skelet, konfig, scheduler, sender, bufer; CPU/RAM/disk/net kollektorlari | 6 |
| B5b | Agent: Docker | Docker API (proksi orqali), konteyner holati, compose bog'lash | 3 |
| B5c | Agent: systemd/backup/certs | systemd, zaxira skaneri (`state.json`), sertifikat skaneri | 3 |
| B5d | Agent: o'rnatish | `install.sh`, systemd unit, imzo tekshiruvi (o'rnatish), enroll, uninstall | 3 |
| B6 | Prober | HTTP/TCP/TLS/DNS tekshiruvlari, tasdiqlash qoidasi, SSRF filtri | 6 |
| B7 | Alert dvigateli | Qoida modeli, shart turlari, holat mashinasi, incident, bostirish, silence, F1 qoidalar to'plami (32) | 7 |
| B8 | Bildirishnoma | Telegram (xabar, tugmalar, webhook), email zaxira, qayta urinish, shablonlar | 4 |
| B9 | Frontend (F1) | Uskuna, auth, Dashboard, serverlar, server sahifasi, loyihalar, loyiha sahifasi, zaxiralar, domenlar, incidentlar, maintenance (oddiy), sozlamalar (kanallar) | 14 |
| B10 | Zaxira monitoringi | Holat qoidalari, yosh/hajm/offsite (1-daraja), zaxira kartasi | 4 |
| B11 | O'zini kuzatish | `/healthz`, evaluator heartbeat, watchdog, o'z zaxirasi | 3 |
| B12 | Deploy va hujjat | Compose, nginx, CI/CD build+release, bootstrap, runbook'lar (asosiy 15 ta), README | 5 |
| B13 | Sinov va mustahkamlash | Birlik/integratsiya/E2E to'ldirish, yuklama T-P-01, chaos asosiy, xavfsizlik tekshiruvi, UAT tayyorlash | 6 |
| | **Jami F1** | | **80** |

### 17.3.3. F2 — Kengaytirilgan (73 kun)

| ID | Ish paketi | Tarkibi | Kun |
|---|---|---|---|
| C1 | Agent kengaytmalari | O'z-o'zini yangilash (imzo, rollback), diskio/inode/jarayonlar, `apt`/reboot/kernel, mahalliy sertifikat (deploy-hook) | 6 |
| C2 | Docker kengaytmalari | Health, resurs statistikasi, OOM, log hajmi, `system df` | 4 |
| C3 | Tekshiruv kengaytmalari | Kalit so'z, sarlavhalar, yo'naltirish, vaqt komponentlari, kunlik uptime, ko'p resolver/tarqalish rejimi, RDAP, cut-over yordamchisi | 8 |
| C4 | Alert kengaytmalari | Titrash, guruhlash, qoidalar UI, qoida testi, F2 qoidalar (48) | 9 |
| C5 | Bildirishnoma kengaytmalari | Sokin soatlar, kunlik/haftalik hisobot, bot buyruqlari, email shablonlari | 6 |
| C6 | Zaxira kengaytmalari | Yaxlitlik, offsite solishtirish (2-daraja), drill (UI+jurnal+eslatma), siyosat, hajm bashorati asosi | 7 |
| C7 | Frontend (F2) | Kengaytirilgan grafiklar (zoom, belgilar), qoidalar/silence/maintenance UI, hisobotlar, domen sahifasi, qorong'i mavzu, SSE, a11y, ru/en | 15 |
| C8 | Xavfsizlik | 2FA, sessiyalar/token UI, audit UI, ZAP, sarlavhalar, parol siyosati kuchaytirish | 6 |
| C9 | Hisobotlar | Uptime/incident/zaxira hisobotlari, CSV/PDF | 4 |
| C10 | Operatsion | Staging, yuklama va chaos testlari to'liq, runbook'lar to'liq (40+), kuzatuv | 8 |
| | **Jami F2** | | **73** |

### 17.3.4. F3 — Yetuklik (32 kun)

| ID | Ish | Kun |
|---|---|---|
| D1 | Loyiha bo'yicha cheklangan viewer (FR-AUTH-005, NFR-DAT-004) | 3 |
| D2 | Ommaviy holat sahifasi (FR-UI-019) | 3 |
| D3 | Ikkinchi tekshiruvchi tugun (FR-HTTP-008) | 4 |
| D4 | `appctl drill` avtomatik drill (FR-BKP-020) | 4 |
| D5 | Eskalatsiya (FR-ALR-015) | 2 |
| D6 | SSH/apt metrikalari, `nginx -t` tekshiruvi, top-N jarayonlar | 3 |
| D7 | Webhook kanali, deploy belgilari (FR-NTF-007, FR-INT-006) | 3 |
| D8 | Global qidiruv, CSV eksport (FR-UI-015/018) | 2 |
| D9 | Supply-chain: `cosign`, SBOM, Renovate | 3 |
| D10 | Silliqlash va xatolarni tuzatish | 5 |
| | **Jami F3** | **32** |

### 17.3.5. Umumiy baho

| Faza | Kishi-kun | 1 dasturchi (haftasiga 4 samarali kun) | 2 dasturchi (parallel) |
|---|---|---|---|
| F0 | 7.5 | ≈ 2 hafta | ≈ 1 hafta |
| F1 | 80 | ≈ 20 hafta | ≈ 10–11 hafta |
| F2 | 73 | ≈ 18 hafta | ≈ 9–10 hafta |
| F3 | 32 | ≈ 8 hafta | ≈ 4–5 hafta |
| **Jami** | **≈ 193** | **≈ 48 hafta (≈ 11 oy)** | **≈ 25 hafta (≈ 6 oy)** |

> **Halol xulosa.** Bu hajm bir kishi uchun jiddiy ish. F1 (MVP) o'zi ham 4–5 oy talab qiladi.
> Agar maqsad tezroq natija bo'lsa, quyidagi variantlar mavjud:
> 1. **Oraliq yechim** (1.9): Uptime Kuma + Healthchecks (o'z-hosting) + `appctl` ga heartbeat
>    — 1–2 kunda ishlaydi va ehtiyojning 60–70% ini yopadi (server/sayt/sertifikat/cron signal).
> 2. **Kichraytirilgan MVP (F1-lite)**: faqat agent (tizim + zaxira + sertifikat) + oddiy panel + Telegram;
>    prober va murakkab alert qoidalarisiz. ≈ 35–40 kun.
> 3. **Mavjud vositalar + o'z qo'shimchasi**: Prometheus/Netdata metrikalar uchun, zaxira/reyestr
>    modulini alohida kichik xizmat qilib yozish.
> Qaror 17.11-bo'limdagi savollar orqali Owner tomonidan qabul qilinadi.

## 17.4. Muhim bosqichlar (milestones)

1 dasturchi varianti uchun (hafta raqami loyiha boshidan):

| Bosqich | Hafta | Natija | Ko'rsatish (demo) |
|---|---|---|---|
| M0 — Protokol prototipi | 2 | Python agent → ingest → grafik; `appctl state.json` | Bitta server grafigi brauzerda |
| M1 — Birinchi alert | 6 | Go agent (tizim), reyestr, alert dvigateli (asosiy qoidalar), Telegram | Agentni to'xtatib, Telegram'da "Server o'chdi" |
| M2 — Faol tekshiruvlar va zaxira | 11 | Prober, sertifikat/DNS, zaxira kartasi, Docker | Domen/sertifikat/zaxira holati panelda |
| M3 — Panel va ishonchlilik | 16 | To'liq F1 paneli, watchdog, o'z zaxirasi, deploy | S-00/S-02 da agentlar |
| M4 — F1 qabul (UAT) | 20 | S-01 agenti, 14 kunlik UAT | UAT-01..12 |
| M5 — F2 | 38 | Kengaytirilgan funksiyalar | Hisobotlar, 2FA, drill |
| M6 — F3 | 48 | Yetuklik | — |

Eslatma: har bosqichda real serverlarda agent kuzatuvi **mumkin bo'lgan eng erta** boshlanadi
(M1 dan S-00, M3 dan S-02, UAT boshida S-01) — shunda real ma'lumot bilan chegaralar sozlanadi.

## 17.5. Resurslar va xarajatlar

### 17.5.1. Odam resursi

| Rol | Ish hajmi | Izoh |
|---|---|---|
| Dasturchi (backend + agent) | F0–F3: ≈ 140 kun | Python/Django + Go |
| Dasturchi (frontend) yoki bir kishi | ≈ 50 kun | React/TS |
| Owner (qabul, qarorlar) | Haftasiga ≈ 2 soat | Demo, savollar |
| Operator (sinov) | UAT davrida ≈ 2 hafta qisman | Haqiqiy serverlar |

(Bir kishi bajarsa, 17.3.5 ning 1-dasturchi ustuni qo'llanadi.)

### 17.5.2. Infratuzilma (taxminiy; narxlar provayderga bog'liq, hujjatda aniq summa yo'q)

| Element | Izoh |
|---|---|
| S-00 (core + offsite) | Mavjud Contabo server (200 GB SSD) qayta o'rnatiladi, yangi xarajat yo'q; S-01 bilan bir provayder (R-110) |
| Watchdog | S-01 da (Owner qarori), qo'shimcha xarajatsiz |
| Offsite zaxira | S-00 da (S-03 ishlatilmaydi); disk hajmi 200 GB ichida nazorat qilinadi |
| Domen | `nazoratchi.<mavjud domen>` — qo'shimcha xarajatsiz |
| Litsenziya | Hamma komponent ochiq manbali (Go, Python/Django, PostgreSQL, TimescaleDB community, Redis 7, nginx, React) |
| Telegram | Bepul (Bot API) |
| CI | GitHub Actions (xususiy repo uchun bepul limit ichida yetarli bo'lishi mumkin) |

### 17.5.3. Ish muhiti

Dev kompyuteri (Docker), GitHub repo, Telegram sinov boti va sinov guruhi, test serveri
(vaqtincha VPS yoki lokal VM'lar: Ubuntu 22.04/24.04 amd64+arm64 uchun).

## 17.6. Dasturchi uchun o'z-o'zini ko'rib chiqish ro'yxati

Yolg'iz ishlaganda kod ko'rigi yo'qligi uchun har PR oldidan:

1. Talab ID si bilan bog'langanmi?
2. Test avval muvaffaqiyatsiz bo'lib, keyin o'tdimi (regressiya)?
3. Maxfiy qiymat log/javob/xato matniga tushmaydimi?
4. Yangi so'rov indeks bilan ishlaydimi (`EXPLAIN`)?
5. Nosozlikda (baza/Redis/tarmoq yo'q) nima bo'ladi — jim yutib yubormaydimi?
6. Yangi alert qoidasi uchun "yolg'on rost" holati testlandimi?
7. UI da holat rang bilan birga matn/belgiga egami? Barcha matn tarjima kalitidami?
8. Migratsiya qaytariladimi?
9. 24 soatdan keyin PR ni yangi ko'z bilan qayta o'qish (muhim o'zgarishlar uchun).

## 17.7. Xavf reyestri (loyiha xavflari)

Ehtimol/ta'sir: **Y**uqori / **O**'rta / **P**ast.

| ID | Xavf | Ehtimol | Ta'sir | Oldini olish / Yumshatish | Egasi |
|---|---|---|---|---|---|
| R-101 | **Ish hajmi o'sib ketishi (scope creep)** | Y | Y | MoSCoW; F1 qamrovi muzlatiladi; yangi g'oyalar F3/ro'yxatga | Owner |
| R-102 | **TimescaleDB** tajriba yo'q; ierarxik/join agregatlar kutilganidek ishlamasligi | P | O | **P-02 da hal qilindi (2026-10-26):** ierarxik va JOIN li agregatlar, siqish, siyosatlar 2.17.2 da ishlaydi (docs/P-02-timescale-sinov.md). Zaxira reja (oddiy partitsiya + Celery) kerak emas | Dasturchi |
| R-103 | Go agent: o'rganish egri chizig'i | O | O | F0 da Python prototip; Go agentni kichik (3–5 ming qator) saqlash; yoki Python agent (PyInstaller) zaxirasi | Dasturchi |
| R-104 | Hajm/unumdorlik baholari noto'g'ri (5.1) | O | O | T-P-01..09 erta; baholarni yangilash; kardinallik chegaralari | Dasturchi |
| R-105 | **Soxta alertlar** — ishonch yo'qoladi, odamlar e'tiborsiz qoladi | Y | Y | `for`, tasdiqlash, gisterezis, bostirish; 4 hafta "yumshoq" rejim (faqat kunlik xulosa); oylik ko'rik (12.11) | Operator |
| R-106 | **Bitta odam (bus factor)** | Y | Y | Hujjat (shu TZ + ADR + runbook); sodda texnologiyalar; kodning ochiq tuzilmasi | Owner |
| R-107 | Telegram API vaqtincha ishlamasligi / bloklanishi | P | Y | Email zaxira kanal; ikkinchi kanal (webhook); AL-086 | Dasturchi |
| R-108 | **Agent ishlab turgan serverda yuk/muammo keltiradi** | O | Y | Resurs cheklovlari (`MemoryMax`, `CPUQuota`); bosqichma-bosqich tarqatish (S-00 → S-02 → S-01); 24 soat kuzatuv; tezkor o'chirish (`uninstall`) | Operator |
| R-109 | **`appctl` o'zgartirishi zaxirani buzadi** (eng xavfli) | O | **Y** | O'zgartirishlar kichik va izolyatsiyalangan (state.json yozishdagi xato zaxirani to'xtatmasligi shart: buyruq oxirida `\|\| true`); avval nusxada sinov; ikki bosqich; o'zgarishdan keyin `appctl backup all` qo'lda tekshiruv; `set -e` ta'siri e'tiborga olinadi | Dasturchi |
| R-110 | Core va kuzatiladigan serverlar bir provayderda — bog'liq nosozlik | O | Y | Qabul qilingan (Owner): core S-00 va S-01 bir provayderda (Contabo); o'zaro kuzatuv (watchdog S-01 da), o'z zaxirasi Telegram'da | Owner |
| R-111 | Vaqt bahosi kam | Y | O | Bufer 20%; har sprintda baholashni yangilash; F1-lite varianti (17.3.5) | Dasturchi |
| R-112 | `docker-socket-proxy` noto'g'ri sozlanishi — agent Docker'ni boshqara oladi | P | Y | Konfiguratsiya testi (T-S-10); `POST=0` majburiy | Dasturchi |
| R-113 | `.uz` domenlar uchun avtomatik WHOIS/RDAP yo'q | Y | P | Qo'lda kiritish + eslatma (FR-DNS-006) | Operator |
| R-114 | S-02 nginx.conf boshqa loyiha tomonidan qayta yoziladi; asadbekashurov.uz yo'qoladi | O | O | Nazoratchi tekshiruvlari darrov topadi (AL-049); aaclub repo egasi bilan kelishuv; qoidani repoga ham qo'shish | Owner |
| R-115 | Maxfiy qiymatlar loglarga tushishi | O | Y | Log filtri + avtomatik skaner testi (T-U-SEC-08) | Dasturchi |
| R-116 | DNS tekshiruvi soxta alert beradi (resolver keshi) | O | P | Tarqalish rejimi, 10 daq. kutish, NS manba haqiqati (11.4) | Dasturchi |
| R-117 | **Restore drill'lar e'tiborsiz qoladi** (jarayon xavfi) | Y | Y | Eslatmalar, panelda ko'rinadigan "hech qachon" belgisi; UAT-09 majburiy | Owner |
| R-118 | Ortiqcha murakkablik: tayyor yechim yetarli edi | O | O | 1.9 va 17.3.5 dagi qarorni F0 oxirida qayta ko'rish ("davom etamizmi?") | Owner |
| R-119 | Redis litsenziyasi / yangi versiya o'zgarishi | P | P | Redis 7.x (BSD) ga qotirish yoki Valkey; Celery/kesh uchun muhim emas | Dasturchi |
| R-120 | Agent yangilanish kanali orqali buzilish (core hujumi) | P | Y | Imzolangan yangilanish (14.5.4) — majburiy talab | Dasturchi |
| R-121 | Telegram bot tokeni sizishi | P | Y | Maxfiy saqlash, rotatsiya yo'riqnomasi (14.12.3) | Owner |
| R-122 | Serverlar soni kutilgandan tez o'sadi | P | P | 15.14 masshtablash bosqichlari | Operator |
| R-123 | Kernel/OS yangilanishi core'ni buzadi (2026-10 saboqi) | O | Y | Avtomatik reboot o'chiq; snapshot; texnik ish oynasi; core'da ham `reboot_required` alerti | Operator |

## 17.8. Bog'liqliklar va taxminlar

| ID | Bog'liqlik/taxmin | Agar bajarilmasa |
|---|---|---|
| DEP-01 | S-00 (core) qayta o'rnatiladi va snapshot olinadi (F0 oxirigacha) | Vaqtincha boshqa serverda (tavsiya etilmaydi, 6.6.1) |
| DEP-02 | `nazoratchi.<domen>` domeni/subdomeni mavjud | Vaqtincha IP orqali (TLS yo'q — tavsiya etilmaydi) |
| DEP-03 | Telegram bot va chat yaratilgan (Owner) | Email bilan boshlanadi |
| DEP-04 | S-00 da offsite papka va SSH kaliti (`rrsync`) sozlanadi | 10.6 offsite qismi kechikadi |
| DEP-05 | `appctl` o'zgartirishlariga Owner roziligi | Papka skaneri (kamroq ishonchli) bilan |
| DEP-06 | Serverlarga root kirish (agent o'rnatish uchun) | — |
| DEP-07 | Owner haftasiga ~2 soat qaror/demo uchun | Kechikish |
| DEP-08 | GitHub repo va CI mavjud | Boshqa CI (GitLab/Gitea) |

## 17.9. Muloqot va hisobot

- Haftalik qisqa hisobot (Telegram/email): bajarilgan, keyingi hafta, to'siqlar, xavflar.
- Har 2 haftada demo (15–20 daqiqa) va talablar bo'yicha qarorlar.
- O'zgarishlar jurnali (`CHANGELOG.md`), talab o'zgarishi TZ hujjat tarixiga yoziladi.
- Har bosqich oxirida qisqa retrospektiva (nima ishladi, nima yo'q).

## 17.10. Hozirgi holatdan o'tish rejasi

| Qadam | Qachon | Nima |
|---|---|---|
| 1 | Hoziroq (1–2 kun) | Oraliq yechim: Uptime Kuma (HTTP/TLS/TCP) + Telegram; `OFFSITE` zaxirani sozlash (ushbu loyihaga bog'liq emas, lekin eng muhim) |
| 2 | F0 | S-00 ni qayta o'rnatish va tayyorlash; `appctl` o'zgartirishlari; protokol prototipi |
| 3 | M1 | S-00 da agent; birinchi Telegram alertlari |
| 4 | M3 | S-02 da agent; Uptime Kuma bilan parallel ishlash |
| 5 | M4 | S-01 da agent; UAT 14 kun |
| 6 | UAT keyin | Uptime Kuma o'chiriladi yoki ikkilamchi tekshiruv sifatida qoladi; 4 haftalik "yumshoq rejim" (soxta alert tuning) |
| 7 | F2/F3 | Qolgan loyihalar (ko'chirilmaganlar) ko'chirilgani sayin reyestrga qo'shiladi |

## 17.11. Owner qarori kerak bo'lgan savollar

| № | Savol | Variantlar | Tavsiya | Ta'siri |
|---|---|---|---|---|
| Q-01 | Nazoratchi'ni yozamizmi yoki tayyor yechimlar bilan boshlaymizmi? | (a) to'liq Nazoratchi; (b) F1-lite; (c) Uptime Kuma + Netdata + o'z zaxira modulingiz | (c) darhol boshlang; (b)/(a) ni F0 natijasi bilan qaror qiling | Muddat 6 oy ↔ 1 hafta |
| Q-02 | Core qayerda? | Alohida VPS (boshqa provayder) / S-02 / S-01 | Alohida VPS | Ishonchlilik |
| Q-03 | Agent tili | Go / Python | Go (F0 da Python prototip) | O'rganish vs ekspluatatsiya soddaligi |
| Q-04 | Telegram: shaxsiy chat yoki guruh; kim ikkinchi kontakt? | | Guruh (2 kishi) | Eskalatsiya |
| Q-05 | Domen nomi | `nazoratchi.avlo.ai` / boshqa | Mavjud domen ostida subdomen | TLS, DNS |
| Q-06 | Loyiha nomi "Nazoratchi" tasdiqlanadimi? | | Ishchi nom | Brending |
| Q-07 | Offsite server (38.242.143.248) rostan ham sizniki va joy yetarlimi? | | Tekshirish | 10.6 |  <!-- javob: S-03 ishlatilmaydi, offsite S-00 da -->
| Q-08 | `appctl` ga o'zgartirish kiritishga rozimisiz? | | Ha (ehtiyotkorlik bilan) | R-109 |
| Q-09 | Mijozlarga (masalan, wmg.uz) holat ko'rsatish kerakmi? | | F3 (status sahifa) | Qamrov |
| Q-10 | S-02 (aaclub) serveriga agent o'rnatishga ruxsat egasidan olinganmi? | | Kelishing | Ruxsat |
| Q-11 | Reboot/kernel yangilanishi rejasi (S-01 da 6.8.0-147 kutmoqda) qachon? | | Offsite + snapshotdan keyin | Xavfsizlik |

> **Javoblar (2026-10-26)** — to'liq ro'yxat QARORLAR.md da: Q-01 to'liq F0→F3; Q-02 core S-00 da; Q-03 Go; Q-04 guruh; Q-05 domen nomga qarab; Q-06 "Nazoratchi"; Q-07 offsite S-00 ga (S-03 ishlatilmaydi); Q-08 ha; Q-10 ruxsat kerak emas; Q-11 hozircha reboot yo'q. Q-12 GCP IP yopilgan (`retired_ips`); Q-13 o'z zaxirasi `age` bilan shifrlanib Owner'ning shaxsiy Telegram chatiga; Q-14 watchdog S-01 da (o'zaro kuzatuv).

## 17.12. Topshirish va qabul tartibi

1. Har faza oxirida: ishlaydigan tizim (prod), testlar hisoboti, yangilangan hujjatlar.
2. Owner UAT ro'yxatini (16.8) o'tkazadi; har band uchun imzo (o'tdi/o'tmadi).
3. O'tmagan band — nuqson ro'yxatiga (daraja 16.10.1), tuzatilib qayta tekshiriladi.
4. Faza qabul qilingach, TZ hujjat tarixiga yozuv va keyingi faza boshlanadi.
5. Yakuniy topshirish: manba kod, hujjatlar, runbook'lar, maxfiy qiymatlar ro'yxati
   (qiymatlarsiz, qayerda saqlanishi), tiklash yo'riqnomasi (15.9) sinalgan.
