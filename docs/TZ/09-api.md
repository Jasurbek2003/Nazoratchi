# 9. API spetsifikatsiyasi

## 9.1. Umumiy qoidalar

| Mavzu | Qoida |
|---|---|
| Bazaviy manzil | `https://<core>/api/v1/` (brauzer/API), `https://<core>/ingest/v1/` (agent), `https://<core>/hb/` (heartbeat) |
| Format | JSON (`application/json; charset=utf-8`), maydon nomlari `snake_case` |
| Vaqt | ISO-8601 UTC: `2026-10-22T09:35:00Z`. Vaqt oralig'i parametrlari ham shu formatda |
| Identifikator | UUID satr |
| Autentifikatsiya | Brauzer: cookie-sessiya + `X-CSRFToken` (o'zgartiruvchi so'rovlarda). API tokeni: `Authorization: Bearer nzr_...`. Agent: `Authorization: Bearer agt_...` |
| Ruxsat | 3.2-bo'limdagi rollar matritsasi; ruxsat yo'q — `403`, kirmagan — `401` |
| Versiyalash | URL da `/v1/`; buzuvchi o'zgarish yangi `/v2/` ni talab qiladi; eski versiya kamida 6 oy ishlaydi |
| Sahifalash | Kursor bo'yicha: `?limit=50&cursor=<opaque>`; javobda `next_cursor` (oxirida `null`). `limit` ≤ 200 |
| Filtr va saralash | `?filter[status]=open&filter[severity]=critical&sort=-started_at` |
| Maydonlarni tanlash | `?fields=id,name,status` (ixtiyoriy) |
| Idempotentlik | O'zgartiruvchi `POST` da `Idempotency-Key: <uuid>` sarlavhasi qo'llab-quvvatlanadi (24 soat) |
| Tezlik cheklovi | Foydalanuvchi bo'yicha 120 so'rov/daqiqa; javob sarlavhalari `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `Retry-After` |
| Hujjat | OpenAPI 3.1 sxemasi `/api/v1/schema/` da, Swagger UI `/api/v1/docs/` (faqat Owner/Operator) |
| Kodlash | `UTF-8`; matnlar `NFC` normallashtirilgan |
| Til | `Accept-Language: uz`, `ru` yoki `en` — xato va shablon matnlari uchun |

### 9.1.1. Xato formati

Barcha xatolar bir xil shaklda:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Ma'lumot noto'g'ri kiritilgan.",
    "details": [
      {"field": "fqdn", "code": "invalid", "message": "Domen nomi noto'g'ri."}
    ],
    "request_id": "req_01JA4E9Q3T7"
  }
}
```

| HTTP | `code` | Ma'nosi |
|---|---|---|
| 400 | `bad_request`, `validation_error` | So'rov noto'g'ri / maydon xato |
| 401 | `unauthenticated`, `invalid_token`, `token_revoked` | Kirmagan yoki token noto'g'ri |
| 403 | `forbidden`, `csrf_failed` | Ruxsat yo'q |
| 404 | `not_found` | Obyekt yo'q yoki ko'rishga ruxsat yo'q (mavjudligini oshkor qilmaydi); noma'lum `/api/`, `/ingest/`, `/agent/` yo'llari ham shu formatda |
| 409 | `conflict`, `duplicate` | Takroriy nom, joriy holat bilan nomuvofiqlik |
| 410 | `gone`, `enroll_token_expired` | Muddati o'tgan |
| 413 | `payload_too_large` | Hajm chegarasi (ingest: 1 MB) |
| 415 | `unsupported_media_type` | JSON emas |
| 422 | `unprocessable` | Mantiqiy xato (masalan, `ends_at < starts_at`) |
| 423 | `account_locked` | Ko'p xato kirishdan keyin |
| 429 | `rate_limited` | Tezlik chegarasi; `Retry-After` |
| 500 | `internal_error` | Kutilmagan xato; `request_id` loglarda qidiriladi |
| 503 | `unavailable` | Baza/navbat vaqtincha mavjud emas |

## 9.2. Autentifikatsiya va foydalanuvchi

