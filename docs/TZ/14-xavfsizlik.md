# 14. Xavfsizlik

## 14.1. Nima himoya qilinadi

Monitoring tizimi o'zi "kalit" emas, lekin **xarita**: u barcha serverlar, loyihalar, domenlar
va zaxiralar joylashuvini bir joyga to'playdi. Hujumchi uchun bu razvedka. Undan tashqari,
tizimda bir nechta maxfiy qiymat bor.

| Aktiv | Ahamiyati | Buzilsa nima bo'ladi |
|---|---|---|
| **Infratuzilma xaritasi** (reyestr: IP, domen, port, loyiha) | Yuqori | Hujum yuzasi ochiladi; maqsadli hujum osonlashadi |
| **Telegram bot tokeni** | Yuqori | Soxta alertlar yuborish, xabarlarni o'qish |
| **Agent tokenlari** | O'rta | Soxta metrika yuborish (monitoringni aldash: "hammasi joyida" deb ko'rsatish) |
| **Agent yangilanish kanali** | **Juda yuqori** | Hujumchi barcha serverlarda o'z kodini bajara oladi |
| **Foydalanuvchi hisoblari** | Yuqori | Sozlamalarni o'zgartirish, alertlarni o'chirish |
| **Tekshiruv sarlavhalari** (`Authorization`, API kalitlar) | O'rta | Tekshirilayotgan xizmatga kirish |
| **Zaxira holati ma'lumoti** | O'rta | Qaysi zaxira zaif ekanini bilish |
| **Audit jurnali** | O'rta | Izlarni yashirish |
| **Core serveri** | Yuqori | Yuqoridagilarning hammasi |

## 14.2. Xavf modeli (STRIDE)

