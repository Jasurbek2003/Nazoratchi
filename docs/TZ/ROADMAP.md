# Nazoratchi — Roadmap (F0 → F1 → F2 → F3)

Manba: TZ 17-bo'lim (reja, baho), 12.7 (alert katalogi), 18.7 (talablar sanog'i).
Baho: bir dasturchi, haftasiga 4 samarali kun (TZ 17.3.5), ±30%. Sprint = 2 hafta = 8 kishi-kun.
Boshlanish sanasi shartli: **2026-10-26 (dushanba)**. Sana siljisa, haftalar o'zgarmaydi.

## 1. Umumiy ko'rinish

| Faza | Kishi-kun | Sprintlar | Haftalar | Tugash (shartli) | Natija |
|---|---|---|---|---|---|
| Hafta 0 | — | — | 0 | 2026-10-30 | Qarorlar, oraliq himoya |
| F0 — Tayyorgarlik | 7.5 | S0 | 1–2 | 2026-11-08 | Protokol prototipi, `appctl` o'zgartirishlari |
| F1 — MVP | 80 | S1–S10 | 3–22 | 2027-03-28 | 35 alert, Telegram, asosiy panel, UAT tayyor |
| F1 UAT (S-01 da 14 kun) | — | F2 bilan parallel | 23–24 | 2027-04-11 | UAT-01…12 |
| F2 — Kengaytirilgan | 73 | S11–S19 | 23–40 | 2027-08-01 | 2FA, hisobotlar, drill, offsite 2-daraja, ru/en |
| F3 — Yetuklik | 32 | S20–S23 | 41–48 | 2027-09-26 | Status sahifa, eskalatsiya, avto-drill, supply-chain |
| **Jami** | **≈ 193** | **24** | **48** | **2027-09-26** | |

Bufer bilan (TZ R-111: +20%): **≈ 58 hafta, 2027-yil dekabr boshi**. Ikki dasturchi bilan: ≈ 25 hafta.

```
Hafta:  0 1 2 | 3 ......... 22 | 23 ............ 40 | 41 ..... 48
        H0 F0 |      F1 (MVP)   |  F2 (kengaytirish) |  F3
              M0   M1   M2   M3 M4        M5                M6
```

## 2. Hafta 0 — boshlashdan oldin (bu hafta)

Bular kod emas, lekin F0 ni boshlash uchun shart (TZ 17.8, 17.10, 17.11).

| № | Ish | Nega | TZ |
|---|---|---|---|
| 1 | **Uptime Kuma** o'rnatish (HTTP/TLS/TCP + Telegram), 1–2 soat | F1 gacha serverlar kuzatuvsiz qolmasin | 17.10/1 |
| 2 | **`OFFSITE` zaxirani sozlash** (S-00 ga `rsync`, `/srv/backups/main-server`) | Eng katta ochiq xavf R-001; Nazoratchi'ga bog'liq emas | 2.6, RB-033 |
| 3 | S-00 (`185.214.135.9`) ni tozalab qayta o'rnatish (Ubuntu 24.04, SSH kalit, `ufw`, Docker), Contabo snapshot | Core + S-01 uchun offsite shu yerda (Q-02, Q-07) | 15.2 |
| 4 | Q-05: `nazoratchi.avlo.ai` tasdiqlash; watchdog uchun subdomen (S-01); Telegram botlari va `/start` (zaxira chati) | DEP-02, DEP-03 | 17.11 |
| 4a | `lutfanai.uz`, `lutfan.israilov.uz` va (mijoz) `*.wmg.uz` DNS ni o'chirilgan GCP IP dan S-01 ga yo'naltirish; `avloai.uz` ni ham | GCP IP mavjud emas, bu saytlar hozir ishlamaydi | 11.4 |
| 5 | Q-08: `appctl` ga o'zgartirish kiritishga rozilik | E-01…E-03 shartiga | R-109 |
| 6 | Q-10: S-02 (aaclub) serveriga agent o'rnatishga ruxsat | M3 da kerak | 15.8 |
| 7 | Q-04: Telegram guruh va ikkinchi kontakt; ikkita bot (Nazoratchi + watchdog) | DEP-03, ADR-014 | 17.11 |
| 8 | GitHub repo (monorepo) va CI uchun hisob | DEP-08 | 15.3 |
| 9 | Q-11: S-01 da kernel `-147` reboot — **faqat** offsite + snapshotdan keyin | R-002, RB-015 | 17.11 |

