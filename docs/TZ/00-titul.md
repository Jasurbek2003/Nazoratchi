# NAZORATCHI — Infratuzilma monitoringi platformasi

## Texnik topshiriq (TZ)

| | |
|---|---|
| **Hujjat turi** | Texnik topshiriq (Technical Specification) |
| **Loyiha ishchi nomi** | Nazoratchi (Nazoratchi Monitor) |
| **Versiya** | 1.20 (loyiha) |
| **Sana** | 2026-10-26 |
| **Holat** | Tasdiqlash uchun taqdim etilgan |
| **Buyurtmachi / mahsulot egasi** | Jasurbek (Avlo loyihalari egasi) |
| **Hujjat tili** | O'zbek (lotin), texnik atamalar va identifikatorlar asl holida |
| **Hujjat formati** | Markdown manba + Word (.docx) |

---

## 0.1. Hujjat tarixi

| Versiya | Sana | Muallif | O'zgarish |
|---|---|---|---|
| 0.1 | 2026-10-22 | Claude (loyiha yordamchisi) | Birinchi qoralama: tuzilma va inventar |
| 0.5 | 2026-10-22 | Claude | Funksional va nofunksional talablar, arxitektura |
| 1.0 | 2026-10-22 | Claude | To'liq nashr: ma'lumotlar modeli, API, UI, test, reja, ilovalar |
| 1.1 | 2026-10-26 | Claude | Loyiha nomi "Qarovul" dan "Nazoratchi" ga o'zgartirildi (QARORLAR.md, Q-06). Core va offsite S-00 da; S-03 ishlatilmaydi (QARORLAR.md) |
| 1.2 | 2026-10-26 | Claude | Q-12…Q-14 qarorlari: GCP IP yopilgan (`retired_ips`), Nazoratchi o'z zaxirasi `age` bilan shifrlanib Owner'ning shaxsiy Telegram chatiga yuboriladi, watchdog S-01 da (S-00 va S-01 bir-birini kuzatadi). `imraninc.com` loyihadan chiqarildi. NFR-SEC-010 M/F1 ga ko'tarildi |
| 1.3 | 2026-10-26 | Claude | P-02 natijalari: soat siljishi `sent_at` bilan aniqlanadi (6.10, 7.5.2, T-U-ING-04, -12…-14); JOIN li `rollup` agregati tasdiqlandi (8.4.2); siqilgan bo'lakka yozuv cheklovi (8.4.1); o'lchangan hajm 6.9 bayt/namuna (5.1.3); log maskalash regexi tuzatildi (14.9); R-102 hal bo'ldi |
| 1.4 | 2026-10-26 | Claude | E-01: `appctl` `state.json`/`_run.json` amalga oshirildi va sinaldi (10.3.1, 10.3.3, FR-INT-003 aniqlashtirildi: offsite `_run.json` da; `daily` `null` bo'lishi mumkin; haftalik `tar` xatosi endi zaxirani fail qiladi) |
| 1.5 | 2026-10-26 | Claude | E-02: `appctl list --json` / `status --json` amalga oshirildi va sinaldi (18.1 aniqlashtirildi: `state` ning `stopped`/`unknown` ma'nosi, `null` = olib bo'lmadi, xato JSON'i) |
| 1.6 | 2026-10-26 | Claude | E-03: heartbeat `appctl` ichiga qo'yildi (cron.d ko'p qatorli namuna ishlamaydi; token `appctl.secret` 0600 da), `setup.sh --heartbeat-url`; 9.14 va 10.3.5 yangilandi. Buzuq `.appctl` endi loyihani `fail` qiladi |
| 1.7 | 2026-10-27 | Claude | F1 S1 topilmalari: sessiya jadvali (`user_sessions`) va `public_id` unique emasligi (8.8); `__Host-` cookie faqat prod'da (14.3.4); `/healthz` ga loopback host orqali kirish (15.4, 15.5); prototip agent `enroll` (7.5.1) |
| 1.8 | 2026-10-27 | Claude | F1 S2: Go agent (system/disk/net) va Telegram kanali amalga oshirildi. Aniqlashtirishlar: core xatosi `{"error": {...}}` (7.5.1); core buyruqlarini agent hali bajarmaydi (7.5.3); `notifications.payload`/`next_attempt_at` (8.8); kanal API: `config` faqat yoziladi, `config_masked`, test `502`, tarix sahifalash (9.9); qayta urinish jadvali (12.9.0); `notifier` servisi va `TELEGRAM_API_BASE` (15.4, 15.5) |
| 1.9 | 2026-10-27 | Claude | F1 S3: alert dvigateli amalga oshirildi (16 standart qoida). Aniqlashtirishlar: `state` manbalari va "ma'lumot yo'q" (12.3.5), `of` kaliti (12.3.6), ahamiyat bo'yicha bostirish va S3 da bo'lmagan qismlar (12.5), incident boshlanishi = shart rost bo'la boshlagan vaqt (6.7.2), `pending` uzluksizligi (6.7.1), qo'shimcha ustunlar (8.7), `evaluator`/`notifier` komandalari va healthcheck (15.4) |
| 1.10 | 2026-10-27 | Claude | F1 S4: reyestr CRUD (serverlar, loyihalar, domenlar), seed, prober (HTTP/TCP), Telegram tugmalari. Aniqlashtirishlar: pauza `until`/sabab (8.3, 9.3), port to'qnashuvi va keyingi bo'sh port qoidasi (9.4), probe `DELETE` = arxiv va `allow_private` faqat Owner (9.6), webhook sirlari va `callback_data` formati (9.12), prober amalga oshirilishi: IP-pinning, qayta tekshiruv `next_run_at` orqali (6.8), `primary` kaliti (18.4), AL-049/049H/085 va `probe`/`prober` manbalari (12.3.5, 12.7), `prober`, `TELEGRAM_WEBHOOK_SECRET`, seed (15.4, 15.5) |
| 1.11 | 2026-10-27 | Claude | F1 S5: TLS va DNS tekshiruvlari, sertifikat/DNS/konteyner qoidalari (AL-035, 036, 057-060, 062, 063), Go agent `docker` kollektori, metrikalar so'rovi API (B4). Aniqlashtirishlar: kutilgan konteyner agent xotirasida (7.4.4, 11.5.1), TLS/DNS amalga oshirilishi (6.8), `cert_status`/`dns_results`/`dns_changes`/`settings` (8.5), so'rov API qoidalari va `null` bo'shliqlar (9.5), `/certs/`, `/domains/{id}/dns`, konteyner va fayl tizimi endpointlari (9.3, 9.4, 9.6), `when` sharti va `cert`/`dns` manbalari (12.3), WHOIS/RDAP F2 ga qoldi |
| 1.12 | 2026-10-27 | Claude | F1 S6: zaxira monitoringi (B10) va agent `systemd`/`backup` kollektorlari (B5c). Aniqlashtirishlar: `systemd`/`backup`/`beat` amalga oshirilishi (7.4.5, 7.4.6), `projects.backup` siyosati va `backup_runs` agent metrikalaridan hosil bo'lishi (8.3, 8.6), `/backups/` API shakli (9.7), `backup` state manbasi va AL-068…072, 075 (12.3.5, 12.7.10) |
| 1.13 | 2026-10-28 | Claude | F1 S7/S8: o'zini kuzatish (B11), mustaqil watchdog (S-01), o'z zaxirasi, agent `install.sh`/`uninstall`, frontend asosi (S8). Aniqlashtirishlar: `/healthz` (liveness), `/readyz` (tayyorlik), `/metrics` (ichki) va `WATCHDOG_URL` ping oqimi (9.15), AL-084 watchdog orqali amalga oshirilishi, AL-090/091 o'z zaxirasi qoidalari (12.7), `NAZORATCHI_BACKUP_AGE_PUBKEY`, `METRICS_TOKEN`, `MINISIGN_PUBKEY`, `AGENT_DIST_DIR` (15.5), `install.sh` imzo fayli `SHA256SUMS.minisig` (7.7.1), `GET /agent/v1/<fayl>` (9.14), `warning` rangi `#c28400` (13.x, WCAG 3:1) |
| 1.14 | 2026-10-28 | Claude | F1 S9: frontend sahifalari (zaxira, domen, incident, texnik ish/silence, sozlamalar) va B12 deploy. Aniqlashtirishlar: prod compose `evaluator`/`prober`/`notifier`/`self-backup` servislari, Celery yo'q (15.4); backend image build context repo ildizi, `install.sh` va `seed` image ichida (15.3, 15.4); frontend image `nginx-unprivileged` 8080 (15.4); `/metrics` va `/readyz` nginx'da tashqariga berilmaydi, SSE `stream` yo'q (15.6); `deploy/bootstrap.sh` (15.7); `release.yml` va CI joblari (15.10); RB-044 haqiqiy `restore_self_backup` buyruqlari bilan, runbook'lar `docs/runbooks/` da (15.9, 18.2); mobil pastki panel 5 ustun (13.9) |
| 1.15 | 2026-10-28 | Claude | F1 S10: sinov va mustahkamlash (B13). Aniqlashtirishlar: `evaluator` va `prober` leader qulfi `pg_try_advisory_lock` bilan amalga oshirildi (15.4); ulanish `connect_timeout=5`, baza o'chiq bo'lsa `/healthz` 5 s da `503` (16.6, T-C-01); noma'lum `/api/`, `/ingest/`, `/agent/` yo'llari JSON `404`, `500` tafsilotsiz JSON (9.1.1); 14.13 va 16.5–16.7 bandlari holati `docs/sinov/B13-natijalar.md` da; `tools/simulator` yuklama simulyatori (16.9) |
| 1.16 | 2026-10-28 | Claude | F1 S10 davomi: restore drill (UC-11, FR-BKP-016) F2 dan F1 ga olindi. Aniqlashtirishlar: `restore_drills` jadvali va `/backups/drills` API (9.7), zaxira jadvali/kartasida `drill` bloki — "hech qachon" va muddati o'tgani ko'rinadi (R-117); frontend: karta sahifasida forma va tarix, ro'yxatda drill belgisi (13, SCR-07). AL-081…083 F2 da qoladi |
| 1.17 | 2026-10-28 | Claude | F1 S10 davomi: AL-081, AL-082, AL-083 (restore drill muddati/natijasi) F2 dan F1 ga olindi, F1 alertlar soni 32 → 35 (12.7.10, 12.9). Aniqlashtirishlar: yangi `drill` state manbasi (`due_soon`, `overdue`, `failed`), faqat faol, ko'chirilgan `expect_daily` loyihalar; AL-081 muddat o'tmaguncha yonadi, o'tgach AL-082 (takroriy shovqin yo'q); hech qachon drill o'tkazilmagan loyiha `overdue`; muvaffaqiyatsiz drill muddat taymerini qayta boshlamaydi; RB-034 to'ldirildi |
| 1.18 | 2026-10-29 | Claude | F2 S11 (1/2): agent kengaytmalari. Host: inode (FR-HST-008), jarayonlar/fd/swap faolligi/OOM (FR-HST-012), `diskio`, reboot va kernel (FR-HST-009); Docker: `cpu_percent`, `mem_*`, `log_bytes`, `system df` (FR-DKR-003/006/007); mahalliy sertifikat skaneri (FR-TLS-005, certbot deploy-hook + `certs.json`). Aniqlashtirishlar: alohida `reboot` kollektori (5 daqiqa, 7.4.8), `cert_*` da `path` belgisi yo'q, `docker_container_mem_limit_bytes` 0 = cheksiz, docker-socket-proxy `SYSTEM=1`, bir konteyner ~11 qator (kardinallik, 7.4.4). Core: `procs_total`, `threads_total`, `fs_inodes_total` gauge, `*_bytes_per_sec` birligi `bayt/s`. Qolgan S11: o'z-o'zini yangilash (FR-AGT-008), versiya hisoboti, soat farqi |
| 1.19 | 2026-10-29 | Claude | F2 S11 (2/2): agentning o'z-o'zini yangilashi (FR-AGT-008, NFR-SEC-012, T-U-SEC-11). Aniqlashtirishlar: yangilanish ikki bosqichli (agent yuklab imzoni tekshiradi va `update/` ga qo'yadi; root `ExecStartPre=+` `apply-update` uni noldan qayta tekshirib almashtiradi), chunki agent root emas va `/usr/local/bin` unga yopiq; `VERSION` ham imzolangan `SHA256SUMS` ichida (core versiyani soxtalashtira olmaydi, orqaga qaytarish rad etiladi); tasdiq/rollback (10 daqiqa), qaytarilgan versiya qayta urinilmaydi, o'rov skripti binar umuman ishlamasa ham rollback qiladi; `agent_update_rejected` alohida hodisa emas, `agent_update_rejected_total` hisoblagichi. API: `POST/DELETE /servers/{id}/agent-update` (faqat owner), `servers.agent_update_to`, host voqealari `agent_updated`/`agent_downgraded`/`agent_update_requested`/`agent_update_cancelled`. Reliz: `VERSION`, `MINISIGN_PUBKEY` repo o'zgaruvchisi. Qolgan S11: versiya hisoboti paneli (FR-AGT-011), soat farqi (FR-AGT-012), paneldagi 'Yangilash' tugmasi |
| 1.20 | 2026-10-29 | Claude | F2 S11 yakuni: versiya hisoboti va eskirgan agent belgisi (FR-AGT-011), soat farqi (FR-AGT-012), paneldagi yangilash tugmasi. Aniqlashtirishlar: faktlarga `agent_build_time` va `go_version` qo'shildi (versiya `X-Nazoratchi-Agent` sarlavhasida); server obyektida `agent_latest`/`agent_outdated`/`agent_update_to`, tafsilotda `clock_skew_seconds`; server sahifasida "Yangilash kerak" belgisi, owner uchun "Yangilash"/"Bekor qilish" va "Soat siljigan" belgisi (chegara 5 s); agent soat farqini 10 daqiqada bir marta ogohlantiradi. `/api/v1/version` (9.x) hali yo'q: `agent_latest` server obyektida beriladi |

Hujjatga o'zgartirish kiritish tartibi: har bir o'zgarish yangi qator sifatida shu jadvalga
yoziladi; talab identifikatorlari (FR-..., NFR-...) hech qachon qayta ishlatilmaydi,
o'chirilgan talab "BEKOR QILINGAN" deb belgilanadi, raqami saqlanadi.

## 0.2. Mundarija

| № | Bo'lim | Fayl |
|---|---|---|
| 0 | Titul, atamalar, hujjatdan foydalanish | 00-titul.md |
| 1 | Kirish: maqsad, muammo, doira, KPI | 01-kirish.md |
| 2 | Hozirgi infratuzilma inventari | 02-inventar.md |
| 3 | Foydalanuvchilar, rollar va foydalanish stsenariylari | 03-foydalanuvchilar.md |
| 4 | Funksional talablar | 04a-funksional-talablar.md, 04b-funksional-talablar.md |
| 5 | Nofunksional talablar | 05-nofunksional-talablar.md |
| 6 | Tizim arxitekturasi | 06-arxitektura.md |
| 7 | Agent spetsifikatsiyasi va metrikalar katalogi | 07-agent-va-metrikalar.md |
| 8 | Ma'lumotlar modeli | 08-malumotlar-modeli.md |
| 9 | API spetsifikatsiyasi | 09-api.md |
| 10 | Zaxira nusxalar (backup) monitoringi | 10-backup-monitoring.md |
| 11 | Loyiha, servis, domen va sertifikat monitoringi | 11-servis-monitoring.md |
| 12 | Alert (ogohlantirish) tizimi | 12-alert-tizimi.md |
| 13 | Foydalanuvchi interfeysi | 13-interfeys.md |
| 14 | Xavfsizlik | 14-xavfsizlik.md |
| 15 | O'rnatish, deploy va ekspluatatsiya | 15-deploy.md |
| 16 | Test rejasi va qabul mezonlari | 16-test-rejasi.md |
| 17 | Loyiha rejasi, resurslar va xavflar | 17-reja-va-xavflar.md |
| 18 | Ilovalar (JSON sxemalar, runbook'lar, tekshiruv sxemalari, seed reyestr, sanoq) | 18a-ilovalar.md, 18b-ilovalar.md |

## 0.3. Hujjatdan foydalanish qoidalari

1. **Talablar identifikatori.** Har bir talab noyob kodga ega: `FR-<MODUL>-<NNN>`
   (funksional), `NFR-<TOIFA>-<NNN>` (nofunksional), `US-<NNN>` (foydalanuvchi hikoyasi),
   `AL-<NNN>` (alert qoidasi), `RB-<NNN>` (runbook), `R-<NNN>` (xavf), `T-<NNN>` (test).
2. **Ustuvorlik (MoSCoW).** Har talabda ustuvorlik belgisi bor:
   - **M** (Must) — usiz tizim qabul qilinmaydi;
   - **S** (Should) — muhim, lekin birinchi reliz keyinga qoldirilishi mumkin;
   - **C** (Could) — foydali, vaqt bo'lsa;
   - **W** (Won't) — bu versiyada qilinmaydi, kelajak uchun qayd etilgan.
3. **Bosqich (Faza).** Har talab qaysi bosqichda amalga oshirilishi ko'rsatiladi:
   F1 (MVP), F2 (kengaytirilgan), F3 (yetuklik). Bosqichlar 17-bo'limda tushuntirilgan.
4. **Kalit so'zlar.** "kerak" (shall) — majburiy; "tavsiya etiladi" (should) — tavsiya;
   "mumkin" (may) — ixtiyoriy. Raqamli chegaralar (masalan, 60 soniya) o'zgartirilishi mumkin
   bo'lgan sozlamalar bo'lsa, "standart qiymat" deb yoziladi.
5. **Misollar.** Hujjatdagi IP-manzillar, domenlar va portlar 2026-10-22 holatiga ko'ra
   haqiqiy infratuzilmadan olingan. Parollar, tokenlar va kalitlar hujjatga **hech qachon**
   kiritilmaydi; ular o'rnida `***` yoki `<TOKEN>` yoziladi.

## 0.4. Atamalar va qisqartmalar

| Atama | Ma'nosi |
|---|---|
| **Agent** | Kuzatiladigan serverda ishlaydigan kichik dastur; metrikalarni yig'ib markazga yuboradi |
| **Markaziy server (Core)** | Metrikalarni qabul qiladigan, saqlaydigan, alert hisoblaydigan va UI beradigan server |
| **Host** | Kuzatiladigan jismoniy yoki virtual server (VPS) |
| **Loyiha (Project)** | Bitta mahsulot: bir yoki bir nechta servis, domen va bazadan iborat (masalan, Nazar, BiznesRadar) |
| **Servis (Service)** | Loyihaning ishlaydigan qismi: Docker konteyner, systemd unit yoki nginx sayti |
| **Metrika (Metric)** | Vaqt bo'yicha o'zgaruvchi son (CPU foizi, bo'sh xotira va h.k.) |
| **Namuna (Sample)** | Metrikaning bitta vaqtdagi qiymati |
| **Tekshiruv (Check)** | Faol (active) tekshirish: HTTP so'rov, TCP ulanish, DNS so'rov, sertifikat muddati |
| **Alert** | Shartga asoslangan ogohlantirish (masalan, "disk 85% dan oshdi") |
| **Incident** | Bir yoki bir nechta alertdan tashkil topgan voqea, yechilguncha ochiq turadi |
| **Heartbeat** | Agentning "tirikman" signali |
| **Retention** | Ma'lumotni saqlash muddati |
| **Downsampling** | Eski ma'lumotni siyraklashtirib (o'rtachalab) saqlash |
| **RPO** | Recovery Point Objective — ma'lumotning yo'qolishi mumkin bo'lgan maksimal vaqt |
| **RTO** | Recovery Time Objective — tiklash uchun maksimal vaqt |
| **SLO / SLA** | Xizmat darajasi maqsadi / kafolati |
| **MTTR / MTTD** | Tiklashning / aniqlashning o'rtacha vaqti |
| **appctl** | `/usr/local/bin/appctl` — serverdagi loyihalarni boshqarish skripti (mavjud) |
| **RBAC** | Rolga asoslangan kirish nazorati |
| **TSDB** | Vaqt qatorlari bazasi (time-series database) |
| **SSE** | Server-Sent Events — serverdan brauzerga bir yo'nalishli oqim |
| **ACME / HTTP-01** | Let's Encrypt sertifikat olish protokoli / tekshiruv usuli |
| **PROXY protocol** | TCP proksi orqali haqiqiy mijoz IP sini uzatish protokoli |
| **Runbook** | Muayyan alert chiqqanda bajariladigan qadamma-qadam yo'riqnoma |
| **Maintenance window** | Rejalashtirilgan ishlar vaqti; alertlar jim qilinadi |