| № | Tahdid | Turi | Ehtimol | Ta'sir | Chora (talab) |
|---|---|---|---|---|---|
| TH-01 | Kirish sahifasiga parol terib hujum (bruteforce, credential stuffing) | Spoofing | Yuqori | Yuqori | Argon2id, blok (5/15 daq), 2FA, tezlik chegarasi (FR-AUTH-001/003/007) |
| TH-02 | Sessiya o'g'irlanishi (XSS, cookie) | Spoofing | O'rta | Yuqori | `HttpOnly/Secure/SameSite`, CSP, XSS himoyasi, qisqa muddat (14.8) |
| TH-03 | CSRF orqali amal bajartirish | Tampering | O'rta | O'rta | CSRF token, `SameSite=Lax`, `Origin` tekshiruvi |
| TH-04 | Soxta agent (token taxmin qilish/o'g'irlash) | Spoofing | Past | O'rta | 256-bit token, xesh saqlash, tezlik chegarasi, bekor qilish (FR-AUTH-006) |
| TH-05 | Buzilgan agent hostdan soxta ma'lumot (alertni yashirish) | Tampering | Past | O'rta | Tashqi faol tekshiruvlar mustaqil; heartbeat + tashqi TCP:22; ma'lumot sifat tekshiruvlari |
| TH-06 | Core buzilib, agentlarga zararli yangilanish yuborish | Elevation | Past | **Juda yuqori** | Imzolangan yangilanish; imzo kaliti core'da **yo'q** (14.5.4) |
| TH-07 | Core buzilib, agent tokenlarini yig'ish | Info disclosure | Past | O'rta | Tokenlar bazada faqat xesh; agent faqat ma'lumot yuboradi, buyruq olmaydi (14.5.3) |
| TH-08 | SSRF: prober orqali ichki tarmoqqa so'rov | Info disclosure / Elevation | O'rta | Yuqori | Shaxsiy diapazonlarni rad etish (6.8), yo'naltirishdan keyin ham tekshirish |
| TH-09 | SQL injection | Tampering | Past | Yuqori | ORM/parametrli so'rovlar; xom SQL faqat tasdiqlangan joylarda |
| TH-10 | XSS orqali saqlangan ma'lumot (loyiha nomi, izoh, konteyner nomi) | Tampering | O'rta | Yuqori | React escaping; markdown izohlarni tozalash (`DOMPurify`); `dangerouslySetInnerHTML` taqiq |
| TH-11 | Webhook/Telegram callback soxtalashtirish | Spoofing | O'rta | O'rta | Maxfiy URL segmenti, `X-Telegram-Bot-Api-Secret-Token`, chat ID ro'yxati, HMAC imzoli callback |
| TH-12 | Maxfiy qiymatlar loglarga tushishi | Info disclosure | O'rta | O'rta | Log filtrlari, `NFR-SEC-008`, avtomatik skaner |
| TH-13 | Core DoS: ingest'ni to'ldirish | DoS | O'rta | O'rta | Tezlik chegarasi, paket hajmi 1 MB, token bo'yicha cheklov, nginx `limit_req` |
| TH-14 | Disk to'ldirish (metrika xaosi, yuqori kardinallik) | DoS | O'rta | O'rta | Kardinallik chegarasi (≤ 1 000 series/host), retention, disk alerti |
| TH-15 | Ichki odam: operator rolidan ortiqcha amal | Elevation | Past | O'rta | RBAC, obyekt darajasida tekshiruv, audit jurnali |
| TH-16 | Zaxira (Nazoratchi bazasi) ma'lumoti sizib chiqishi | Info disclosure | Past | Yuqori | Telegram'ga yuboriladigan zaxira `age` bilan shifrlangan, maxfiy kalit alohida (Owner'da) |
| TH-17 | Ta'minot zanjiri: zararli kutubxona | Tampering | O'rta | Yuqori | Versiyalarni qotirish, `pip-audit`/`npm audit`/`govulncheck`, minimal bog'liqlik |
| TH-18 | Man-in-the-middle (agent ↔ core) | Tampering / Info | Past | Yuqori | TLS 1.2+, sertifikat tekshiruvi (CA qotirish ixtiyoriy) |
| TH-19 | Docker socket orqali root huquqi (agent) | Elevation | O'rta | **Juda yuqori** | `docker-socket-proxy` (faqat GET), agent root emas, `docker` guruhida emas |
| TH-20 | Monitoringni "ko'r" qilish: Nazoratchi o'zi o'chirilsa | DoS | O'rta | Yuqori | Alohida serverdagi watchdog (S-01, FR-SYS-002) |

## 14.3. Autentifikatsiya va sessiya

### 14.3.1. Parol

| Parametr | Qiymat |
|---|---|
| Algoritm | Argon2id; `time_cost=3`, `memory_cost=64 MiB`, `parallelism=2` (o'lchov bilan sozlanadi: ≤ 300 ms) |
| Minimal uzunlik | 12; maksimal 128 |
| Tekshiruv | Eng ko'p ishlatiladigan 10 000 ta parol ro'yxati bilan taqqoslash; login/email bilan o'xshashlik |
| Saqlash | Faqat xesh (tuz ichida); parol hech qayerda saqlanmaydi/loglanmaydi |
| O'zgartirish | Joriy parol talab qilinadi; boshqa sessiyalar tugatiladi |
| Muddat | Majburiy muddatli almashtirish yo'q (NIST 800-63B); buzilish gumonida majburiy almashtirish |

### 14.3.2. Kirishga urinishlar

- 5 ta ketma-ket xato (login + IP bo'yicha ikkalasi ham hisoblanadi) → 15 daqiqa blok (`423`),
  har keyingi blok 2 baravar uzayadi (maks. 24 soat).
- Xato javoblari "login yoki parol noto'g'ri" bir xil matn va **bir xil vaqt** (timing farqini
  yashirish uchun soxta xesh solishtirish).
- Barcha urinishlar audit jurnalida (muvaffaqiyatli va muvaffaqiyatsiz).
- Egasi (Owner) uchun muvaffaqiyatsiz urinishlar > 10/soat → Telegram ogohlantirish.

### 14.3.3. Ikki bosqichli tasdiqlash (TOTP)

- RFC 6238; 6 raqam, 30 s, ±1 oyna. Sir 160 bit, bazada shifrlangan (`totp_secret_enc`).
- Bir marta ishlatiladigan zaxira kodlar (10 ta, xeshlangan).
- Owner roli uchun 2FA **majburiy** (F2 dan); boshqalar uchun tavsiya.
- Qayta ishlatishdan himoya: bir kod bir marta (oxirgi ishlatilgan vaqt oynasi saqlanadi).

### 14.3.4. Sessiya

| Parametr | Qiymat |
|---|---|
| Saqlash | Server tomonida (baza/Redis); cookie faqat tasodifiy identifikator |
| Cookie | `HttpOnly; Secure; SameSite=Lax; Path=/`, nomi `__Host-nzr_sid` |
| Muddat | Harakatsizlik 12 soat; mutlaq 7 kun |
| Aylantirish | Kirishdan keyin va rol/parol o'zgarganda yangi identifikator |
| Chiqish | Serverda sessiya o'chiriladi; "barcha qurilmalardan chiqish" |
| Bir vaqtdagi sessiyalar | Cheklanmagan, lekin ro'yxatda ko'rinadi (qurilma, IP, vaqt) |

### 14.3.5. Parolni tiklash

Email orqali emas (email hisobi alohida zaif nuqta) — Telegram bot orqali: faqat oldindan
bog'langan `telegram_chat_id` ga 15 daqiqalik bir martalik havola. Havola ishlatilgach, barcha
sessiyalar tugatiladi, 2FA qayta tasdiqlanadi (yoqilgan bo'lsa).

## 14.4. Avtorizatsiya

- **RBAC** (3.2 matritsasi) markaziy dekorator/ruxsat sinfi bilan; har endpoint o'z
  ruxsat talabini e'lon qiladi; e'lon qilinmagan endpoint **rad etiladi** (xavfsiz standart).
- **Obyekt darajasidagi tekshiruv:** viewer faqat `user_projects` dagi loyihalar va ularga
  bog'liq obyektlarni ko'radi; ID taxmin qilish `404` beradi (mavjudligini oshkor qilmaydi).
- **Maxfiy maydonlar** (kanal sozlamasi, tekshiruv sarlavhalari) API javobida **hech qachon**
  to'liq qaytmaydi (`••••` bilan maskalanadi); o'zgartirish uchun yangi qiymat yuboriladi.
- **Eng kam huquq:** Operator foydalanuvchi, token, kanal, tizim sozlamalarini o'zgartira olmaydi.
- **Audit:** barcha o'zgartiruvchi amallar (FR-AUD-001).

## 14.5. Agent xavfsizligi

### 14.5.1. Enroll va token hayoti

```
[Owner/Operator] ── yaratadi ──► enroll_token (1 soat, bir marta)
        │
        ▼ (o'rnatish buyrug'i ichida)
[Agent] ── enroll_token + facts ──► [Core] ── tekshiradi ──► agent_token (256 bit) ──► [Agent]
                                                            (bazada: SHA-256 xesh)
```

- `agent_token` faqat agent fayli `/etc/nazoratchi/token` (rejim `0600`, egasi `nazoratchi`) da.
- Token **host bilan bog'langan**: boshqa hostdan ishlatilsa (ma'lumot `host_id` mos emas yoki
  IP o'zgargan bo'lsa) — ogohlantirish (`info`), lekin rad etilmaydi (dinamik IP lar bo'lishi mumkin).
- Rotatsiya: Owner yangi token yaratadi → agentga `reload_config` orqali yetkaziladi (eski token
  24 soat parallel ishlaydi) → eski bekor qilinadi. Tavsiya: yiliga 1 marta yoki buzilish
  gumonida.
- Bekor qilish: darhol (`revoked_at`); agent 401 oladi va 5 daqiqada qayta urinadi (14.5.3).

### 14.5.2. Agent nima qila olmaydi (cheklov kafolati)

- Masofaviy buyruq bajarmaydi (shell yo'q) — core faqat 4 turdagi buyruq beradi (7.5.3).
- Konteyner yaratmaydi/to'xtatmaydi/o'chirmaydi (Docker proksi — faqat GET).
- Fayl mazmunini o'qimaydi (faqat nom, hajm, `mtime`, `gzip -t` natijasi).
- Hech qanday kiruvchi port ochmaydi.
- `root` emas; `NoNewPrivileges`, `ProtectSystem=strict`, bo'sh `CapabilityBoundingSet`.

### 14.5.3. Core buzilsa agentga ta'siri

Agent core'dan faqat quyidagilarni qabul qiladi: `set_interval`, `reload_config`, `collect_now`,
`update`. Birinchi uchtasi zararsiz (resurs sarfini oshirishdan tashqari, intervalda 5 s
pastki chegara bor). **`update` xavfli** — shu sabab 14.5.4.

### 14.5.4. Imzolangan yangilanishlar (TH-06)

Talab (NFR-SEC-012, majburiy):

1. Agent binarlari CI muhitida **`minisign` maxfiy kaliti** bilan imzolanadi. Maxfiy kalit
   faqat CI sirlarida (yoki offlayn, egasida) turadi; **core serverda yo'q**.
2. Ochiq kalit agent binariga **joylangan** (compile-time) — yangilanish orqali ham,
   sozlama orqali ham o'zgartirib bo'lmaydi (kalit almashtirish uchun yangi qo'lda o'rnatish
   yoki ikkita kalitli "o'tish" davri).
3. Agent `update` buyrug'ini qabul qilganda: faylni yuklaydi → imzoni tekshiradi → **faqat shundan
   keyin** almashtiradi. Imzo mos kelmasa — rad etadi, `agent_update_rejected` voqeasini yuboradi
   va logga yozadi.
4. Eskiga qaytarishdan himoya (rollback attack): yangilanish versiyasi hozirgidan **katta**
   bo'lishi kerak (yoki aniq `--allow-downgrade` bilan).
5. `install.sh` (birinchi o'rnatish) core'dan yuklanadi — bu **trust-on-first-use** (TOFU).
   Yumshatish: skript ichidagi minisign ochiq kaliti va SHA-256 qiymati hujjatda (README) alohida
   ham e'lon qilinadi; operator o'rnatishdan oldin `sha256sum install.sh` ni solishtira oladi.

### 14.5.5. Soxta ma'lumotdan himoya (TH-05)

Buzilgan agent "hammasi joyida" deb yolg'on yuborishi mumkin. Cheklov (to'liq himoya emas):
- Faol tekshiruvlar (HTTP/TLS/DNS/TCP) mustaqil va agentga bog'liq emas.
- Heartbeat tashqi TCP:22/ICMP bilan birga baholanadi.
- Statistik tekshiruv: qiymatlar diapazondan tashqarida (masalan, `cpu_busy_percent > 100`)
  yoki namunalar vaqti kelajakda bo'lsa — rad etiladi va `ingest_rejected` hisoblanadi.
- Agent versiyasi/`boot_id` o'zgarishi voqea sifatida yoziladi.

## 14.6. Maxfiy ma'lumotlarni saqlash

| Maxfiy qiymat | Saqlash | Himoya |
|---|---|---|
| Foydalanuvchi parollari | `users.password_hash` | Argon2id |
| Agent/API/heartbeat tokenlari | `*.token_hash` | SHA-256 (256-bit tasodifiy tokenlar uchun yetarli); token faqat yaratilganda ko'rsatiladi |
| Telegram bot tokeni, SMTP paroli, webhook siri | `channels.config_enc` | AES-256-GCM, har yozuv uchun yangi `nonce`, `aad = channel_id` |
| Tekshiruv sarlavhalari | `probes.secrets_enc` | AES-256-GCM |
| TOTP siri | `users.totp_secret_enc` | AES-256-GCM |
| Django `SECRET_KEY` | Muhit o'zgaruvchisi / fayl | Repoda yo'q |
| Shifrlash asosiy kaliti (`NAZORATCHI_MASTER_KEY`, 32 bayt) | `/opt/applications/projects/Nazoratchi/.env` yoki `/etc/nazoratchi/master.key` | Fayl rejimi `0400`, egasi — servis foydalanuvchisi; bazadan alohida; zaxirada **alohida** saqlanadi (parol menejeri) |
| Imzo kaliti (minisign) | CI sirlari / oflayn | Core'da yo'q |

**Kalit rotatsiyasi:** `master.key` almashtirish — `nazoratchi rotate-key` buyrug'i (barcha `*_enc`
maydonlarni eski kalit bilan ochib, yangisi bilan qayta shifrlaydi; tranzaksiyada). Kalitni
yo'qotish = shifrlangan maydonlarni yo'qotish (kanal sozlamalarini qayta kiritish kerak) — shuning
uchun kalit nusxasi parol menejerida saqlanishi shart.

## 14.7. Tarmoq va infratuzilma xavfsizligi

### 14.7.1. Core serveri

| Chora | Tafsilot |
|---|---|
| Firewall (`ufw`) | Faqat 22 (kalit bilan), 80, 443 |
| SSH | Faqat kalit (`PasswordAuthentication no`), `root` kirishi taqiqlangan yoki `prohibit-password`; `fail2ban` |
| Docker | Portlar `127.0.0.1` ga bog'langan (Docker nashr qilingan portlar `ufw` ni chetlab o'tadi); `db`, `redis` xostga chiqarilmaydi |
| nginx | `server_tokens off`; TLS 1.2+; zamonaviy shifrlar; HSTS; `limit_req` (ingest, login) |
| Yangilanishlar | `unattended-upgrades` (xavfsizlik); **reboot rejalashtirilgan** oyna bilan (L-4 saboqi) |
| Snapshot | Kunlik provayder snapshot; reboot/kernel oldidan qo'lda |
| Core ni kuzatish | Watchdog (S-01); core'ga ham agent o'rnatiladi (disk/RAM) |

### 14.7.2. SSRF himoyasi (prober)

1. Domen/URL kiritilganda va **har so'rovda** (yo'naltirishdan keyin ham) manzil aniqlanadi.
2. Rad etiladigan diapazonlar: `127.0.0.0/8`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`,
   `169.254.0.0/16` (bulut metadata), `100.64.0.0/10`, `::1`, `fc00::/7`, `fe80::/10`.
3. DNS rebinding: aniqlangan IP bilan ulaniladi (qayta aniqlanmaydi).
4. Faqat `http`/`https` protokollari; `file://`, `gopher://` va h.k. taqiq.
5. Maxsus istisno (loopback tekshiruvi uchun) faqat Owner tomonidan, har tekshiruv uchun alohida
   `allow_private=true` bilan va audit bilan.
6. Javob tanasi ≤ 64 KB o'qiladi; timeout qattiq.

### 14.7.3. Tezlik chegaralari (nginx va ilova)

| Endpoint | Chegara |
|---|---|
| `/auth/login` | IP bo'yicha 10/daqiqa; hisob bo'yicha 5 xato/15 daq |
| `/ingest/v1/metrics` | Token bo'yicha 30/daqiqa (normal ≈ 4/daqiqa) |
| `/ingest/v1/enroll` | IP bo'yicha 10/soat |
| `/hb/<token>` | Token bo'yicha 10/daqiqa |
| `/api/v1/*` | Foydalanuvchi bo'yicha 120/daqiqa |
| Telegram webhook | Telegram IP diapazonlari (ixtiyoriy) + maxfiy segment |

## 14.8. Ilova xavfsizligi

### 14.8.1. Kirishni tekshirish va chiqishni kodlash

- Barcha kirish DRF serializerlari bilan (turi, uzunligi, formati); noma'lum maydonlar rad etiladi.
- ORM parametrlari; xom SQL (agregatlar) faqat parametr bog'lash bilan (`%s`).
- JSON javoblar `Content-Type: application/json` + `X-Content-Type-Options: nosniff`.
- Markdown izohlar (incident, loyiha) — cheklangan (qalin, havola, ro'yxat), `DOMPurify` bilan tozalash,
  havolalar `rel="noopener noreferrer"`.

### 14.8.2. Sarlavhalar

```
Strict-Transport-Security: max-age=31536000; includeSubDomains
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:;
                         connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'
X-Content-Type-Options: nosniff
Referrer-Policy: same-origin
X-Frame-Options: DENY
Permissions-Policy: camera=(), microphone=(), geolocation=()
Cross-Origin-Opener-Policy: same-origin
```

CORS: ruxsat yo'q (panel va API bir xil origin). Agent API (`/ingest`) CORS talab qilmaydi.

### 14.8.3. CSRF

Cookie-sessiyali so'rovlarda `X-CSRFToken` majburiy; `Origin`/`Referer` tekshiruvi; API tokenli
so'rovlarda (cookie yo'q) CSRF talab qilinmaydi.

### 14.8.4. Fayl yuklash

Tizimda fayl yuklash **yo'q** (F1–F3); import (reyestr YAML) — hajm ≤ 1 MB, xavfsiz YAML
yuklovchi (`safe_load`), sxema validatsiyasi.

## 14.9. Loglar va audit (xavfsizlik jihati)

- Loglarda taqiqlanganlar: parol, token, `Authorization`, `Cookie`, `Set-Cookie`, `.env` qiymatlari,
  TOTP kodlari, Telegram bot tokeni (URL ichida bo'lishi mumkin: `api.telegram.org/bot<TOKEN>/...` —
  `httpx` loglari filtrlanadi).
- Maxfiy qiymatlarni maskalash filtri (regex: `(?i)((?:token|secret|password|authorization)\S*\s*[=:]\s*(?:(?:bearer|basic)\s+)?)\S+`, qiymat `***` bilan almashadi; `Authorization: Bearer <token>` da "Bearer" dan keyingi token ham yopilishi shart — P-02 testi eski regexda shu xatoni topdi)
  barcha log yozuvlariga qo'llanadi; test: sun'iy token yuborilganda logda ko'rinmasligi.
- Audit jurnali faqat qo'shiladi; ilova DB roli `UPDATE/DELETE` huquqiga ega emas (8.8).
- Xavfsizlik hodisalari alohida belgilanadi: `login_failed`, `account_locked`, `token_revoked`,
  `agent_update_rejected`, `permission_denied`. F1–F2 da ular kunlik/haftalik hisobotda
  ko'rsatiladi; alohida alert qoidasi F3 da qo'shilishi mumkin (hozir katalogda yo'q).

## 14.10. Nazoratchi'ning o'z zaxirasi va tiklash

- Kunlik mantiqiy `pg_dump` (reyestr, incident, audit, sozlamalar; metrikalar kirmaydi) + `.env`
  (shifrlangan) + `master.key` **emas** (u alohida saqlanadi).
- `age` bilan shifrlanadi (NFR-SEC-010): ochiq kalit core'da, maxfiy kalit — faqat Owner'da (parol menejeri).
- **Saqlash joyi (Q-13):** Owner'ning shaxsiy Telegram chati (bot orqali, `sendDocument`; guruhga emas).
  Bot API fayl chegarasi 50 MB: katta bo'lsa bo'laklanadi yoki metrikasiz sxema kichraytiriladi.
  Telegram faqat shifrlangan faylni ko'radi. Owner botni bir marta `/start` qilgan bo'lishi kerak.
- Yuborish natijasi qayd etiladi; ketma-ket 2 kun yuborilmasa alert. Owner chatni o'chirib yubormasligi kerak.
- Tiklash tartibi sinovdan o'tkaziladi (yiliga 1 marta; NFR-REL-006), 15.9-bo'lim.

## 14.11. Ta'minot zanjiri

| Chora | Tafsilot |
|---|---|
| Versiyalarni qotirish | `uv.lock`/`requirements.txt` (hash bilan), `pnpm-lock.yaml`, `go.sum`; Docker image'lar versiya tegi bilan (digest tavsiya) |
| Skanerlash | CI da `pip-audit`, `npm audit`, `govulncheck`, `trivy` (image); jiddiy zaiflikda build to'xtaydi |
| Minimal bog'liqlik | Yangi kutubxona qo'shish sababi PR da yoziladi |
| SBOM | CI har relizda (`syft`) SBOM yaratadi |
| Image kelib chiqishi | Image'lar faqat o'zimizning CI da quriladi; `ghcr.io` yoki o'z registry; imzo (`cosign`) — F3 |
| Dependabot/Renovate | Haftalik yangilanish PR lari |
| Imzo kaliti | CI sirlarida, 2FA bilan himoyalangan hisob; kamida 2 kishi (yoki egasi + zaxira) ruxsat |

> Eslatma (2026-10 tajribasidan): MinIO ommaviy image'lari endi tortib bo'lmadi va manbadan
> qurish kerak bo'ldi. Bu "uchinchi tomon image'iga bog'liqlik" xavfini ko'rsatdi: Nazoratchi
> faqat o'z image'lari va keng qo'llab-quvvatlanadigan rasmiy image'lardan (`postgres`, `redis`,
> `nginx`, `timescale/timescaledb`) foydalanadi va ularning nusxasini o'z registry'ga qo'yish
> mumkin bo'lishi uchun versiyalarni qotiradi.

## 14.12. Hodisaga javob (Nazoratchi uchun)

### 14.12.1. Agent tokeni sizdi (yoki hostda buzilish gumoni)

1. Panelda tokenni bekor qilish (Sozlamalar → Tokenlar).
2. Hostda: agentni to'xtatish, `token` faylini o'chirish, hostni tekshirish (RB-014 dagi qadamlar).
3. Yangi enroll tokeni → agentni qayta o'rnatish.
4. Audit jurnalida o'sha token bilan so'nggi 7 kundagi kirishlar (`last_used_ip`) ko'rib chiqiladi.

### 14.12.2. Core buzilishi gumoni

1. Core'ni tarmoqdan ajratish (firewall/provayder panel).
2. **Agentlarni to'xtatish shart emas:** `update` imzosiz ishlamaydi (14.5.4), shuning uchun
   agentlar xavfsiz. Ular core'ga ma'lumot yuborishda davom etadi (buferga yig'adi) — core
   tiklanguncha tashqi watchdog va provayder monitoringiga tayaning.
3. Yangi serverda zaxiradan tiklash; **barcha maxfiy qiymatlarni almashtirish**: `master.key`,
   Django `SECRET_KEY`, Telegram bot tokeni (BotFather orqali yangi), SMTP paroli, barcha
   foydalanuvchi parollari va sessiyalar, agent tokenlari, tekshiruv sarlavhalari.
4. Hodisa tahlili: kirish vektori, davomiyligi, nima o'qilgan.

### 14.12.3. Telegram bot tokeni sizdi

BotFather'da `/revoke`, yangi token → `channels` da yangilash → eski tokenli xabarlar
yuborilmaydi. Webhook maxfiy segmentini ham almashtirish.

## 14.13. Xavfsizlik tekshiruv ro'yxati (reliz oldidan)

| № | Tekshiruv | Qanday |
|---|---|---|
| S-01 | OWASP ASVS L1 (barcha) va L2 (autentifikatsiya, sessiya, kirish tekshiruvi) bandlari | Ro'yxat bo'yicha qo'lda + ZAP |
| S-02 | `testssl.sh` — A daraja | Avtomatik |
| S-03 | `securityheaders.com` — A | Avtomatik |
| S-04 | Maxfiy qiymat loglarda yo'q | Loglarni skaner qilish testi |
| S-05 | Bazada ochiq matnli maxfiy qiymat yo'q | `SELECT` bilan tekshirish |
| S-06 | Agent: root emas, `docker` guruhida emas, yangilanish imzosi | Qo'lda + test (buzuq imzo bilan rad etish) |
| S-07 | Prober: ichki IP ga so'rov rad etiladi | Birlik va E2E test |
| S-08 | Tezlik chegaralari ishlaydi | `k6` bilan |
| S-09 | RBAC: viewer/operator ruxsatsiz endpointlarga `403` | Avtomatik test (matritsa bo'yicha) |
| S-10 | CSRF: tokensiz POST rad etiladi | Avtomatik |
| S-11 | `db`/`redis` portlari tashqaridan yopiq | `nmap` tashqaridan |
| S-12 | Bog'liqlik skanerlari toza (jiddiy zaiflik yo'q) | CI |
| S-13 | Zaxira tiklash sinovi muvaffaqiyatli | Qo'lda |

## 14.14. Qoldiq xavflar (qabul qilingan)

| № | Xavf | Sabab | Qabul sharti |
|---|---|---|---|
| RS-01 | TOFU: `install.sh` birinchi yuklanishda core'ga ishonadi | Soddalik; hozircha bitta egasi | Ochiq kalit va skript xeshi README da e'lon qilinadi |
| RS-02 | Watchdog va Nazoratchi bir egasi hisoblari ostida (Telegram bot ham) | Kichik jamoa | Alohida bot; server bir (S-00, ADR-014 istisnosi, RS-06) |
| RS-03 | Buzilgan agent soxta ma'lumot yuborishi mumkin | Push modelining tabiati | Faol tekshiruvlar mustaqil (14.5.5) |
| RS-04 | Bitta core (SPOF) | Byudjet | RTO ≤ 1 soat, watchdog |
| RS-05 | Parol bilan SSH (core uchun tavsiya etilmaydi; kalitga o'tish rejalashtirilgan) | Hozirgi serverlarda shunday | Core uchun kalit majburiy; S-01 uchun alohida ish |
| RS-06 | S-00 (core, offsite) va S-01 (watchdog, ishchi loyihalar) bir provayderda; ikkalasi bir vaqtda tushsa hech kim xabar bermaydi | Owner qarori (2026-10-26), byudjet | Aniqlash: o'zaro kuzatuv. Yumshatish ixtiyoriy: tashqi bepul xizmat; provayder snapshoti; S-01 zaxiralari S-01 da ham qoladi |
| RS-07 | Nazoratchi o'z zaxirasi Telegram'da: Telegram yoki Owner hisobi yo'qolsa zaxira yo'qoladi; Bot API fayl chegarasi 50 MB | Q-13 qarori (2026-10-26) | `age` shifrlash; chatni o'chirmaslik; vaqti-vaqti bilan nusxani qo'lda saqlash; tiklash mashqi (15.9) |