**Chiqish mezoni:** S-00 qayta o'rnatilgan va snapshot olingan, offsite ishlaydi, Uptime Kuma xabar beryapti, Q-12…Q-14 yopilgan.

## 3. F0 — Tayyorgarlik (hafta 1–2, S0, 7.5 kun)

Maqsad: texnik xavflarni erta yo'qotish (R-102 Timescale, R-103 Go, R-109 `appctl`).

| Ish | Kun | Natija |
|---|---|---|
| P-01 Repo, CI skeleti (lint, test), `docker-compose.dev.yml` | 2.0 | Yashil CI |
| P-02 Python prototip agent (`psutil`) + minimal ingest + Timescale agregat sinovi | 3.0 | Metrika grafikda; ierarxik agregatlar ishlaydi; `rollup` filtri sinovi |
| E-01 `appctl`: `state.json`, `_run.json` | 1.0 | Zaxira natijasi mashinada o'qiladi |
| E-02 `appctl`: `list --json`, `status --json` | 1.0 | JSON chiqish (18.1) |
| E-03 Cron heartbeat chaqiruvi | 0.5 | Cron signal yuboradi |

**M0 (hafta 2) — Protokol prototipi.** Demo: bitta server grafigi brauzerda, `appctl backup` `state.json` yozadi.

**Holat (2026-10-26):** P-01 (repo, CI) va P-02 (prototip agent, ingest, grafik, Timescale sinovi; R-102 hal bo'ldi) bajarildi — [`docs/P-02-timescale-sinov.md`](../P-02-timescale-sinov.md). E-01 (`appctl` `state.json`/`_run.json`) bajarildi — [`deploy/appctl-patches/`](../../deploy/appctl-patches/README.md). E-02 (`list --json`, `status --json`) bajarildi. E-03 (heartbeat) bajarildi. **F0 ning barcha ishlari tugadi**: M0 mezonlari bajarilgan, qaror nuqtasi №1 (F1 ga o'tish) turibdi.

**Holat (2026-10-28, S9):** B9 frontend: zaxira, domen (DNS, sertifikat), incident (ack, izoh, qo'lda yopish), texnik ish va silence, sozlamalar (Telegram kanallari, qoidalar) sahifalari; 171 test. B12: prod compose, nginx, `bootstrap.sh`, backend/frontend image'lari, `release.yml`, CI kengaytmasi, 34 runbook fayli. **Sinalmagan:** haqiqiy ghcr release, bo'sh serverda `bootstrap.sh`, brauzerda qo'lda ko'rik. **Kechiktirildi:** restore drill formasi va offsite solishtirish UI (backend API yo'q), domen muddati ustuni va "kesib o'tish yordamchisi", incident runbook bloki va sabab tahriri, kanal `quiet_hours`, texnik ish nazorat ro'yxati.

