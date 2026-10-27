# 6. Tizim arxitekturasi

## 6.1. Umumiy ko'rinish

```
 Brauzer (Owner/Operator/Viewer)         Telegram Bot API               Watchdog (S-01)
     │ HTTPS                             ▲   │ webhook                  ▲  │ ping/hb
     ▼                                   │   ▼                          │  ▼
┌────────────────────────────────  S-00: Nazoratchi CORE + offsite  ─────────────────────────────────┐
│  nginx (80/443, TLS, rate-limit)                                                                   │
│    ├─ /            → frontend (statik SPA)                                                         │
│    ├─ /api/        → web (Django ASGI)                                                             │
│    ├─ /ingest/     → web (ingest endpointlari, alohida limit)                                      │
│    └─ /hb/<token>  → web (kiruvchi heartbeat)                                                      │
│                                                                                                    │
│  web ──────► db (PostgreSQL 16 + TimescaleDB) ◄────── evaluator (alert hisoblash)                  │
│   │             ▲                                      ▲                                           │
│   │             │                                      └── prober (HTTP/TLS/DNS tekshiruvlari)     │
│   └──► redis ◄──┴──── worker (Celery: bildirishnoma, hisobot, retention, o'z zaxirasi)             │
└────────────────────────────────────────────────────────────────────────────────────────────────────┘
             │                          │                          │
        agent → core               agent → core               agent → core
             │                          │                          │
   ┌───────────────────┐      ┌───────────────────┐      ┌───────────────────┐
   │ S-01 main-2       │      │ S-02 vmd208589    │      │ S-00 (core ham)   │
   │ nazoratchi-agent  │      │ nazoratchi-agent  │      │ nazoratchi-agent  │
   │ docker, watchdog  │      │ docker, nginx     │      │ /srv/backups      │
   └───────────────────┘      └───────────────────┘      └───────────────────┘
```

Asosiy g'oyalar:

1. **Agent itaruvchi (push) modelda ishlaydi.** Kuzatiladigan serverlarda hech qanday yangi
   kiruvchi port ochilmaydi; bu xavfsizlikni oshiradi va NAT/firewall orqasidagi serverlar
   bilan ham ishlaydi.
2. **Core kuzatiladigan serverlardan alohida** joyda turadi. Aks holda bitta server o'lganda
   monitoring ham o'ladi va hech kim bilmaydi (eski serverdagi hodisaning saboqi).
3. **Faol tekshiruvlarni (HTTP/TLS/DNS) core bajaradi** — mijoz nuqtai nazaridan, tashqaridan.
   Agent esa ichkaridan ko'radi. Ikkalasi ham kerak: sayt "tashqaridan ishlamayapti,
   ichkaridan hammasi yaxshi" holati (masalan, nginx yoki DNS muammosi) faqat shunday topiladi.
4. **Core ham kuzatiladi**: boshqa serverdagi (S-01) watchdog uni tekshiradi (FR-SYS-002); S-01 ni esa core kuzatadi.

## 6.2. Komponentlar

| Komponent | Vazifa | Texnologiya | Ma'lumot saqlaydimi | Masshtab |
|---|---|---|---|---|
| **agent** (`nazoratchi-agent`) | Metrikalarni yig'ish va yuborish, mahalliy bufer | Go 1.23, `gopsutil`, systemd | Faqat bufer (diskda, 20 MB) | Har host 1 nusxa |
| **nginx** | TLS, marshrutlash, statik fayllar, tezlik cheklovi | nginx | Yo'q | 1 |
| **web** | REST API, ingest, autentifikatsiya, SSE, Telegram webhook | Python 3.13, Django 5, DRF, uvicorn | Yo'q (holatsiz) | 1–N |
| **evaluator** | Alert qoidalarini davriy hisoblash, incident holati mashinasi | Python (asyncio), Django ORM | Bazada holat | 1 (leader) |
| **prober** | HTTP/TCP/TLS/DNS/WHOIS faol tekshiruvlari | Python (asyncio, httpx, dnspython) | Bazaga natija yozadi | 1–2 |
| **worker** | Bildirishnoma yuborish, hisobotlar, retention, o'z zaxirasi | Celery 5 + Redis | Yo'q | 1–N |
| **beat** | Davriy vazifalar jadvali | Celery beat | Yo'q | 1 |
| **db** | Barcha ma'lumot | PostgreSQL 16 + TimescaleDB 2.x | Ha | 1 |
| **redis** | Celery navbati, kesh, rate-limit, SSE pub/sub | Redis 7 | Vaqtinchalik | 1 |
| **frontend** | Veb-panel | React 18 + TypeScript + Vite, build → statik | Yo'q | CDN-siz, nginx |
| **watchdog** | Nazoratchi tirikligini tashqaridan tekshirish | Kichik Python skript + systemd, **S-01 da** (Owner qarori; ADR-014) | Faqat oxirgi ping vaqti | 1 |
| **docker-socket-proxy** | Agentga Docker ma'lumotini faqat o'qish uchun berish | `tecnativa/docker-socket-proxy` | Yo'q | Har Docker hostda |

