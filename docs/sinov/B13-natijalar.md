# B13. Sinov va mustahkamlash natijalari (F1 S10)

Sana: 2026-10-28. Muhit: dev (Windows + Docker Desktop, `runserver`, TimescaleDB 5434). Prod-ga o'xshash muhitda
(uvicorn 2 worker, 2 vCPU) takrorlash UAT bosqichida (S-01) bajariladi.

## 1. Xavfsizlik ro'yxati (TZ 14.13, 16.7)

| № | Tekshiruv | Holat | Qanday |
|---|---|---|---|
| S-01 | ASVS L1/L2, ZAP | **Kutilmoqda** | Autentifikatsiyalangan ZAP skaneri staging/S-01 da (T-S-01) |
| S-02 | `testssl.sh` A | **Kutilmoqda** | Haqiqiy domen va sertifikat kerak |
| S-03 | `securityheaders.com` A | **Kutilmoqda** | Sarlavhalar nginx shablonida bor (HSTS, nosniff, DENY, CSP); haqiqiy serverda tekshiriladi |
| S-04 | Maxfiy qiymat loglarda yo'q | O'tdi | `test_notifications`: bot token xato matnlarida va log maskasida yo'q |
| S-05 | Bazada ochiq sir yo'q | O'tdi | `test_security`: agent tokeni faqat xesh, kanal sirlari shifrlangan, audit'da sir yo'q |
| S-06 | Agent: root emas, imzo | O'tdi | `install.sh` konteyner testi: buzilgan binar va begona imzo rad etiladi |
| S-07 | Prober: ichki IP rad | O'tdi | `test_probes`: loopback/private/metadata, redirect, DNS orqali SSRF |
| S-08 | Tezlik chegaralari | Qisman | Birlik testlari bor (ingest 30/daq, login, enroll); `k6` bilan yuklama testi kutilmoqda |
| S-09 | RBAC matritsasi | O'tdi | `test_security`: **barcha** `/api/v1/` yo'nalishlari avtomatik aylanib chiqiladi |
| S-10 | CSRF | O'tdi | `test_accounts`, `test_security` |
| S-11 | `db`/`redis` tashqaridan yopiq | **Kutilmoqda** | Compose faqat `127.0.0.1` ga bog'laydi; `nmap` tashqaridan prod'da |
| S-12 | Bog'liqlik skanerlari | O'tdi (CI) | `pip-audit`, `govulncheck`, `npm audit` |
| S-13 | Zaxira tiklash | Qisman | `restore_self_backup` testlari bor; to'liq RTO mashqi (UAT-10) kutilmoqda |

### Avtomatik xavfsizlik testlari (`backend/tests/test_security.py`, 19 ta)

- T-S-08/S-09: anonim hech bir API yo'nalishiga kira olmaydi (GET/POST/PATCH/DELETE); viewer hech qayerga yoza
  olmaydi; operator egasiga xos amallarni (kanallar) bajara olmaydi; hech bir yo'nalish 5xx bermaydi.