| Metod | Yo'l | Rol | Tavsif |
|---|---|---|---|
| POST | `/auth/login` | — | `{login, password}` → sessiya cookie; 2FA yoqilgan bo'lsa `202 {"mfa_required":true,"mfa_token":"..."}` |
| POST | `/auth/mfa` | — | `{mfa_token, code}` → sessiya |
| POST | `/auth/logout` | hamma | Joriy sessiyani tugatadi |
| POST | `/auth/logout-all` | hamma | Barcha sessiyalardan chiqish |
| GET | `/auth/me` | hamma | Joriy foydalanuvchi, rol, til, vaqt zonasi, ruxsat etilgan loyihalar |
| PATCH | `/auth/me` | hamma | Til, vaqt zonasi, parol almashtirish (`current_password` bilan) |
| POST | `/auth/mfa/setup` | hamma | TOTP sirini va QR (`otpauth://`) ni qaytaradi |
| POST | `/auth/mfa/confirm` | hamma | `{code}` → 2FA yoqiladi, 10 ta zaxira kod qaytariladi (faqat bir marta) |
| GET | `/auth/sessions` | hamma | Faol sessiyalar |
| DELETE | `/auth/sessions/{id}` | hamma | Sessiyani tugatish |
| GET/POST | `/users/` | owner | Foydalanuvchilar ro'yxati / yaratish (`role`, `projects[]`) |
| GET/PATCH/DELETE | `/users/{id}` | owner | Ko'rish / o'zgartirish (rol, faollik) / o'chirish (aslida o'chirib qo'yish, `is_active=false`) |
| POST | `/users/{id}/unlock` | owner | Bloklangan hisobni ochish |

Namuna:

```http
POST /api/v1/auth/login
Content-Type: application/json

{"login": "jasur", "password": "********"}
```

```json
HTTP/1.1 200 OK
Set-Cookie: __Host-nzr_sid=...; HttpOnly; Secure; SameSite=Lax; Path=/

{"user": {"id": "0193...", "login": "jasur", "role": "owner", "language": "uz",
          "timezone": "Asia/Tashkent", "mfa_enabled": true}}
```

## 9.3. Serverlar

| Metod | Yo'l | Rol | Tavsif |
|---|---|---|---|
| GET | `/servers/` | hamma | Ro'yxat (filtr: `status`, `tag`, `q`) |
| POST | `/servers/` | owner, operator | Yangi server yaratish → enroll tokeni va o'rnatish buyrug'ini qaytaradi |
| GET | `/servers/{id}` | hamma | Tafsilot: reyestr maydonlari, `facts`, so'nggi qiymatlar, ochiq incidentlar soni, `clock_skew_seconds` (agent o'lchagan soat farqi, 5 daqiqadan eski bo'lsa `null`; FR-AGT-012) |
| PATCH | `/servers/{id}` | owner, operator | Maydonlarni o'zgartirish |
| POST | `/servers/{id}/pause` | owner, operator | `{reason, until?}` → pauza (FR-HST-016) |
| POST | `/servers/{id}/resume` | owner, operator | Pauzani bekor qilish |
| POST | `/servers/{id}/archive` | owner | Arxivga o'tkazish |
| POST | `/servers/{id}/agent-update` | owner | Agentni eng yangi relizga yangilashni so'rash (FR-AGT-008, 7.7.3). `202` + server (`agent_update_to`). `409`: agent versiyasi noma'lum/dev, arxitektura noma'lum, core'da reliz fayllari yo'q yoki agent allaqachon eng yangi |
| DELETE | `/servers/{id}/agent-update` | owner | So'rovni bekor qilish (`409`, agar so'ralmagan bo'lsa) |
| GET | `/servers/{id}/events` | hamma | Reboot, fakt o'zgarishi, yangilanish tarixi |