**Holat (2026-10-29, S11, 2/2):** FR-AGT-008 o'z-o'zini yangilash: agent `internal/update` (minisign `Ed`/`ED`, imzolangan `VERSION`, faqat oldinga, `staged`), root `apply-update` (`ExecStartPre=+`, noldan qayta tekshiruv, tasdiq/rollback, o'rov skripti), core `POST/DELETE /servers/{id}/agent-update` va ingest `update` buyrug'i, `release.yml` (`VERSION`, `MINISIGN_PUBKEY`). Haqiqiy `minisign` bilan e2e: yangilash, tasdiq, rollback, begona kalit, buzuq binar. **Qolgan S11:** FR-AGT-011 (eskirgan agentlar belgisi), FR-AGT-012 (soat farqi), paneldagi 'Yangilash' tugmasi. **Sinalmagan:** haqiqiy `systemd` (`ExecStartPre=+`, `Restart=always`) va haqiqiy GitHub reliz oqimi.

**Holat (2026-10-29, S11, 1/2):** C1/C2: agent kollektorlari — inode, jarayonlar, fd, swap faolligi, OOM hisoblagichi, `diskio`, reboot/kernel; Docker `cpu_percent`/`mem_*`/`log_bytes`/`system df`; mahalliy sertifikat skaneri (certbot deploy-hook + `certs.json`). Haqiqiy `docker-socket-proxy` bilan tekshirildi (`stats`, `/system/df`, `/info` ruxsat; `POST` 403). **Qolgan S11:** o'z-o'zini yangilash (FR-AGT-008), versiya hisoboti (FR-AGT-011), soat farqi (FR-AGT-012). **Keyingi sprintlarga:** yangi metrikalar uchun alertlar (S13/S14: inode, reboot kutilmoqda, unhealthy/OOM, sertifikat muddati) va paneldagi ko'rsatish (S16). **Sinalmagan:** haqiqiy Linux xostda `diskio`/`reboot`/inode (testlar soxta `/proc` bilan), certbot'ning haqiqiy yangilanishi.

**Holat (2026-10-28, S10):** B13: xavfsizlik testlari (RBAC matritsasi barcha `/api/v1/` yo'nalishlari bo'yicha, XSS/SQLi, sirlar, cookie; 19 test), chaos testlari (fuzz ingest, kesh yo'qolishi, leader), yuklama simulyatori `tools/simulator`; backend 449 test. Topilib tuzatilgan: JSON 404/500, DB `connect_timeout` (baza o'chiqda `/healthz` osilardi), `evaluator`/`prober` leader qulfi. **Sinalmagan (haqiqiy muhit kerak):** ZAP, testssl, `nmap`, T-C-03..13, T-P-02..10, 14 kunlik UAT. **UAT to'sig'i** (restore drill kiritish) keyin yopildi: `/backups/drills` API, karta sahifasidagi forma va tarix, ro'yxatda drill belgisi; AL-081…083 keyin F1 ga olindi (35 ta F1 alert). Tafsilot: `docs/sinov/B13-natijalar.md`.

**Holat (2026-10-28, S7/S8):** B11: `/healthz`, `/readyz`, `/metrics`, evaluator ping (AL-084 watchdog orqali), o'z zaxirasi (`age` + Telegram, `self_backup`/`restore_self_backup`, AL-090/091). B5d: `install.sh` (minisign, idempotent, docker-socket-proxy), `uninstall`, core'da `/install.sh` va `/agent/v1/`. Mustaqil Python watchdog (`watchdog/`, 12 test). F1 S8: React/TS frontend asosi (kirish, dashboard, loyiha, server, incident; 118 test). **Sinalmagan:** haqiqiy `systemctl`/Docker proxy/Telegram bot, brauzerda qo'lda ko'rik. Qolgan: backend Docker image'ida `install.sh` yo'q (context `backend/`, B12), frontend sahifalari (zaxira, alertlar, sozlamalar) keyingi sprintda.

**Holat (2026-10-27, S6):** B5c agent: `systemd` (unit holati, cron heartbeat fayllari, `beat` buyrug'i) va `backup` (appctl `state.json` + papka skaneri + offsite) kollektorlari. B10 zaxira monitoringi: loyiha siyosati, `BackupRun` tarixi (metrikalardan), yosh/muvaffaqiyatsizlik/hajm anomaliyasi qoidalari (AL-068…072, 075), `/backups/` API. Butun zanjir sinaldi (appctl formatidagi daraxt -> agent -> ingest -> API -> alert). Haqiqiy `systemctl` va haqiqiy `appctl` chiqishi bilan hali sinalmagan. Kechiktirildi (F2): `certs` kollektori, `gzip -t` yaxlitligi, offsite solishtirish (AL-076…080), restore drill (AL-081…083).

**Holat (2026-10-27, S5):** B6 prober tugadi (F1 doirasi): TLS (muddat, zanjir, SAN) va DNS (ko'p resolver, `ns:auto`, o'zgarish tarixi, yopilgan IP), AL-057…060, 062, 063; haqiqiy internetga qarshi sinaldi (muddati o'tgan va noto'g'ri host sertifikatlari, haqiqiy resolverlar). B5b Go agent `docker` kollektori (haqiqiy Docker daemon va butun zanjir bilan sinaldi), AL-035/036. B4 metrikalar API (`query` bo'shliqlar bilan, `latest`, `names`, `top`) + server konteynerlari va fayl tizimlari. Kechiktirildi: WHOIS/RDAP va AL-066/067 (katalogda F2), resurs sarfi (`docker stats`) va `system/df` (F2).

**Holat (2026-10-27, S4):** B2 reyestr: serverlar (PATCH, pauza `until` bilan, arxiv, voqealar, tokenlar), loyihalar va domenlar (CRUD, port to'qnashuvi va keyingi bo'sh port, arxiv, avto-tekshiruv), `seed_registry` (`seed/inventory.yaml`). B6 prober (qisman): HTTP va TCP, SSRF filtri + IP-pinning, tasdiqlash qoidasi (3 ketma-ket xato), API, AL-049/049H/085; haqiqiy internetga qarshi sinaldi (to'g'ri/buzuq sertifikat, noto'g'ri host, ichki manzil to'silishi). B8: Telegram tugmalari ("Qabul qilaman", "1 soat jim") va webhook (HMAC imzo). Qolgan: TLS/DNS/WHOIS tekshiruvlari va sertifikat/DNS qoidalari (S5), reyestr import/eksport (F2), `/projects/{id}/status` (frontend bilan).

**Holat (2026-10-27, S3):** B7 alert dvigateli: shartlar (threshold, absent, rate, forecast, state, and/or/not), holat mashinasi, incident (bog'lash, ahamiyat oshishi, ack), bostirish (pause, maintenance, silence, host o'chdi, ommaviy jimlik, ahamiyat bo'yicha), takroriy eslatmalar, "Tiklandi" xabari, 16 standart qoida, API (qoidalar, incidentlar, silence, maintenance). **M1 mexanikasi haqiqiy Go agent bilan sinaldi** (soxta Telegram bilan): agent to'xtadi -> 5 daqiqada AL-002 (high), SSH o'chdi -> 16 s da AL-001 (critical) o'sha incident ichida, hammasi qaytdi -> "Tiklandi". Qolgan: prober (AL-001 uchun TCP:22 hozir minimal tekshiruv), Telegram tugmalari (S4), guruhlash/titrash/gisterezis (F2).

**Holat (2026-10-27, S2):** Go agent (`agent/`: system, disk, net kollektorlari, diskdagi navbat, backoff, enroll, `agent_*` metrikalari) haqiqiy backend bilan sinaldi (enroll, 116 namuna bazada, toza to'xtash); CI da `go vet`, `staticcheck`, `go test -race`, `govulncheck`, amd64+arm64. B8: Telegram kanali (sirlar AES-256-GCM bilan shifrlangan), xabar shabloni, 5 urinishli qayta yuborish, kanal API va `notify_worker`. **Soxta Bot API bilan sinaldi, haqiqiy Telegram bot bilan hali emas.** Qolgan: agent kollektorlari diskio/docker/systemd/backup/certs/ssh/apt (S5-S7), core buyruqlari, Telegram tugmalari/webhook (S4), email zaxira kanali (F2).

**Holat (2026-10-27):** F1 / S1 bajarildi: B1 (auth, sessiyalar, RBAC, audit, to'liq reyestr modellari, Dockerfile va CI da image build) va B3 ning S1 qismi (`/ingest/v1/enroll`, `/goodbye`, `/hb/<token>`). `appctl heartbeat` ishlayotgan backend'ga qarshi sinaldi; prototip agent `enroll` oqimini biladi. Navbatda: S2 (Go agent, Telegram) va B2 (reyestr CRUD, S4 dan oldinga olinishi mumkin). `appctl`/`setup.sh` jonli serverlarga hali qo'llanmagan.

> **Qaror nuqtasi №1 (R-118).** F0 oxirida: Timescale ishladimi? Go agent uchun tayyormisiz?
> Ish hajmi bahosi o'zgardimi? Shundan keyin F1 ga to'liq kirishiladi.

`appctl` o'zgartirishlari: avval nusxada sinang, `|| true` bilan, keyin `appctl backup all` ni qo'lda tekshiring (R-109).

## 4. F1 — MVP (hafta 3–22, S1–S10, 80 kun)

Maqsad: server o'chsa, disk to'lsa, sayt tushsa, zaxira buzilsa, sertifikat tugasa — Telegram'da xabar.
Yondashuv: avval yupqa vertikal kesim (agent → ingest → alert → Telegram), keyin kengaytirish.

| Sprint | Hafta | Ish paketlari (kun) | Natija |
|---|---|---|---|
| S1 | 3–4 | B1 Core skeleti (5), B3 Ingest (3/4) | Django, modellar, auth, ingest |
| S2 | 5–6 | B3 (1), B5a Agent: tizim (4/6), B8 Telegram (3/4) | Go agent CPU/RAM/disk yuboradi; Telegram xabar |
| S3 | 7–8 | B5a (2), B7 Alert dvigateli (6/7) | Holat mashinasi, incident, bostirish, asosiy qoidalar |
| S4 | 9–10 | B7 (1), B8 (1), B2 Reyestr (4), B6 Prober (2/6) | Reyestr + seed, ack tugmasi |
| S5 | 11–12 | B6 (4), B5b Agent: Docker (3), B4 Metrika so'rovlari (1/3) | HTTP/TLS/DNS tekshiruvlari, Docker |
| S6 | 13–14 | B4 (2), B5c systemd/zaxira/sertifikat (3), B10 Zaxira monitoringi (3/4) | Zaxira kartasi, `state.json` o'qiladi |
| S7 | 15–16 | B10 (1), B5d `install.sh` (3), B11 O'zini kuzatish (3), B9 Frontend (1/14) | Watchdog (S-01), o'z zaxirasi (`age` + Telegram), bir buyruqli o'rnatish |
| S8 | 17–18 | B9 Frontend (8) | Dashboard, serverlar, loyihalar |
| S9 | 19–20 | B9 (5), B12 Deploy va hujjat (3/5) | Zaxira, domenlar, incidentlar, sozlamalar |
| S10 | 21–22 | B12 (2), B13 Sinov va mustahkamlash (6) | Yuklama, chaos, xavfsizlik, UAT tayyor |

Eslatma: M1 dan boshlab S-00 ga agent **qo'lda** o'rnatiladi (`install.sh` S7 da tayyor bo'ladi).

### Muhim bosqichlar

| Bosqich | Hafta | Sana | Mezon / demo |
|---|---|---|---|
| **M1 — Birinchi alert** | 8 | 2026-12-20 | sinov serverida (S-02 yoki vaqtinchalik VM) agentni to'xtatib/serverni o'chirib, Telegram'da AL-002/AL-001 |
| **M2 — Faol tekshiruvlar va zaxira** | 14 | 2027-01-31 | Domen/sertifikat/zaxira holati panelda, Docker ko'rinadi |
| **M3 — Panel va ishonchlilik** | 20 | 2027-03-14 | To'liq F1 paneli, watchdog (S-01), o'z zaxirasi (Telegram); S-00 va S-02 da agentlar |
| **M4 — F1 qabul (UAT)** | 22–24 | 2027-04-11 | S-01 da agent, 14 kun uzluksiz kuzatuv, UAT-01…12 |

### F1 chiqish mezonlari
- 35 ta F1 alert yoqilgan va har biri sinalgan (rost va yolg'on holat).
- UAT-03…UAT-07: 3 server 14 kun bo'shliqsiz, server o'chirish ≤ 2 daqiqa, soxta alert ≤ 5%.
- T-P-01, T-P-02, T-P-10 (yuklama, agent resursi) mezonlari bajarilgan.
- Zaxira va tiklash sinovi (T-DEP-05), xavfsizlik ro'yxati (14.13) o'tgan.
- Agentlar tarqatish tartibi: S-00 → S-02 → S-01 (15.8). S-01 da 24 soat kuzatuv.
- 4 haftalik "yumshoq rejim" (faqat kunlik xulosa) — soxta alertlarni sozlash (R-105).
- Uptime Kuma o'chiriladi yoki ikkilamchi tekshiruv bo'lib qoladi.

> **Qaror nuqtasi №2.** Hafta 14 (M2): F1 jadvaldan ortda qolayotgan bo'lsa, F2 dan nima
> kesilishini shu yerda hal qiling (Could/Should talablar).

## 5. F2 — Kengaytirilgan (hafta 23–40, S11–S19, 73 kun)

F1 UAT bilan parallel boshlanadi (UAT ko'proq kuzatuv, kod kam).

| Sprint | Hafta | Ish paketlari (kun) |
|---|---|---|
| S11 | 23–24 | C1 Agent kengaytmalari (6), C2 Docker (2/4) |
| S12 | 25–26 | C2 (2), C3 Tekshiruv kengaytmalari (6/8) |
| S13 | 27–28 | C3 (2), C4 Alert kengaytmalari (6/9) |
| S14 | 29–30 | C4 (3), C5 Bildirishnoma (5/6) |
| S15 | 31–32 | C5 (1), C6 Zaxira kengaytmalari (7) |
| S16 | 33–34 | C7 Frontend F2 (8/15) |
| S17 | 35–36 | C7 (7), C8 Xavfsizlik (1/6) |
| S18 | 37–38 | C8 (5), C9 Hisobotlar (3/4) |
| S19 | 39–40 | C9 (1), C10 Operatsion (7/8) |

Asosiy yangiliklar: o'z-o'zini yangilash (imzo, rollback), offsite 2-daraja (FR-BKP-011…013),
restore drill (UI, jurnal, eslatma), `gzip -t` yaxlitlik, 2FA, cut-over yordamchisi, qoidalar UI,
titrash/guruhlash, kunlik/haftalik hisobotlar, SSE, qorong'i mavzu, ru/en, staging va yuklama testlari.

**M5 (hafta 40, 2027-08-01):** hisobotlar, 2FA, drill ishlaydi.
**Chiqish:** F2 testlari o'tgan; soxta alert ≤ 5% (90 kun); NFR-CAP-001 (30/60 agent); runbook'lar to'liq (40+).

## 6. F3 — Yetuklik (hafta 41–48, S20–S23, 32 kun)

| Sprint | Hafta | Ish (kun) |
|---|---|---|
| S20 | 41–42 | D1 Cheklangan viewer (3), D2 Status sahifa (3), D3 Ikkinchi tekshiruvchi tugun (2/4) |
| S21 | 43–44 | D3 (2), D4 `appctl drill` avtomatik (4), D5 Eskalatsiya (2) |
| S22 | 45–46 | D6 SSH/apt/`nginx -t` metrikalari (3), D7 Webhook va deploy belgilari (3), D8 Qidiruv va CSV (2) |
| S23 | 47–48 | D9 Supply-chain: `cosign`, SBOM, Renovate (3), D10 Silliqlash (5) |

**M6 (hafta 48, 2027-09-26):** yakuniy topshirish — manba kod, hujjat, runbook'lar, tiklash yo'riqnomasi sinalgan.

## 7. Qaror nuqtalari

| № | Qachon | Savol |
|---|---|---|
| 1 | F0 oxiri (hafta 2) | Timescale va Go ishladimi? Baho o'zgardimi? (R-102, R-103, R-118) |
| 2 | M2 (hafta 14) | F1 jadvalda ketyaptimi? F2 dan nima kesiladi? |
| 3 | F1 UAT oxiri (hafta 24) | Uptime Kuma o'chiriladimi? Soxta alert darajasi qabul qilarlimi? |
| 4 | M5 (hafta 40) | F3 ning qaysi qismlari haqiqatan kerak (status sahifa, eskalatsiya)? |

## 8. Fazalar bo'yicha asosiy xavflar

| Faza | Xavf | Chora |
|---|---|---|
| F0 | R-102 Timescale agregatlari kutilganidek emas | Zaxira reja: oddiy partitsiya + Celery agregat (ADR-002) |
| F0/F1 | R-109 `appctl` o'zgartirishi zaxirani buzadi | Nusxada sinov, `\|\| true`, ikki bosqich |
| F1 | R-105 Soxta alertlar | `for`, tasdiqlash, gisterezis, 4 hafta yumshoq rejim |
| F1 | R-108 Agent serverga yuk beradi | S-00 → S-02 → S-01, `MemoryMax`/`CPUQuota`, 24 soat kuzatuv |
| F1/F2 | R-101, R-111 Hajm o'sishi, baho kam | F1 qamrovi muzlatiladi; 20% bufer |
| Doim | R-106 Bitta odam (bus factor) | TZ + ADR + runbook'larni yangilab borish |
| F2 | R-117 Restore drill e'tiborsiz qoladi | Eslatma; UAT-09 majburiy |

## 9. TZ da topilgan nomuvofiqliklar (rejaga ta'siri bilan)

Roadmap quyidagilarni hisobga olib tuzilgan. TZ matniga tegmadim; qaror sizniki.

1. **M4 va M5 haftalari xato.** 17.4: M4 = hafta 20, M5 = hafta 38. Lekin 17.3.5 bo'yicha
   2+20 = 22 va 22+18 = 40. Bu roadmap'da 22 va 40 ishlatilgan.
2. **M1 hafta 6 da sig'maydi.** M1 uchun kerak ish ≈ 24–30 kun (B1, B3, B5a, B7, B8, B2 qismi), hafta 3–6 da
   esa 16 kun bor. Bu roadmap'da M1 = hafta 8.
3. **UAT-01 ("barcha M talablar") F1 uchun noto'g'ri.** M (Must) talablarning bir qismi F2 da
   (masalan, FR-BKP-006, FR-BKP-011…013, FR-HTTP-009). UAT-01 "F1 ga tegishli M talablar" deb o'qilishi kerak.
4. **Offsite 2-daraja F2 da, xavf R-001 esa eng katta.** F1 da faqat 1-daraja (`_run.json`). Hafta 0 dagi
   `OFFSITE` sozlash buni vaqtincha yopadi; S-00 agenti M1 da turgani uchun 2-darajani F1 oxiriga
   olib kirish ≈ 1–2 kun. Tavsiya etiladi.
5. **NFR-SEC-012 (imzolangan yangilanish) F1, o'z-o'zini yangilash (FR-AGT-008) F2.** F1 da faqat
   `install.sh` imzo tekshiruvi bo'ladi; yangilanishni rad etish testi (T-U-SEC-11) F2 ga o'tadi.
6. **B9 Frontend F1 (14 kun)** 12 dan ortiq ekran uchun optimistik. Eng katta kechikish xavfi shu paketda.

## 10. Keyingi qadam

1. Hafta 0 ro'yxatini (2-bo'lim) bajaring.
2. Q-01…Q-11 ga javob bering (17.11); ayniqsa Q-02, Q-05, Q-07, Q-08.
3. Javoblardan keyin S0 (F0) ni boshlaymiz: repo, CI va prototip agent.