- T-S-06: javoblar faqat `application/json` + `nosniff`; xato javoblari JSON.
- T-S-07: SQL payload'lar filtr parametrlarida so'rovni buzmaydi.
- T-S-04: sessiya cookie `HttpOnly`, `SameSite=Lax` (prod'da `__Host-` va `Secure`).
- T-S-14: kanal tokeni API javobida ham, bazada ham ochiq matnda yo'q; audit jurnalida yo'q.

### Topilgan va tuzatilgan nuqsonlar

1. Noma'lum `/api/...` yo'li HTML 404 qaytarardi → `handler404`/`handler500` yagona JSON formatda (TZ 9.1.1).
2. `DATABASES` da ulanish vaqti cheklanmagan: baza javob bermasa `/healthz` cheksiz osilardi →
   `connect_timeout=5`; endi baza o'chiq bo'lsa 5 s da `503` (T-C-01, real sinovda tasdiqlandi).
3. `run_evaluator`/`run_prober` ning ikkinchi nusxasi ham ishlardi (alert takrorlanishi xavfi) → Postgres
   advisory lock bilan yagona leader (`apps/core/leader.py`, T-C-14).

## 2. Chaos (TZ 16.6)

| № | Natija | Qanday |
|---|---|---|
| T-C-01 | O'tdi | Real: `db` konteyneri to'xtatildi → `/healthz` 5 s da `503`, tiklangach `200` (yuqoridagi nuqson tuzatilgach) |
| T-C-02 | O'tdi | `test_chaos`: kesh (Redis) xato bersa ingest `200` (tezlik chegarasi fail-open) |
| T-C-14 | O'tdi | `test_chaos`: ikkinchi nusxa leader bo'lmaydi; birinchisi chiqsa egallaydi |
| T-C-17 | O'tdi | `test_chaos`: 70+ buzuq/tasodifiy tana (gzip bilan va gzip'siz), buzuq sarlavhalar → hech qachon 5xx |
| T-C-03..13, 15, 16 | **Kutilmoqda** | Haqiqiy server kerak (kill -9, soat siljitish, disk to'ldirish, tarmoq uzish, reboot) — UAT oldidan S-01 da qo'lda |

## 3. Unumdorlik (TZ 16.5)

Simulyator: `tools/simulator/simulate.py` (README shu papkada).

| № | Natija | Eslatma |
|---|---|---|
| T-P-01 (qisqartirilgan) | O'tdi | 10 agent × 90 s, interval 5 s (prod'dan 3 baravar tez), ~190 namuna/paket: 180/180 `200`, p50 75 ms, **p95 98 ms**, p99 115 ms (mezon p95 ≤ 300 ms) |
| T-P-01 (to'liq: 1 soat, 15 s) | **Kutilmoqda** | Prod-ga o'xshash muhit va CPU o'lchovi (≤ 40%) kerak |
| T-P-02..10 | **Kutilmoqda** | 30 agent × 4 soat, chegara, 90 kunlik so'rov, dashboard, prober, baza hajmi, agent resursi — staging/S-01 |

Dev `runserver` (bitta jarayon) natijasi prod uvicorn uchun konservativ taxmin: prod'da p95 yaxshiroq bo'lishi kutiladi.

## 4. UAT tayyorlik (TZ 16.8)

| № | Mezon | Tayyorlik |
|---|---|---|
| UAT-01 | M talablar | Matritsa (16.12) qo'lda to'ldiriladi; F1 ga tegishli M talablar kodda bor, F2 ga tegishlilari ROADMAP'da |
| UAT-02 | F1 testlar 100% | Backend 449, Go, watchdog 12, frontend 171, install.sh 12 tekshiruv — hammasi yashil |
| UAT-03 | 3 server × 14 kun | Agent o'rnatish tayyor (`install.sh`); boshlash Owner qaroriga bog'liq |
| UAT-04..06 | Haqiqiy sinovlar | Runbook'lar va alertlar tayyor; o'tkazish S-01 da |
| UAT-07 | Soxta alert ≤ 5% | 14 kun davomida qo'lda belgilanadi |
| UAT-08 | Seed loyiha tekshiruvlari | `seed_registry` bor; haqiqiy muhitda tekshiriladi |
| UAT-09 | 2 ta restore drill | Forma, API va AL-081…083 tayyor; 2 ta loyiha uchun haqiqiy drill'ni Owner o'tkazadi (TZ 10.8.3) |
| UAT-10 | Nazoratchi tiklash mashqi | RB-044 tayyor; vaqtni o'lchash kerak |
| UAT-11 | Hujjatlar | README, 34 runbook, o'rnatish yo'riqnomasi mavjud |
| UAT-12 | Xavfsizlik ro'yxati | 1-bo'limdagi "Kutilmoqda" bandlari yopilishi kerak |

UAT oldidan to'sqinlik qiluvchi kod bo'shlig'i qolmadi; drill'ning o'zi (UAT-09) va 1-bo'limdagi "Kutilmoqda" bandlari Owner/staging ishi.