> **Server obyektidagi agent maydonlari (S11, FR-AGT-008/011):** `agent_version` (agent bildirgan), `agent_update_to` (Owner so'ragan nishon, bo'sh bo'lsa so'ralmagan), `agent_latest` (core'dagi `VERSION`, reliz fayllari yo'q bo'lsa `null`), `agent_outdated` (`true` eskirgan, `false` yangi, `null` noma'lum: `dev` build yoki reliz yo'q). Ro'yxatda `VERSION` bir so'rovda bir marta o'qiladi.
| GET | `/servers/{id}/containers` | hamma | Konteynerlar va oxirgi qiymatlari |
| GET | `/servers/{id}/services` | hamma | systemd servislar |
| GET | `/servers/{id}/filesystems` | hamma | Fayl tizimlari, bandlik, bashorat (to'lishga qolgan kun) |
| POST | `/servers/{id}/enroll-token` | owner | Yangi bir martalik enroll tokeni (1 soat amal qiladi) |
| GET | `/servers/{id}/tokens` | owner | Agent tokenlari ro'yxati (token qiymatisiz) |
| DELETE | `/servers/{id}/tokens/{token_id}` | owner | Tokenni bekor qilish |

Qoidalar (S4): `GET /servers/` — `status` (arxivlangan faqat `?status=archived` bilan), `tag`, `q` (nom, provayder, IP boshi). `PATCH` da `status` va `name` dan boshqa tizim maydonlari o'zgarmaydi; nom takrorlansa `409`. `pause`: `{reason (majburiy), until? (≤ 90 kun)}`, muddat tugagach evaluator o'zi davom ettiradi; allaqachon pauzada bo'lsa `409`. `archive`: tokenlar bekor qilinadi, server alert bermaydi, tarix saqlanadi. `tokens` javobida token qiymati yo'q (faqat xesh saqlanadi). `GET /servers/{id}` ga `open_incidents` qo'shilgan.

Namuna — server yaratish:

```http
POST /api/v1/servers/
{"name": "main-2", "provider": "Contabo", "public_ipv4": "164.68.105.194",
 "role": "production", "tags": ["contabo", "docker"]}
```

```json
201 Created
{
  "id": "0193c0de-7a4e-7b3a-9d41-2f6c8e5a1b90",
  "name": "main-2",
  "status": "new",
  "enroll": {
    "token": "enr_Zk3...",
    "expires_at": "2026-10-22T10:35:00Z",
    "install_command": "curl -fsSL https://nazoratchi.example.uz/install.sh | sudo bash -s -- --token enr_Zk3..."
  }
}
```

## 9.4. Loyihalar, domenlar, servislar

| Metod | Yo'l | Rol | Tavsif |
|---|---|---|---|
| GET | `/projects/` | hamma (L) | Birlashtirilgan ro'yxat (FR-REG-004): domenlar, serverlar, holat, oxirgi zaxira yoshi, eng yaqin sertifikat muddati |
| POST | `/projects/` | owner, operator | Loyiha yaratish (`domains[]` bilan birga — avtomatik tekshiruvlar yaratiladi) |
| GET | `/projects/{id}` | hamma (L) | Tafsilot |
| PATCH | `/projects/{id}` | owner, operator | O'zgartirish |
| POST | `/projects/{id}/archive` | owner | Arxivlash |
| GET | `/projects/{id}/status` | hamma (L) | Umumiy holat: domenlar (HTTP/TLS/DNS), konteynerlar, servislar, zaxira, incidentlar |
| PUT | `/projects/{id}/servers` | owner, operator | Serverlarga biriktirish (`[{server_id, environment, ports}]`); port to'qnashuvida `409` |
| GET | `/projects/ports/next` | owner, operator | `?server_id=` uchun keyingi bo'sh port juftligi |
| GET | `/domains/` | hamma (L) | Domenlar ro'yxati (`filter[days_left_lt]=21`, `filter[dns_ok]=false`) |
| POST | `/domains/` | owner, operator | Domen yaratish; `auto_probes=true` bo'lsa HTTP, TLS, DNS tekshiruvlari yaratiladi |
| GET/PATCH | `/domains/{id}` | hamma (L) / owner, operator | Ko'rish / o'zgartirish |
| GET | `/domains/{id}/dns` | hamma (L) | Resolverlar bo'yicha oxirgi natija va o'zgarishlar tarixi |
| POST | `/domains/{id}/dns/watch` | owner, operator | Tarqalish rejimi (FR-DNS-005): `{expect_ips:[...], until}` |
| PUT | `/domains/{id}/whois` | owner, operator | Domen muddatini qo'lda kiritish (`.uz` uchun) |
| GET | `/registry/export` | owner | Butun reyestr YAML/JSON (FR-REG-009) |
| POST | `/registry/import` | owner | Reyestrni import qilish (`?dry_run=true` bilan farqni ko'rsatadi) |

Qoidalar (S4):

- `POST /projects/` tanasi: loyiha maydonlari + ixtiyoriy `servers: [{server_id, environment, ports}]`, `domains: [{fqdn, ...}]`, `auto_probes` (standart `true`: ko'chirilgan loyihaning har domeni uchun HTTP tekshiruv). Hammasi bitta tranzaksiyada: biror domen takrorlansa loyiha ham yaratilmaydi (`409`). `slug` yaratilgandan keyin o'zgarmaydi.
- **Port to'qnashuvi:** faol loyihalar orasida bir serverda bir port ikki marta berilsa `409 port_conflict`, `details[]` da band qilgan loyiha va keyingi bo'sh port taklifi. Arxivlangan loyiha portni bo'shatadi. Portlar 1024–65535, bir biriktirishda ≤ 10 ta; berilgan tartib saqlanadi.
- **Keyingi bo'sh port** (`GET /projects/ports/next?server_id=`): `[A, B]`, A — 8000–8999 dagi eng kichik bo'sh port, B — `3000 + (A − 8000)`, u band bo'lsa 3000–3999 dagi eng kichik bo'sh. (REGISTRY.md qoidasining amalga oshirilgan talqini; hujjat bilan farq qilsa, shu yerni yangilang.)
- `domains`: `fqdn` kichik harfga keltiriladi, oxirgi nuqta olib tashlanadi, IP va bir bo'g'inli nomlar rad etiladi. Domen `archived` bo'lsa uning tekshiruvlari o'chadi. Loyiha arxivlansa, uning tekshiruvlari ham o'chadi (alert yo'q, tarix qoladi).
- `GET /projects/` standart holatda arxivlanganlarni ko'rsatmaydi; filtrlar: `status`, `q` (nom, slug, domen), `tag`, `server_id`, `moved`.
- S5 da qo'shilgan: `GET /domains/{id}/dns` (har resolver bo'yicha oxirgi natija va `changes[]` o'zgarishlar tarixi). Yaratilmagan: `/projects/{id}/status`, `/domains/{id}/dns/watch`, `/domains/{id}/whois` (F2), `/registry/export|import` (F2).

## 9.5. Metrikalar so'rovi

| Metod | Yo'l | Rol | Tavsif |
|---|---|---|---|
| GET | `/metrics/query` | hamma (L) | Vaqt qatorini olish |
| GET | `/metrics/latest` | hamma (L) | Server uchun oxirgi qiymatlar: `?server_id=&names=cpu_busy_percent,mem_used_percent` |
| GET | `/metrics/names` | hamma | Mavjud metrika nomlari va belgilar |
| GET | `/metrics/top` | hamma (L) | Eng yuklangan (CPU/RAM/disk) serverlar va konteynerlar |

`/metrics/query` parametrlari:

| Parametr | Majburiy | Tavsif |
|---|---|---|
| `server_id` | ha | Server |
| `name` | ha | Metrika nomi (`cpu_busy_percent`) |
| `labels` | yo'q | `labels[mount]=/` |
| `from`, `to` | ha | ISO vaqt; `to` ≤ hozir |
| `step` | yo'q | Soniya; ko'rsatilmasa avtomatik (`max_points=1000`) |
| `agg` | yo'q | `avg` (standart), `min`, `max`, `last` |
| `max_points` | yo'q | 100–2000, standart 1000 |

```http
GET /api/v1/metrics/query?server_id=0193c0de-...&name=cpu_busy_percent&from=2026-10-22T08:00:00Z&to=2026-10-22T09:00:00Z
```

```json
{
  "name": "cpu_busy_percent",
  "unit": "%",
  "step_seconds": 15,
  "source": "raw",
  "series": [
    {"labels": {}, "points": [[1761120000000, 11.8], [1761120015000, 12.4], [1761120030000, 13.0]]}
  ]
}
```

Qoidalar (S4-S5): `step` (soniya) berilsa nuqtalar soni `ceil(oraliq/step)` (≤ 2000); aks holda `max_points` (100–2000, standart 1000). Oraliq ≤ 400 kun, `to` kelajakda bo'lmasligi kerak (≤ 1 daqiqa tolerantlik), `from`/`to` vaqt zonasi bilan. `agg`: `avg|min|max|last`. Ko'pi bilan 50 seriya. **Bo'shliq:** qo'shni nuqtalar orasi `max(3 qadam, 2 daqiqa)` dan uzoq bo'lsa, orasiga `null` nuqta qo'yiladi (agent jim bo'lgan davr grafikda uziladi, oddiy 15-30 s namuna oralig'i bo'shliq emas). `GET /metrics/latest?server_id=&names=a,b` — har seriyaning oxirgi qiymati. `GET /metrics/names[?server_id=]` — nom, birlik, tur, belgi kalitlari. `GET /metrics/top?metric=&limit=` — oxirgi 5 daqiqadagi qiymat bo'yicha kamayish tartibida (arxivlangan serverlar yashirin). `GET /servers/{id}/containers` — konteynerlar va oxirgi qiymatlari (5 daqiqadan eskisi `stale: true`); `GET /servers/{id}/filesystems` — bandlik va `days_until_full` (oxirgi 6 soat, R² ≥ 0.5 bo'lsa).

`points` — `[vaqt_ms, qiymat]` juftliklari (ixcham). `source` — qaysi daraja ishlatilgani:
`raw`, `1m`, `5m`, `1h` (8.4.3). Ma'lumot bo'lmagan oraliqlar `null` qiymat bilan beriladi
(grafikda bo'shliq).

## 9.6. Faol tekshiruvlar

| Metod | Yo'l | Rol | Tavsif |
|---|---|---|---|
| GET | `/probes/` | hamma (L) | Ro'yxat (filtr: `type`, `state`, `project_id`) |
| POST | `/probes/` | owner, operator | Yaratish |
| GET | `/probes/{id}` | hamma (L) | Tafsilot va oxirgi natija |
| PATCH | `/probes/{id}` | owner, operator | O'zgartirish (interval, chegara, yoqish/o'chirish) |
| DELETE | `/probes/{id}` | owner | O'chirish (aslida arxiv) |
| POST | `/probes/{id}/run` | owner, operator | Zudlik bilan bir marta bajarish (natija javobda) |
| GET | `/probes/{id}/results` | hamma (L) | Natijalar tarixi (`from`, `to`, `limit`) |
| GET | `/probes/{id}/uptime` | hamma (L) | Uptime %: 24 soat, 7, 30, 90 kun |
| GET | `/certs/` | hamma (L) | Barcha sertifikatlar va qolgan kun |

Namuna — HTTP tekshiruv yaratish:

```json
POST /api/v1/probes/
{
  "type": "http",
  "project_id": "0193...",
  "domain_id": "0193...",
  "name": "Nazar healthz",
  "interval_s": 60,
  "timeout_s": 10,
  "config": {
    "url": "https://nazar.avlo.ai/healthz/",
    "method": "GET",
    "expected_status": [200],
    "keyword": null,
    "follow_redirects": true,
    "max_redirects": 5,
    "headers": {"X-Check": "nazoratchi"},
    "latency_warn_ms": 3000
  }
}
```

Konfiguratsiya sxemalari (tur bo'yicha) 18.4-bo'limda.

Qoidalar (S4): hozircha `http` va `tcp` turlari (qolganlari `400`). `DELETE` tekshiruvni o'chirmaydi: `enabled=false`, `state=paused` (tarix saqlanadi); qayta yoqilganda holat `unknown` dan boshlanadi. `config.allow_private=true` (ichki manzillarga ruxsat, SSRF) faqat Owner tomonidan o'rnatiladi. `POST /probes/{id}/run` — bir marta bajaradi, natijani qayd etadi va tasdiqlash qoidasini qo'llaydi. `GET /probes/{id}/results`: `from`, `to`, `limit` (≤ 500). `GET /probes/{id}/uptime`: 1, 7, 30, 90 kun. `GET /certs/` — sertifikatlar va `days_left` (`?days_left_lt=21`, `?project_id=`), muddati yaqinlari birinchi. TLS va DNS turlari endi qo'llab-quvvatlanadi (`tls`: 18.4.3, `dns`: 18.4.4; DNS uchun `domain` majburiy emas, lekin tarix faqat domenli tekshiruvlar uchun yoziladi); `whois` — F2.

## 9.7. Zaxira nusxalar

| Metod | Yo'l | Rol | Tavsif |
|---|---|---|---|
| GET | `/backups/overview` | hamma (L) | Barcha loyihalar bo'yicha jadval: oxirgi zaxira, yoshi, hajmi, offsite, oxirgi drill |
| GET | `/backups/projects/{project_id}` | hamma (L) | Loyiha zaxira kartasi: oxirgi 30 ta run, hajm grafigi, holat |
| GET | `/backups/runs` | hamma (L) | Run'lar ro'yxati (`project`, `status`, `from`, `to`) |
| GET | `/backups/offsite` | hamma (L) | Mahalliy va offsite solishtirish |
| GET | `/backups/drills` | hamma (L) | Restore drill tarixi |
| POST | `/backups/drills` | owner, operator | Drill natijasini kiritish |
| PATCH | `/backups/drills/{id}` | owner, operator | Tuzatish |
| GET/PUT | `/backups/policy` | owner | Har loyiha uchun siyosat: kutilgan yosh (26 s), hajm chegarasi, drill davriyligi (90 kun) |

> **F1 S10 da qo'shildi:** `GET/POST /backups/drills` (filtr `project`, `result`), `GET/PATCH /backups/drills/{id}`; `drills` yo'li `{slug}` dan oldin. Tanasi: `project` (slug), `performed_at`, `backup_file`, `backup_age_h`, `duration_s`, `tables_count`, `rows_count`, `result` (`success|partial|failed`), `notes`; kelajak sanasi rad etiladi, loyihani PATCH bilan o'zgartirib bo'lmaydi, har yozuv audit'ga tushadi. `GET /backups/` va `GET /backups/{slug}` javobida `drill` bloki: `every_days` (siyosatdagi `drill_every_days`, standart 90), `last`, `last_success_days`, `never`, `overdue`; karta qo'shimcha `drills` (oxirgi 20). AL-081…083 hali F2.
> **S6 da amalga oshirilgan (soddalashtirilgan yo'llar):** `GET /backups/` (jadval) va `GET /backups/{slug}` (karta). Yuqoridagi `/backups/overview`, `/projects/{id}`, `/runs`, `/offsite`, `/drills`, `/policy` — F2. Siyosat hozircha `PATCH /projects/{id}` dagi `backup` maydoni orqali.
> `GET /backups/` elementi: `project, project_id, name, server, server_id, expect_daily, expect_weekly_files, require_offsite, state, age_hours, last_success_at, last_size_bytes, last_status (ok|fail|null), daily_count, weekly_count, files_count, newest_age_seconds{kind}, offsite_configured (server darajasida), data_seen_at`. `state`: `ok`, `late` (> 26 s), `critical` (> 50 s), `failed` (oxirgi zaxira xato), `stale` (agent 15 daqiqadan beri jim: ma'lumot ishonchsiz), `missing` (kutilgan, lekin hech qachon olinmagan, loyiha ≥ 26 soatlik), `unknown` (yangi loyiha), `none` (zaxira kutilmaydi). Ro'yxatga faqat faol, ko'chirilgan va siyosati bor yoki agent ma'lumot yuborayotgan loyihalar kiradi. Karta qo'shimcha: `runs[]` (oxirgi 30, eskidan yangiga: `finished_at, size_bytes`), `size_median_7`, `size_ratio`, `size_anomaly`.

Namuna — `GET /backups/overview` javobi:

```json
{
  "generated_at": "2026-10-22T09:35:00Z",
  "items": [
    {
      "project": {"id": "0193...", "slug": "BiznesRadar", "name": "BiznesRadar"},
      "server": "main-2",
      "last_success_at": "2026-10-22T03:15:41Z",
      "age_hours": 6.3,
      "size_bytes": 48273114,
      "gz_ok": true,
      "daily_count": 7, "weekly_count": 5,
      "offsite": {"configured": true, "last_success_at": "2026-10-22T03:16:55Z", "in_sync": true},
      "last_drill": {"performed_at": "2026-09-30T10:00:00Z", "result": "success", "days_ago": 22},
      "status": "ok"
    },
    {
      "project": {"slug": "lutfan_ai"},
      "age_hours": 31.2,
      "status": "stale",
      "problems": ["backup_too_old"]
    }
  ]
}
```

`status` qiymatlari: `ok`, `warning` (offsite yo'q, drill muddati o'tgan), `stale` (yosh >
chegara), `failed` (oxirgi run `fail`), `suspicious` (hajm anomaliyasi), `unknown`.

## 9.8. Alertlar va incidentlar

| Metod | Yo'l | Rol | Tavsif |
|---|---|---|---|
| GET | `/alert-rules/` | hamma | Qoidalar (filtr: `enabled`, `severity`, `built_in`) |
| POST | `/alert-rules/` | owner, operator | Yangi qoida |
| GET/PATCH | `/alert-rules/{id}` | hamma / owner, operator | Ko'rish / o'zgartirish |
| POST | `/alert-rules/{id}/test` | owner, operator | Qoidani hozirgi ma'lumotda quruq hisoblash (kim "firing" bo'lardi), alert yubormasdan |
| GET | `/alerts/` | hamma (L) | Faol alert instance lar (`pending`/`firing`/`resolving`) |
| GET | `/incidents/` | hamma (L) | Incidentlar (`filter[status]`, `severity`, `server_id`, `project_id`, `from`, `to`) |
| GET | `/incidents/{id}` | hamma (L) | Tafsilot: alertlar, ta'sirlanganlar, vaqt chizig'i |
| POST | `/incidents/{id}/ack` | owner, operator | Qabul qilish (`{comment?}`) |
| POST | `/incidents/{id}/comments` | owner, operator | Izoh |
| PATCH | `/incidents/{id}` | owner, operator | `root_cause` ni kiritish |
| POST | `/incidents/{id}/resolve` | owner, operator | Qo'lda yopish (faqat shart allaqachon yo'qolgan bo'lsa; aks holda `409`) |
| GET/POST | `/silences/` | hamma / owner, operator | Ro'yxat / yaratish (`matchers`, `ends_at`, `reason`) |
| DELETE | `/silences/{id}` | owner, operator | Bekor qilish |
| GET/POST | `/maintenance/` | hamma / owner, operator | Ro'yxat / yaratish |
| DELETE | `/maintenance/{id}` | owner, operator | Bekor qilish |

Namuna — silence:

```json
POST /api/v1/silences/
{
  "matchers": [{"label": "server", "op": "=", "value": "main-2"},
               {"label": "severity", "op": "!=", "value": "critical"}],
  "ends_at": "2026-10-22T12:00:00Z",
  "reason": "Kernel yangilanishi va reboot"
}
```

## 9.9. Bildirishnoma kanallari

| Metod | Yo'l | Rol | Tavsif |
|---|---|---|---|
| GET | `/channels/` | owner | Kanallar (maxfiy maydonlarsiz: `bot_token: "••••"`) |
| POST | `/channels/` | owner | Yaratish |
| PATCH/DELETE | `/channels/{id}` | owner | O'zgartirish / o'chirish |
| POST | `/channels/{id}/test` | owner | Sinov xabari (FR-ALR-020) |
| GET | `/notifications/` | owner, operator | Yuborilgan xabarlar tarixi (muvaffaqiyat/xato); `?channel=`, `?status=`, `?before=<id>` |
| POST | `/telegram/webhook/{secret}` | Telegram | Bot callback (9.12) |

Qoidalar (F1 S2):

- Yaratishda `config` yoziladi: `{"bot_token": "123456:ABC...", "chat_id": -1001234567890}` (`chat_id` — butun son
  yoki `@kanal_nomi`). Javobda `config` **hech qachon** qaytmaydi, o'rniga `config_masked`:
  `{"bot_token": "••••", "chat_id": ...}`. Audit jurnaliga ham sir tushmaydi.
- `PATCH` da `config` qisman bo'lishi mumkin: berilmagan kalit (masalan, `bot_token`) eskicha qoladi.
  Kanal turini o'zgartirib bo'lmaydi. Hozircha faqat `telegram` (email F2, webhook F3) — qolganlari `400`.
- `POST /channels/{id}/test`: bitta urinish, qayta urinishsiz. Muvaffaqiyatda `200 {"ok": true}`, Telegram xatosida
  `502 {"ok": false, "error": "..."}` (xato matnida token bo'lmaydi).
- `GET /notifications/`: 50 tadan, yangisidan eskisiga; keyingi sahifa uchun `next_before` qiymatini `?before=` ga bering
  (`null` — oxiri). Xabar matni va sirlar tarixda qaytmaydi.

## 9.10. Hisobotlar, audit, tizim

| Metod | Yo'l | Rol | Tavsif |
|---|---|---|---|
| GET | `/reports/uptime` | hamma (L) | Oy/chorak uptime (`from`, `to`, `group=project` yoki `group=domain`) |
| GET | `/reports/incidents` | hamma (L) | Incident statistikasi: soni, MTTR, ahamiyat bo'yicha |
| GET | `/reports/backups` | hamma (L) | Zaxira muvaffaqiyat foizi |
| GET | `/reports/weekly` | owner, operator | Haftalik hisobot (JSON/PDF: `Accept: application/pdf`) |
| GET | `/audit/` | owner | Audit jurnali (`user`, `action`, `from`, `to`) |
| GET | `/settings/` | owner | Tizim sozlamalari (retention, standart kanallar, chegaralar) |
| PATCH | `/settings/` | owner | O'zgartirish |
| GET | `/system/status` | owner, operator | Nazoratchi o'zining holati: evaluator, prober, navbat, baza hajmi, oxirgi zaxira |
| GET | `/dashboard/summary` | hamma (L) | Bosh sahifa ma'lumoti: banner holati, sonlar, eng yaqin muddatlar |
| GET | `/stream` | hamma (L) | SSE oqimi (9.11) |

## 9.11. SSE oqimi

```http
GET /api/v1/stream?scope=dashboard
Accept: text/event-stream
```

Voqealar (`event:` turi va `data:` JSON):

| Voqea | Qachon | `data` |
|---|---|---|
| `host.status` | Host holati o'zgarganda | `{"server_id":"...","status":"offline","since":"..."}` |
| `host.metrics` | Har 5 s (partiya) | `{"server_id":"...","cpu":12.4,"mem":41.8,"disk":23.1}` |
| `incident.opened` / `incident.updated` / `incident.resolved` | Incident o'zgarganda | Incident qisqa obyekti |
| `probe.state` | Tekshiruv holati o'zgarganda | `{"probe_id":"...","state":"down"}` |
| `backup.updated` | Zaxira holati yangilanganda | `{"project":"BiznesRadar","status":"ok"}` |
| `ping` | Har 25 s | `{}` (aloqani ushlab turish) |

`scope`: `dashboard`, `server:<id>`, `project:<id>`, `incidents`. Cheklangan viewer faqat o'z
loyihalariga tegishli voqealarni oladi. `Last-Event-ID` bilan qayta ulanganda o'tkazib
yuborilgan voqealar (5 daqiqagacha) qayta yuboriladi.

## 9.12. Telegram webhook

`POST /api/v1/telegram/webhook/{secret}` — Telegram yuboradi. Talablar:

1. `X-Telegram-Bot-Api-Secret-Token` sarlavhasi sozlamadagi qiymatga teng bo'lishi kerak.
2. `callback_query.from.id` / `message.chat.id` ruxsat etilgan chat ID lar ro'yxatida bo'lishi kerak.
3. `callback_data` formati: `ack:<incident_id>:<sig>`, `snz:<incident_id>:<daqiqa>:<sig>`. `sig` — HMAC-SHA256 ning dastlabki 12 hex belgisi
   (kalit `SECRET_KEY` dan olingan; butun qiymat Telegram chegarasi 64 baytga sig'adi). Muddat 15 daqiqadan 24 soatgacha.
   Chat ID kanallardan birining `chat_id` siga teng bo'lishi shart. Bosgan odam `users.telegram_chat_id` bilan bog'langan bo'lsa, uning roli tekshiriladi (`viewer` rad etiladi, audit shu foydalanuvchi nomidan); bog'lanmagan bo'lsa chat ruxsati yetarli va amal `telegram:<username>` deb yoziladi.
   "1 soat jim" qamrovi: host incident'i — `server`, loyiha incident'i — `project`, qolgani — `rule`.
   Maxfiy kalit `TELEGRAM_WEBHOOK_SECRET`: URL segmenti VA sarlavha ikkalasi ham shunga teng bo'lishi kerak; bo'sh bo'lsa webhook o'chiq. O'rnatish: `setWebhook(url=https://<core>/api/v1/telegram/webhook/<secret>, secret_token=<secret>)`.
4. Javob har doim `200` (Telegram qayta yubormasligi uchun); ruxsatsiz so'rov faqat loglanadi.

Qo'llab-quvvatlanadigan bot buyruqlari (F2):

| Buyruq | Natija |
|---|---|
| `/status` | Qisqa umumiy holat (serverlar, ochiq incidentlar) |
| `/incidents` | Ochiq incidentlar |
| `/silence <server> <daqiqa> <sabab>` | Jim qilish |
| `/backups` | Zaxira holati |
| `/help` | Yordam |

## 9.13. Agent (ingest) endpointlari

Protokol tafsiloti 7.5-bo'limda. Qisqa jadval:

| Metod | Yo'l | Autentifikatsiya | Tavsif |
|---|---|---|---|
| POST | `/ingest/v1/enroll` | `enroll_token` (tanada) | Enroll |
| POST | `/ingest/v1/metrics` | Bearer `agt_` | Metrika paketi |
| POST | `/ingest/v1/goodbye` | Bearer `agt_` | Agent o'chirildi |
| GET | `/agent/v1/latest` | — | `{version, sha256, url}` (oxirgi agent versiyasi) |
| GET | `/agent/v1/nazoratchi-agent-{arch}` | — | Agent binari |
| GET | `/install.sh` | — | O'rnatish skripti |

## 9.14. Kiruvchi heartbeat (cron va skriptlar uchun)

```
GET|POST https://<core>/hb/<token>[?status=ok|fail][&msg=<qisqa matn>][&duration=<s>]
```

- `token` — `heartbeat_jobs` yaratilganda berilgan maxfiy kalit (URL da; shuning uchun
  alohida, tor ruxsatli).
- `status` ko'rsatilmasa `ok`. `fail` — darhol alert (`AL-048`).
- `msg` 200 belgigacha; maxfiy ma'lumot yubormaslik ogohlantiriladi.
- Javob: `200 ok` (matn), tezkor (< 50 ms), tezlik cheklovi: token bo'yicha daqiqada 10.

Namuna — `appctl-backup` uchun (E-03): cron qatori o'zgarmaydi, heartbeat'ni `appctl` o'zi yuboradi
(10.3.5). Token `appctl.secret` ga yoziladi:

```bash
sudo bash setup.sh --heartbeat-url=https://nazoratchi.example.uz/hb/<TOKEN>   # yoki: appctl heartbeat-set <url>
appctl heartbeat ok                                                           # qo'lda sinash
```

```cron
15 3 * * * root /usr/local/bin/appctl backup all >> /var/log/appctl-backup.log 2>&1
```

Eski namunadagi \ bilan ko'p qatorli `&& curl ... || curl ...` zanjiri `/etc/cron.d` da ishlamaydi (qator
bo'linmaydi) va faqat `curl` yiqilganda ham noto'g'ri `fail` yuboradi, shuning uchun almashtirildi.

## 9.15. Tizim endpointlari

| Metod | Yo'l | Kirish | Javob |
|---|---|---|---|
| GET | `/healthz` | ichki/tashqi watchdog | Liveness: `200 {"status":"ok"}` yoki `503` (baza/navbat) |
| GET | `/readyz` | ichki | Tayyorlik: baza, Redis, notifier va evaluator yurak urishi (tsikl yangi) tekshiriladi; biri yiqilsa `503` |
| GET | `/metrics` | `METRICS_TOKEN` yoki faqat loopback | Prometheus matni (NFR-OBS-001); nginx tashqariga bermaydi |
| GET | `/api/v1/version` | hamma | `{"version":"1.0.0","build":"...","agent_latest":"1.0.0"}` |

> **S7 da amalga oshirilgan:** evaluator har tsikl muvaffaqiyatli tugagach (kamida 60 s oralig'ida) `WATCHDOG_URL` (`https://<host>/ping/<id>`) ga ping yuboradi; tsikl yiqilsa ping to'xtaydi va watchdog 5 daqiqada xabar beradi (AL-084). `WATCHDOG_URL` `https://` bo'lishi shart (maxfiy id ochiq ketmasligi uchun; loopback `http` mumkin). Tarqatish: `GET /install.sh` (`__CORE_URL__`, `__MINISIGN_PUBKEY__` almashtiriladi; kalit yo'q bo'lsa `503`), `GET /agent/v1/<nazoratchi-agent-amd64|arm64|SHA256SUMS|SHA256SUMS.minisig>` (oq ro'yxat).

## 9.16. Moslik va o'zgarishlar siyosati

- Javobga yangi maydon qo'shish — buzuvchi emas (klient noma'lum maydonlarni e'tiborsiz
  qoldirishi kerak).
- Maydonni o'chirish yoki ma'nosini o'zgartirish — buzuvchi, yangi versiya.
- Agent protokoli alohida versiyalanadi (`/ingest/v1/`); eski agentlar kamida 2 minor
  versiya davomida qo'llab-quvvatlanadi (NFR-MNT-009).
- Barcha o'zgartiruvchi so'rovlar audit jurnaliga yoziladi (FR-AUD-001).