## 6.3. Texnologiya tanlovi — arxitektura qarorlari (ADR)

Har qaror: **Kontekst → Qaror → Sabab → Oqibatlar → Muqobillar**.

### ADR-001. Markaziy server: Django + DRF

- **Kontekst.** Buyurtmachi Django (Nazar, BiznesRadar, wmg) bilan tajribali; kod egasi
  bitta odam.
- **Qaror.** Django 5 + DRF, ASGI (uvicorn) da.
- **Sabab.** Tanish stek — tez ishlab chiqish va ekspluatatsiya; Django admin zaxira boshqaruv
  oynasi sifatida foydali; ORM, migratsiya, autentifikatsiya tayyor. Ingest yuklamasi past
  (30 host / 15 s ≈ 2 so'rov/soniya) — Django uchun muammo emas.
- **Oqibat.** Ingest yozuvlari `bulk_create`/`COPY` bilan paketlanadi (ORM orqali bittalab emas).
- **Muqobillar.** FastAPI (tezroq, lekin admin/autentifikatsiyani qo'lda yozish kerak);
  Go backend (eng yengil, lekin buyurtmachi tajribasi kam).

### ADR-002. Vaqt qatorlari bazasi: PostgreSQL + TimescaleDB

- **Qaror.** Alohida TSDB (Prometheus/VictoriaMetrics/InfluxDB) o'rniga PostgreSQL
  ustida TimescaleDB kengaytmasi.
- **Sabab.** Bitta baza: reyestr, incidentlar, audit va vaqt qatorlari birga (JOIN, tranzaksiya,
  bitta zaxira). Timescale gipertablitsalari, siqish, doimiy agregatlar (continuous aggregates)
  va saqlash siyosatlari tayyor — o'z downsampling kodimizni yozmaymiz.
- **Oqibat.** Docker image `timescale/timescaledb:latest-pg16`. Zaxira va tiklash `pg_dump`
  bilan (bizga tanish). TimescaleDB litsenziyasi (TSL) o'z-hosting uchun bepul.
- **Muqobil (agar Timescale tanlanmasa).** Oddiy PostgreSQL deklarativ partitsiyalash
  (kunlik) + `pg_cron`/Celery bilan agregat. Kod ikkala holatda ishlashi uchun repozitoriy
  (data access) qatlami orqali yoziladi (NFR-MNT-008).
- **Xavf.** Timescale tajribasi yo'q; R-102.

### ADR-003. Agent tili: Go

- **Qaror.** Agent — Go da, statik binar (`CGO_ENABLED=0`), amd64 va arm64.
- **Sabab.** Bitta fayl, interpreter va bog'liqliklarsiz, ~10 MB, ~15–25 MB RAM; Python agent
  har serverda virtual muhit va versiya muammolarini keltiradi (eski serverda Python 3.13,
  tizim Python 3.12 — bunday nomuvofiqliklar ma'lum). Cross-compile oson.
- **Oqibat.** Agent kodi alohida modul/repo; hajmi taxminan 3–5 ming qator. Buyurtmachi Go
  bilan tanish bo'lmasa, F0 da prototip Python (`psutil`) bilan yoziladi va protokol
  tasdiqlangach Go ga o'tkaziladi (17-bo'lim).
- **Muqobillar.** Python + psutil (oson, lekin og'irroq va bog'liqlik), Rust (eng yengil, lekin
  o'rganish qiyin).

### ADR-004. Agent → core: HTTPS push, JSON+gzip

- **Qaror.** Agent HTTPS POST yuboradi (`/ingest/v1/metrics`), JSON, `Content-Encoding: gzip`.
- **Sabab.** Eng sodda, firewall/proksi bilan muammosiz, curl bilan nosozlikni topish oson.
  Hajm kichik (≈ 2–4 KB siqilgan paket), shuning uchun protobuf/gRPC qulayligi katta emas.
- **Oqibat.** Protokol versiyalanadi (`/v1/`). Kelajakda yuklama oshsa protobuf qo'shish mumkin.

### ADR-005. Faol tekshiruvlar core ichida (prober)

- **Qaror.** HTTP/TLS/DNS tekshiruvlari core serverdagi alohida `prober` jarayoni bilan.
- **Sabab.** Tashqi ko'rinish; agent o'chsa ham sayt tekshiriladi.
- **Oqibat.** Core serverning chiquvchi tarmog'i barqaror bo'lishi kerak; F3 da ikkinchi
  tekshiruvchi tugun (FR-HTTP-008).

### ADR-006. Frontend: React + TypeScript + Vite, statik build

- **Qaror.** SPA; build `dist/` ni nginx beradi (SSR yo'q).
- **Sabab.** Panel autentifikatsiyalangan ichki ilova — SEO kerak emas; statik fayllar oddiy
  va tez; Next.js ga ehtiyoj yo'q. Buyurtmachi loyihalarida React/TS tajribasi bor.
- **Kutubxonalar.** TanStack Query (ma'lumot keshi), React Router, Tailwind CSS, `uPlot`
  (juda tez vaqt qatori grafiklari; 100+ nuqtali ko'p grafik uchun ECharts'dan yengil),
  `i18next` (uz/ru/en), `zod` (API javob validatsiyasi).

### ADR-007. Real vaqt: SSE (Server-Sent Events)

- **Qaror.** Dashboard yangilanishi uchun WebSocket emas, SSE.
- **Sabab.** Faqat serverdan klientga yo'nalish kerak; SSE oddiy va avtomatik qayta ulanadi;
  Redis pub/sub bilan oson.
- **Muqobil.** Har 5 s polling (zaxira rejimi; SSE ishlamasa).

### ADR-008. Navbat: Celery + Redis

- **Qaror.** Bildirishnoma, hisobot, retention uchun Celery.
- **Sabab.** Buyurtmachi Nazar loyihasida Celery + Redis + beat ni allaqachon ishlatadi;
  bir xil tajriba va monitoring.
- **Muhim istisno.** Alert hisoblash (evaluator) va faol tekshiruvlar (prober) Celery'da emas,
  alohida uzoq yashaydigan jarayonlar: Celery beat'ning soniyalik aniqligi va leader
  boshqaruvi yetarli emas.

### ADR-009. Deploy: Docker Compose, bitta server

- **Qaror.** Core Docker Compose bilan, bitta VPS da.
- **Sabab.** Miqyos kichik; Kubernetes ortiqcha. Compose buyurtmachi `appctl` standartiga mos:
  Nazoratchi o'zi ham `/opt/applications/projects/Nazoratchi/` da, `.appctl` bilan boshqariladi.
- **Oqibat.** Core — SPOF; shuning uchun RTO ≤ 1 soat (zaxira + qayta ko'tarish) va tashqi
  watchdog.

### ADR-010. Autentifikatsiya: Django sessiyalari (brauzer) + tokenlar (agent/API)

- **Qaror.** Brauzer uchun cookie-sessiya + CSRF; agent/API uchun `Authorization: Bearer`.
- **Sabab.** JWT ning murakkabligi ortiqcha; sessiyani server tomonida bekor qilish oson.

### ADR-011. Alert holati: bazada (xotirada emas)

- **Qaror.** Alert/incident holati PostgreSQL da saqlanadi; evaluator qayta ishga tushsa
  holatni bazadan tiklaydi.
- **Sabab.** Qayta ishga tushganda "tiklandi/yangi alert" xabarlari takrorlanmasligi kerak.

### ADR-012. Reyestr — yagona manba

- **Qaror.** Kuzatuv sozlamasi (qaysi domen tekshiriladi, qaysi konteyner qaysi loyihaga
  tegishli) reyestrdan hosil bo'ladi, agent sozlamasidan emas.
- **Sabab.** Bitta joyda o'zgartirish; ikki manba nomuvofiqlikka olib keladi.

### ADR-013. Ma'lumot modeli: "tor" (long) metrika jadvali

- **Qaror.** `metric_samples(time, series_id, value)` — bitta uzun jadval; `series` jadvali
  (metrika nomi + belgilar/labels) alohida (Prometheus modeliga o'xshash).
- **Sabab.** Yangi metrika qo'shish migratsiyasiz (NFR-CAP-004); siqish samarali.
- **Oqibat.** Qatorlar kardinalligi (cardinality) nazorat qilinadi: har host uchun `series`
  soni ≤ 1 000 (agent chegarasi), aks holda ogohlantirish.

### ADR-014. Watchdog: mustaqil va minimal

- **Qaror (Owner, 2026-10-26).** Watchdog — Nazoratchi koddan mustaqil kichik xizmat (≤ 100 qator),
  alohida jarayon va alohida Telegram bot bilan; **S-01 (main-2) da**, core (S-00) dan boshqa serverda.
- **Sabab.** Nazoratchi o'chsa, uning o'z xabarlari ham ketmaydi (kod, bot va server mustaqilligi shundan).
- **O'zaro kuzatuv.** Core S-01 ni agent heartbeat orqali kuzatadi; S-01 dagi watchdog core'dan
  60 soniyada bir ping kutadi (va ixtiyoriy ravishda `/healthz` ni tekshiradi). Bitta server o'lsa,
  ikkinchisi xabar beradi.
- **Qoldiq xavf.** S-00 va S-01 bir provayderda (Contabo). Ikkalasi bir vaqtda tushsa, hech kim xabar
  bermaydi (RS-06). Oxirgi yumshatish — o'z Uptime Kuma yoki tashqi bepul xizmat (majburiy emas).

## 6.4. Backend modullari (Django ilovalari)

```
nazoratchi/
  apps/
    accounts/       # foydalanuvchi, rol, sessiya, 2FA, tokenlar
    registry/       # Server, Project, Domain, Service (reyestr), teglar
    ingest/         # /ingest/v1/* endpointlari, validatsiya, yozish
    metrics/        # Series, MetricSample, agregatlar, so'rov API
    inventory/      # host ma'lumoti (OS, kernel, jihoz), o'zgarish voqealari
    probes/         # HTTP/TCP/TLS/DNS/WHOIS tekshiruvlari, natijalar, uptime
    backups/        # zaxira holati, restore drill, offsite solishtirish
    alerts/         # qoida, holat, incident, silence, maintenance, bostirish
    notify/         # kanallar (telegram/email/webhook), shablonlar, yuborish
    reports/        # kunlik/haftalik hisobotlar, uptime hisoblash
    audit/          # audit jurnali
    realtime/       # SSE, Redis pub/sub
    core/           # umumiy: sozlamalar, vaqt, kriptografiya, yordamchilar
  workers/
    evaluator.py    # alert hisoblash jarayoni (asyncio)
    prober.py       # faol tekshiruvlar jarayoni (asyncio)
  config/           # Django sozlamalari (base/dev/prod)
```

Bog'liqlik qoidasi (bir yo'nalishli): `core ← registry ← (metrics, probes, backups, inventory)
← alerts ← notify`. `alerts` boshqa modullarni **o'qiydi**, ular esa `alerts` ni import
qilmaydi (signal/hodisa orqali).

## 6.5. Asosiy oqimlar

### 6.5.1. Metrikalarni qabul qilish (ingest)

1. Agent paket tuzadi: `{agent_id, seq, sent_at, samples:[{name, labels, t, v}], facts:{...}}`.
2. `POST /ingest/v1/metrics` + `Authorization: Bearer <agent_token>`.
3. nginx tezlik cheklovini qo'llaydi (NFR-SEC-007), so'rovni `web` ga uzatadi.
4. `web` tokenni tekshiradi (xesh bo'yicha), host faolligini (arxiv emasligini) tekshiradi.
5. Paket tekshiriladi (sxema, `sent_at` majburiy; namuna vaqti tuzatilgandan keyin `now − 1 soat ≤ t ≤ now + 1 daqiqa`, 6.10).
6. `series` kesh (Redis/xotira) orqali `series_id` lar aniqlanadi; yo'q bo'lsa yaratiladi
   (kardinallik chegarasi bilan).
7. Namunalar `COPY`/`bulk_create` bilan `metric_samples` ga yoziladi; oxirgi qiymatlar
   `series_latest` jadvalida yangilanadi (UPSERT).
8. `hosts.last_seen = now`; Redis'ga `host:<id>:updated` hodisasi (SSE uchun).
9. Javob: `200 {"ok":true,"server_time":"...","next_interval":15,"commands":[]}`. Qabul
   qilinmagan (takroriy) paketga ham `200` (idempotent, agent navbatdan o'chiradi).

### 6.5.2. Alert hisoblash

1. `evaluator` har 15 soniyada (`tick`) yoqilgan qoidalarni yuklaydi (60 s kesh).
2. Har qoida uchun qamrovdagi obyektlar bo'yicha shart hisoblanadi:
   `series_latest`, oxirgi N daqiqa xom ma'lumoti yoki `probe_results` dan.
3. Natijada har (qoida, obyekt) juftligi uchun holat: `ok` → `pending` (shart bajarildi, `for`
   kutilmoqda) → `firing` → `resolved`.
4. `firing` ga o'tganda: bostirish (6.7.3) va silence/maintenance tekshiriladi; o'tgan bo'lsa
   incident yaratiladi/yangilanadi va `notify` ga topshiriq (Celery) yuboriladi.
5. Har tick oxirida `evaluator_heartbeat` bazaga yoziladi (FR-SYS-001).

### 6.5.3. Faol tekshiruv

1. `prober` har tekshiruv uchun navbatdagi vaqtni (`next_run_at`) bazadan oladi.
2. Asinxron ravishda (`httpx.AsyncClient`, `dnspython`, `ssl`) bajaradi, vaqtlarni o'lchaydi.
3. Natija `probe_results` ga yoziladi; holat o'zgargan bo'lsa (3 ketma-ket qoida) —
   `check_state` yangilanadi va `evaluator` ga hodisa (Redis) yuboriladi.
4. Xato turi (timeout, dns, tls, 5xx, kalit so'z yo'q) saqlanadi.

### 6.5.4. Bildirishnoma yuborish

1. `evaluator` Celery vazifasi `notify.send_incident(incident_id, event)` ni navbatga qo'yadi.
2. `worker` kanal sozlamalarini oladi, sokin soatlarni (FR-NTF-006) tekshiradi, xabarni
   shablondan hosil qiladi.
3. Telegram'ga yuboradi; muvaffaqiyatsiz bo'lsa eksponensial kutish (5 s, 20 s, 1 daq, 5 daq,
   15 daq); hammasi yo'qolsa, ikkinchi kanal (email).
4. Yetkazilish natijasi `notifications` jadvaliga yoziladi (kim, qachon, qaysi kanal, holat).

### 6.5.5. Telegram tugmasi (callback)

1. Telegram `POST /api/v1/telegram/webhook/<secret>` ga yuboradi.
2. `web` `chat_id` ni ruxsat etilganlar ro'yxati bilan solishtiradi, `X-Telegram-Bot-Api-Secret-Token`
   sarlavhasini tekshiradi.
3. `ack`/`silence` amali bajariladi, audit jurnaliga yoziladi, xabar yangilanadi (`editMessageText`).

### 6.5.6. Panelga jonli yangilanish (SSE)

1. Brauzer `GET /api/v1/stream?scope=dashboard` ochadi (cookie bilan).
2. `web` Redis pub/sub'ga obuna bo'ladi; `ingest`/`evaluator` hodisalarini (host holati,
   incident) 1 soniyalik partiyalar bilan yuboradi.
3. Aloqa uzilsa brauzer avtomatik qayta ulanadi (`Last-Event-ID`); 3 marta muvaffaqiyatsiz
   bo'lsa, polling (5 s) ga o'tadi.

## 6.6. Joylashtirish (deployment) topologiyasi

### 6.6.1. Serverlar

| Server | Rol | Joylashuv | Tavsiya etilgan xususiyat |
|---|---|---|---|
| **S-00** | Nazoratchi CORE + offsite zaxira (S-01 uchun) | Contabo (`185.214.135.9`), kuzatiladigan S-01 dan **boshqa server**, lekin bir provayderda (R-110) | 200 GB SSD, Ubuntu 24.04 (qayta o'rnatiladi), kuniga snapshot |
| S-01, S-02 | Agent o'rnatiladi (S-00 da ham agent bor); S-01 da watchdog ham | Mavjud | — |
| Watchdog | Nazoratchi tirikligini tekshirish | **S-01** (Owner qarori) | Minimal |

**Qaror (Owner, 2026-10-26).** Core S-00 da, S-01 dan alohida: S-01 o'lsa, S-01 uchun xabar beradigan
tizim yo'qolmaydi. S-02 aaclub bilan band va uning nginx front-proksi qoidalariga bog'liq (R-009),
shuning uchun core uchun ishlatilmaydi. S-00 oldin yuklanmagan (1.3.1), shu sabab qayta o'rnatishdan
keyin darhol provayder snapshoti olinadi. S-03 zaxira uchun ishlatilmaydi.

**Vazifalar taqsimoti.** Core va S-01 uchun offsite zaxira S-00 da turadi. Watchdog S-01 da turadi
(ADR-014). Nazoratchi'ning **o'z zaxirasi** (FR-SYS-003) S-00 dan tashqarida — Owner'ning shaxsiy
Telegram chatida, `age` bilan shifrlangan holda saqlanadi.

### 6.6.2. Docker Compose servislari (core)

| Servis | Image | Portlar (127.0.0.1) | Hajm (volume) |
|---|---|---|---|
| `db` | `timescale/timescaledb:latest-pg16` | 5432 (faqat ichki tarmoq) | `nazoratchi_pgdata` |
| `redis` | `redis:7-alpine` | — | `nazoratchi_redis` (AOF o'chiq, kesh) |
| `web` | `ghcr.io/<owner>/nazoratchi-web:<ver>` (o'zimiz quramiz) | 8040 | — |
| `evaluator` | shu image, `command: python -m workers.evaluator` | — | — |
| `prober` | shu image, `command: python -m workers.prober` | — | — |
| `worker` | shu image, `celery -A config worker` | — | — |
| `beat` | shu image, `celery -A config beat` | — | `nazoratchi_beat` |
| `frontend` | `nginx:alpine` + statik fayllar | 3040 | — |

Port tanlovi `REGISTRY.md` qoidasiga mos: keyingi bo'sh backend/frontend portlari (8040, 3040
taklif qilinadi; S-01 dagi bandlari bilan to'qnashuvni reyestr tekshiradi, FR-REG-010).

### 6.6.3. Tarmoq va xavfsizlik chegaralari

- Tashqariga faqat 80/443 (nginx). `db`, `redis` ichki Docker tarmog'ida; xostga chiqarilmaydi.
- `/ingest/*` — tashqaridan ochiq (agentlar uchun), lekin token + tezlik cheklovi bilan.
- `/api/*`, UI — autentifikatsiya talab qiladi; ixtiyoriy IP allowlist (NFR-SEC-011).
- `/metrics`, `/healthz` — faqat ichki yoki token bilan.
- Agent → core: faqat 443. Core → Telegram: 443 (chiquvchi).
- DNS: `nazoratchi.<domen>` A yozuvi core serverga; sertifikat Let's Encrypt (certbot).

### 6.6.4. Nazoratchi'ning o'zi `appctl` bilan

`/opt/applications/projects/Nazoratchi/` + `.appctl` (`DB_SERVICE=db`, `DB_USER=nazoratchi`,
`DB_NAME=nazoratchi`, `HEALTH_URL=http://127.0.0.1:8040/healthz`). `appctl backup all` uni ham
zaxiralaydi; xuddi shu mexanizm bilan Nazoratchi **o'z zaxirasini** ham kuzatadi (FR-SYS-003).

## 6.7. Alert dvigateli dizayni

### 6.7.1. Holat mashinasi (har qoida × obyekt)

```
     shart yolg'on                shart rost                 shart rost `for` davomida
  ┌────────────────┐        ┌───────────────┐             ┌───────────────────────────┐
  │                ▼        │               ▼             │                           ▼
 [OK] ───────────────► [PENDING] ─────────────────────► [FIRING] ──── shart yolg'on ──► [RESOLVING]
  ▲        shart rost      │  shart yolg'on (OK ga qaytadi)  ▲                              │
  │                        └─────────────────────────────────┘                              │
  └───────────── `resolve_after` (standart 60 s) davomida yolg'on ─────────────────────────┘
```

- `PENDING`: shart rost bo'ldi, lekin `for` hali o'tmadi — xabar yuborilmaydi. Agar shu paytda ma'lumot butunlay
  yo'qolsa (agent jim), uzluksizlik tasdiqlanmagan hisoblanadi va holat `OK` ga qaytadi; aks holda agent bir soatdan
  keyin qaytganda eski `PENDING` darrov `FIRING` bo'lib ketardi. `FIRING`/`RESOLVING` ma'lumot yo'qligida o'zgarmaydi.
- `FIRING`: alert faol; incident ochiq.
- `RESOLVING`: shart yolg'on bo'ldi, `resolve_after` kutiladi (titrashdan himoya, FR-ALR-018).
- `OK`: yopildi; "tiklandi" xabari yuboriladi (agar FIRING bo'lgan bo'lsa).

### 6.7.2. Incident va alert o'rtasidagi bog'liqlik

- **Alert instance** — bitta (qoida × obyekt) ning FIRING holati.
- **Incident** — bir yoki bir nechta alert instance dan tashkil topgan, odam uchun mo'ljallangan
  yagona voqea. Yangi alert, agar xuddi shu **qamrov kaliti** (masalan, `host:S-01`) bo'yicha
  ochiq incident bo'lsa, o'shanga qo'shiladi; aks holda yangi incident ochiladi.
- Incident'ning ahamiyati = ichidagi alertlarning eng yuqorisi. Incident `started_at` — birinchi alertning shart
  rost bo'la boshlagan vaqti (`for` kutish davri ham kiradi), shuning uchun "Davomiyligi" haqiqiy muammo vaqtini ko'rsatadi.
- Incident yopiladi: barcha alert instance lari `OK` bo'lganda (+ 60 s).

### 6.7.3. Bostirish (suppression) qoidalari

| Sharoit | Natija |
|---|---|
| Host `down` (critical) | Shu hostdagi barcha `docker_*`, `svc_*`, `backup_age_*`, `http_*` (agar loyiha asosiy serveri shu bo'lsa) alertlari bostiriladi va incident "ta'sirlangan" ro'yxatiga qo'shiladi |
| Domen DNS mos emas | O'sha domen uchun `http_down` va `tls_*` alertlari bostiriladi (sabab bitta) |
| Maintenance oynasi | Qamrovdagi hamma alert bostiriladi, yig'iladi |
| Silence | Moslik (matcher) bo'yicha bostiriladi |
| Server `pause` | Hamma alert bostiriladi |

### 6.7.4. Bashorat (forecast)

Disk to'lishi: oxirgi 6 soatlik (`disk_used_bytes`) nuqtalariga eng kichik kvadratlar usuli
bilan chiziq o'tkaziladi; `eta = (jami − hozirgi) / qiyalik`. Chiziq R² < 0.5 bo'lsa (tartibsiz),
bashorat ishonchsiz deb belgilanadi va faqat chegara qoidasi ishlaydi. Qo'shimcha: 24 soatlik
va 7 kunlik oynalar ham hisoblanadi, **eng yomon (eng yaqin)** natija ishlatiladi.

## 6.8. Prober dizayni

- **Rejalashtirish.** Har tekshiruvning `next_run_at` maydoni bor; jitter (±10%) bilan taqsimlanadi,
  shunda 450 tekshiruv bir soniyada boshlanmaydi.
- **Parallellik.** `asyncio.Semaphore(50)`; har tekshiruv uchun qattiq timeout.
- **HTTP.** `httpx` (HTTP/2 qo'llab-quvvatlanadi), DNS/TCP/TLS/TTFB vaqtlari `httpx` hodisa
  ilgaklari yoki alohida `socket`/`ssl` o'lchovlari bilan.
- **TLS.** `ssl.create_default_context()` + `getpeercert()`; tekshiruvsiz rejim muddatni
  o'qish uchun (hostname mos kelmaydigan holatni ham aniqlash uchun alohida o'tish).
- **DNS.** `dnspython`, resolverlar ro'yxati; har resolver uchun alohida natija (`probe_dns_results`).
- **Tasdiqlash qoidasi.** Muvaffaqiyatsiz natijadan keyin 15 s oraliq bilan 2 marta qayta
  tekshiriladi; 3 ketma-ket xato = `down`. Bitta muvaffaqiyat = `up`.
  *Amalga oshirish (S4):* qayta tekshiruv oqimni uxlatmaydi — `next_run_at` 15 s ga suriladi; tasdiqlanmagan xatolarda holat
  o'zgarmaydi (`unknown` bo'lsa `unknown` qoladi). Parallellik: `asyncio` o'rniga 50 oqimli `ThreadPoolExecutor`; vaqti kelganlar
  `SELECT ... FOR UPDATE SKIP LOCKED` bilan olinib, `next_run_at` avval suriladi (bir nechta prober takrorlamaydi).
- **IP-pinning (S4).** Nom bir marta aniqlanadi, tekshiruvdan o'tgan IP ga ulanadi; `Host` sarlavhasi va TLS SNI/sertifikat
  tekshiruvi asl nomda qoladi (DNS rebinding oldini oladi, `resolve_to` shu mexanizm). Har yo'naltirish qayta aniqlanadi va
  tekshiriladi. Vaqtlar (`dns/connect/tls/ttfb`) `httpx` trace hodisalaridan olinadi. S4 da faqat HTTP va TCP; TLS/DNS/WHOIS — S5.
- **Ruxsat etilgan chiquvchi manzillar.** Prober ichki/loopback IP larga (SSRF xavfi) so'rov
  yubormaydi: manzil aniqlangach shaxsiy diapazonlar (`10/8`, `172.16/12`, `192.168/16`,
  `127/8`, `169.254/16`) rad etiladi (maxsus ruxsat bilan o'zgartiriladi).

## 6.9. Muvaffaqiyatsizlik rejimlari (FMEA)

| Nosozlik | Ta'siri | Aniqlash | Yumshatish |
|---|---|---|---|
| Core serveri (S-00) o'ldi | Monitoring yo'q | S-01 dagi watchdog (5 daq) | Agent buferi 15 daq; zaxiradan tiklash RTO 1 soat |
| `db` to'xtadi | Yozib bo'lmaydi | `/healthz` 503, watchdog | Redis navbati (15 daq), `restart: unless-stopped` |
| `evaluator` qotdi | Yangi alert chiqmaydi | `evaluator_heartbeat` eskirdi → watchdog | Docker healthcheck + avto-restart |
| `prober` qotdi | Faol tekshiruv natijasi yo'q | `probe_last_run` eskirdi | healthcheck, "ma'lumot eskirgan" alerti |
| Telegram API ishlamayapti | Xabar yetmaydi | `notify` xato hisoblagichi | Qayta urinish + email zaxira kanal |
| Agent to'xtadi (host tirik) | Host ma'lumoti yo'q | Heartbeat 120 s | "Agent javob bermayapti" (`high`), TCP:22 tekshiruvi |
| Host o'ldi | Hamma narsa yo'q | Heartbeat + TCP:22 | "Server o'chdi" (`critical`), bostirish |
| Core va agent o'rtasida tarmoq uzildi | Hamma host "jim" | Ko'p hostlar bir vaqtda jim bo'lsa — "core tarmog'i" gumoni | Massaviy holat: > 50% host jim bo'lsa bitta yig'ma alert, TCP:22 tekshiruvi farqlaydi |
| Soat siljishi (core) | Vaqt tamg'alari xato | NTP kuzatuvi (FR-HST-013) | chrony, agent soat farqi hisoboti |
| Disk to'ldi (core) | Yozish to'xtaydi | O'z disk alerti | Retention, hajm chegarasi, 85% da `critical` |
| Zararli/buzuq paket | Baza ifloslanadi | Validatsiya xatolari soni | Sxema tekshiruvi, qiymat diapazoni, token cheklovi |

## 6.10. Vaqt va soat

- Barcha vaqt UTC (`timestamptz`), API da ISO-8601 (`2026-10-22T09:35:00Z`).
- Namuna vaqti — agent soatidan. Soat siljishi paketdagi `sent_at` bilan aniqlanadi: `|core vaqti − sent_at|
  > 10 daqiqa` bo'lsa, butun paket shu farqqa surilib tuzatiladi va `clock_skew` belgisi qo'yiladi.
  Aks holda namuna vaqti o'zgartirilmaydi: core o'chib qaytganda 15 daqiqalik bufer (FR-AGT-007)
  o'z vaqtlari bilan yoziladi (P-02 da aniqlangan: namuna vaqtini "core vaqti bilan almashtirish"
  buferni buzardi). Tuzatishdan keyin 1 soatdan eski yoki 1 daqiqadan ilgari namuna rad etiladi.
- Agent hodisa tartibi uchun monoton `seq` raqamidan ham foydalanadi.

## 6.11. Kengaytirish nuqtalari

| Kengaytma | Qanday amalga oshadi |
|---|---|
| Yangi metrika | Agentda yangi kollektor yoki `custom` kollektor; core o'zgarmaydi (ADR-013) |
| Yangi tekshiruv turi | `probes` ilovasida yangi `Probe` kichik sinfi + prober ro'yxatdan o'tkazish |
| Yangi bildirishnoma kanali | `notify.channels` da `Channel` interfeysini amalga oshirish (`send`, `validate`) |
| Yangi alert shart turi | `alerts.conditions` da `Condition` interfeysi |
| Yangi integratsiya | Kiruvchi webhook/heartbeat endpointi (FR-INT-005) |
| Ikkinchi core (HA) | F3 dan keyin: bazada replika + ikkinchi core; hozir qamrovda emas (X-6) |
