# NAZORATCHI — Infratuzilma monitoringi platformasi

## Texnik topshiriq (TZ)

| | |
|---|---|
| **Hujjat turi** | Texnik topshiriq (Technical Specification) |
| **Loyiha ishchi nomi** | Nazoratchi (Nazoratchi Monitor) |
| **Versiya** | 1.8 (loyiha) |
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
