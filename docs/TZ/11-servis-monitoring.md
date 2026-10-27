# 11. Loyiha, servis, domen va sertifikat monitoringi

Bu bo'lim ikki xil kuzatuvni birlashtiradi:

- **Tashqaridan (faol)** — core'dagi `prober` mijoz nuqtai nazaridan tekshiradi: sayt ochiladimi,
  sertifikat yaroqlimi, DNS to'g'ri joyga qaraydimi.
- **Ichkaridan (passiv)** — agent serverning ichidan ko'radi: konteyner, systemd servis, cron.

Ikkalasi ham kerak: "tashqaridan ishlamayapti, ichkaridan hammasi yaxshi" holati (masalan, DNS
yoki nginx muammosi) va "tashqaridan ishlayapti, lekin ichkarida worker o'lgan" holati faqat
shu birlashma bilan topiladi.

## 11.1. Loyiha holati qanday hisoblanadi

Loyiha kartasidagi umumiy rang quyidagi tarkibiy qismlardan **eng yomoni** bo'yicha olinadi:

| Tarkibiy qism | Manba | Qizil bo'ladi, agar | Sariq bo'ladi, agar |
|---|---|---|---|
| **Domenlar (HTTP)** | prober | Hech bo'lmaganda bitta asosiy domen `down` | Sekin javob yoki bitta ikkilamchi domen `down` |
| **Sertifikat** | prober, agent | ≤ 3 kun yoki yaroqsiz | ≤ 21 kun |
| **DNS** | prober | Kutilgan IP ga qaramaydi (10 daq. dan ko'p) | Resolverlar bir-biriga mos kelmaydi |
| **Konteynerlar/servislar** | agent | Kutilgan konteyner ishlamayapti / `unhealthy` / crash loop | Qayta ishga tushishlar ko'p, xotira limitga yaqin |
| **Zaxira** | agent | `failed`, `stale` | Offsite yo'q, drill muddati o'tgan |
| **Server** | agent | Server o'chiq | Disk/RAM ogohlantirish |
| **Incident** | alert tizimi | Ochiq `critical`/`high` incident | Ochiq `warning` |

Kulrang — "noma'lum": ma'lumot kelmayapti yoki loyiha pauzada/ko'chirilmagan.

Har tarkibiy qismning holati loyiha sahifasida alohida ko'rinadi; umumiy rang faqat
bosh sahifadagi xulosa uchun.

## 11.2. HTTP(S) tekshiruvlari

### 11.2.1. Tekshiruv bajarilishi (bir urinish)

1. DNS so'rov (tizim resolveri, vaqt o'lchanadi).
2. TCP ulanish (`connect_ms`).
3. TLS qo'l siqish (`tls_ms`), sertifikat tekshiruvi (zanjir, hostname, muddat).
4. HTTP so'rov (`GET` yoki `HEAD`), sarlavhalar: `User-Agent: Nazoratchi/1.0 (+https://<core>/about)`,
   foydalanuvchi sarlavhalari.
5. Birinchi bayt (`ttfb_ms`) va to'liq javob (`total_ms`) vaqti; javob tanasi birinchi 64 KB gacha
   o'qiladi (kalit so'z tekshiruvi uchun).
6. Baholash: status kodi kutilgan oraliqda; kalit so'z (bo'lsa); vaqt chegarasi.

### 11.2.2. Tasdiqlash qoidasi

Soxta (bir martalik) xatoni alert qilmaslik uchun:

```
urinish 1 muvaffaqiyatsiz → 15 s kutish → urinish 2 → 15 s kutish → urinish 3
3 ta ketma-ket muvaffaqiyatsiz  → holat = DOWN   (alert hisoblash `for` bilan davom etadi)
1 ta muvaffaqiyat               → holat = UP
```

Shu sababli eng tez aniqlash vaqti ≈ 30 s (qayta urinishlar) + interval (60 s) kechikishi:
**≤ 90 soniya** (G-2).

### 11.2.3. Xato turlari

| `error_kind` | Sabab | Odatdagi ma'nosi |
|---|---|---|
| `dns` | Nom hal qilinmadi | DNS yozuvi yo'q/xato |
| `connect` | TCP ulanmadi / timeout | Server o'chiq, firewall, port yopiq |
| `tls` | Qo'l siqish/sertifikat xatosi | Sertifikat tugagan, hostname mos emas |
| `timeout` | Javob vaqti oshdi | Ilova qotgan, server haddan tashqari band |
| `status` | Kutilmagan status kodi | 5xx — ilova xatosi; 4xx — sozlama |
| `keyword` | Kalit so'z topilmadi/topildi (teskari rejim) | Soxta "xizmat ishlamayapti" sahifasi |
| `redirect` | Yo'naltirish halqasi / ko'p yo'naltirish | nginx/ilova sozlamasi |

Alert xabarida shu turdan kelib chiqib **birinchi tekshirish qadami** ko'rsatiladi
(masalan, `connect` → "serverga ulanish: RB-001", `tls` → "RB-006").

### 11.2.4. Django loyihalar uchun maxsus sozlama

Nazar kabi Django loyihalar tashqi so'rovni `ALLOWED_HOSTS` va `SECURE_SSL_REDIRECT` tufayli
`400`/`301` bilan rad etishi mumkin (bu 2026-10 da bevosita uchragan). Nazoratchi'da:

- Odatiy: haqiqiy domen orqali `https://` bilan tekshirish — Django uchun hech qanday
  maxsus sozlama kerak emas, chunki so'rov to'g'ri `Host` va `X-Forwarded-Proto` bilan keladi.
- Ichki (loopback) tekshiruv kerak bo'lsa (agent ichidan), `headers` bilan `Host` va
  `X-Forwarded-Proto: https` beriladi (`appctl` dagi `HEALTH_CURL_OPTS` bilan bir xil g'oya).
- Maxsus `healthz` yo'li bo'lsa (Nazar: `/healthz/`), shu ishlatiladi; bo'lmasa — bosh sahifa.

### 11.2.5. Standart tekshiruv to'plami (boshlang'ich seed)

Quyidagi tekshiruvlar Nazoratchi birinchi ishga tushganda reyestrdan avtomatik taklif qilinadi.
"Kutilgan" ustuni 2026-10-22 holatidagi real xatti-harakatga asoslangan; belgi (?) — aniqlash
kerak.

| Loyiha | URL | Kutilgan status | Izoh |
|---|---|---|---|
| Nazar | `https://nazar.avlo.ai/healthz/` | 200 | `healthz` mavjud |
| Nazar | `https://nazar.avlo.ai/` | 200–399 | Til bo'yicha yo'naltirish (307) normal |
| Nazar (Beyondlinks UI) | `https://app.beyondlinks.uz/` | 200–399 | Xuddi shunday |
| BiznesRadar | `https://biznesradar.uz/` | 200 | Bosh sahifa |
| BiznesRadar | `https://api.biznesradar.uz/` | 404 (?) | Ildiz yo'li 404 normal; haqiqiy health yo'li (?) aniqlash |
| BiznesRadar | `https://cabinet.biznesradar.uz/` | 404 (?) | Xuddi shunday |
| BiznesRadar | `https://admin.biznesradar.uz/` | 200–399 (?) | |
| beyondlinks_landing | `https://beyondlinks.uz/` | 200 | Statik |
| freighthubllc | `https://freighthubllc.co/` va `.com` | 200 | Statik |
| avlo.ai | `https://avlo.ai/` | 200 | Statik sayt |
| avlo.ai | `https://avlo.ai/api/` | 404/405 (?) | `GET` ga backend javobi; aniq kodni birinchi sinovda aniqlash |
| asadbekashurov.uz | `https://asadbekashurov.uz/` | 200 | S-02 da |
| asadbekashurov.uz | `https://www.asadbekashurov.uz/` | 301 → asosiy | Yo'naltirishni tekshirish (`follow_redirects=false`) |
| lutfan_ai | `https://lutfanai.uz/` | 200 (?) | DNS GCP da; ko'chirilgach tekshiruv yoqiladi |
| wmg | `https://moliyaviyerkinlik.wmg.uz/`, `https://investitsiya.wmg.uz/` | 200 (?) | DNS mijozda |

### 11.2.6. TCP tekshiruvlari (xavfsizlik va mavjudlik)

| Maqsad | Host:port | Kutilgan |
|---|---|---|
| SSH mavjud (server tirikligi ikkilamchi signal) | `164.68.105.194:22`, `173.249.37.152:22` | ochiq |
| HTTPS ochiq | `...:443` | ochiq |
| **Yopiq bo'lishi kerak** (xavfsizlik) | `...:5432`, `:6379`, `:9000`, `:8020`, `:3017`, `:2375` | yopiq (ulanish rad etiladi) |

Yopiq bo'lishi kerak bo'lgan portlar tekshiruvi (`expect: closed`) — Docker port nashri
`ufw` ni chetlab o'tishi (2026-10 da ko'rilgan) kabi xatolarni topadi (AL-030).

## 11.3. Sertifikat (TLS) monitoringi

### 11.3.1. Ikki manba

| Manba | Nima ko'radi | Qachon foydali |
|---|---|---|
| **Prober** (TLS probe) | Tashqaridan haqiqatan taqdim etilayotgan sertifikat | Ishlayotgan sertifikat — foydalanuvchi ko'radigan narsa |
| **Agent** (`certs`) | Serverdagi `/etc/letsencrypt/live/*` fayllari | Yangilangan, lekin nginx hali o'qimagan (reload qilinmagan) sertifikatni topish |

Ikkalasi taqqoslanadi: agent'dagi sertifikat yangi (`not_after` kattaroq), prober hali eskisini
ko'rsatsa — **"sertifikat yangilangan, lekin nginx reload qilinmagan"** (AL-061 ning
alohida holati). Bu `certbot` deploy-hook muammosining klassik belgisi.

### 11.3.2. Qaysi nomlar tekshiriladi

Har faol domenning FQDN va (agar reyestrda `www` bor bo'lsa) `www.` varianti. Sertifikat SAN
ro'yxatida `FQDN` yo'q bo'lsa — `hostname_ok = false` (AL-060).

### 11.3.3. Chegaralar va ahamiyat

| Qolgan kun | Holat | Alert | Ahamiyat |
|---|---|---|---|
| > 21 | OK | — | — |
| 8–21 | Yaqinlashmoqda | AL-057 | `warning` |
| 4–7 | Yuqori | AL-058 | `high` |
| 1–3 | Kritik | AL-059 | `critical` |
| ≤ 0 | O'tib ketgan | AL-059 (`critical`, "tugadi") | `critical` |

Let's Encrypt sertifikatlari certbot tomonidan **30 kun qolganda** avtomatik yangilanadi;
shuning uchun 21 kunlik ogohlantirish "yangilanish ishlamayapti" degan ishonchli
signal (30 kundan 21 kunga tushgan bo'lsa, kamida ~9 kun yangilash urinishlari muvaffaqiyatsiz
bo'lgan).

### 11.3.4. Yangilanish natijasi

- **S-01 (certbot, nginx authenticator):** agent `/var/log/letsencrypt/letsencrypt.log` dan
  oxirgi `renew` natijasini o'qiydi (`certbot_last_renew_status`).
- **S-02 (`asadbekashurov.uz`, konteyner certbot, kunlik cron):** cron natijasini yozuvchi
  heartbeat (`/hb/<token>`) — `cron: asadbekashurov-certbot` (FR-SVC-004).
- Ikki ketma-ket muvaffaqiyatsiz yangilash → AL-061 (`high`), sertifikat muddati yaqin
  bo'lmasa ham.

### 11.3.5. Maxsus holatlar

| Holat | Nazoratchi qanday ishlaydi |
|---|---|
| Domen DNS i boshqa serverga qaraydi | Sertifikat o'sha server taqdim etganini tekshiradi (Nazoratchi domenning haqiqiy egasini emas, ko'rinayotgan holatni baholaydi); DNS mos emasligi alohida alert (AL-062) |
| Sertifikat yo'q (HTTP faqat) | `tls_enabled = false` bo'lsa tekshirilmaydi |
| Wildcard sertifikat | `SAN` da `*.domen` bo'lsa, subdomenlar mos deb hisoblanadi |
| Front-proksi orqali (S-02: SNI bo'yicha) | Prober `SNI` bilan ulanadi, shuning uchun to'g'ri stekning sertifikatini ko'radi |

## 11.4. DNS va domen monitoringi

### 11.4.1. Reyestrdagi DNS ma'lumoti

Har domen uchun saqlanadi:
- `expected_ips` — qaysi IP lar kutiladi (masalan, `164.68.105.194`);
- `dns_provider` — DNS qayerda boshqariladi (`ahost.uz`, Namecheap, Google Cloud DNS, Beget);
- `controlled_by` — `self` yoki `client` (mijoz o'zgartiradi: wmg.uz);
- `registrar`, domen muddati (WHOIS yoki qo'lda).

### 11.4.2. Tekshirish

Har 5 daqiqada (o'zgartirish rejimida — 1 daqiqada):

| Resolver | Maqsad |
|---|---|
| 8.8.8.8 (Google) | Eng keng tarqalgan; o'zgarishni sekin oladi |
| 1.1.1.1 (Cloudflare) | Tez yangilanadi |
| 9.9.9.9 (Quad9) | Qo'shimcha nuqta |
| Domenning o'z NS serveri (`rdns1.ahost.uz` va h.k.) | **Haqiqat manbai** — o'zgartirish aynan shu yerda ko'rinadi |

**Holatlar:**

| Holat | Ma'nosi | Alert |
|---|---|---|
| `match` | Hammasi kutilgan IP | — |
| `propagating` | NS yangi IP da, ba'zi resolverlar hali eski | Ma'lumot (alert yo'q) |
| `mismatch` | NS ham kutilgan IP ni bermaydi | AL-062 (`high`, 10 daqiqadan keyin) |
| `retired_ip` | Domen **eski/yopilgan** IP ga qaraydi (masalan, o'chirilgan GCP `34.173.220.247`) | AL-063 (`high`) — ko'chirishdan keyin unutilgan yozuv |
| `resolver_disagree` | NS kutilgan, lekin 30+ daqiqadan beri resolverlar mos emas | AL-065 (`warning`) — TTL/kesh muammosi |
| `nxdomain` | Domen mavjud emas | AL-062 (`critical`) |

"Yopilgan IP ro'yxati" sozlamada (`retired_ips = [34.173.220.247]`, o'chirilgan GCP) — Nazoratchi shu IP ga qaragan
har bir domenni darrov belgilaydi. Bu `lutfanai.uz` va `*.wmg.uz` kabi DNS yangilanmagan
domenlarni **avtomatik** topadi. `185.214.135.9` endi core serveri; unga qaragan
boshqa loyiha domeni kutilgan IP ga mos kelmasligi uchun baribir AL-062 (`mismatch`) beradi.

### 11.4.3. Domen muddati

- `.com`, `.ai` va boshqa RDAP qo'llaydigan zonalar uchun avtomatik (RDAP, kuniga 1 marta).
- `.uz` uchun RDAP har doim mavjud emas — muddat **qo'lda kiritiladi** (FR-DNS-006), tizim
  eslatadi.
- Chegaralar: 60 / 30 / 14 / 7 kun (AL-066: ≤ 30 kun `warning`, AL-067: ≤ 7 kun `critical`).

### 11.4.4. Kesib o'tish (cut-over) yordamchisi

Domen bir serverdan boshqasiga ko'chirilayotganda (2026-10 da ko'p marta bajarilgan jarayon)
Nazoratchi quyidagi ishni bajaradi:

**Oldindan tekshiruv (DNS o'zgartirilishidan oldin):**
1. Operator: "domen X ni IP Y ga ko'chiraman".
2. Nazoratchi `prober` orqali **to'g'ridan-to'g'ri Y IP ga**, `Host: X` va `SNI: X` bilan
   HTTPS so'rov yuboradi (`curl --resolve X:443:Y` ning ekvivalenti).
3. Natija: HTTP status, sertifikat (muddati, hostname mosligi), javob vaqti.
4. Hammasi yaxshi bo'lsa — "tayyor, DNS ni o'zgartirishingiz mumkin"; aks holda sabab ("sertifikat
   yo'q", "502", ...) ko'rsatiladi. Bu aynan ko'chirish jarayonida qo'lda qilingan
   `curl --resolve` tekshiruvini avtomatlashtiradi.

**Kuzatish (DNS o'zgartirilgandan keyin):**
1. Tarqalish rejimi yoqiladi (FR-DNS-005): har 1 daqiqada barcha resolverlar so'raladi.
2. Panelda real vaqtda: qaysi resolver yangi IP ga o'tdi, qaysisi hali eski.
3. Hammasi o'tganda Telegram'ga "domen X yangi serverga to'liq o'tdi" xabari va avtomatik
   HTTP + TLS tekshiruv natijasi.
4. 2 soat o'tib ham ba'zi resolverlar eski bo'lsa — maslahat: "Google DNS keshini tozalash:
   dns.google/cache", TTL qiymati.

Bu funksiya talab sifatida FR-DNS-009 (4-bo'lim).

## 11.5. Konteynerlar (Docker)

### 11.5.1. Qaysi konteyner "kutilgan"

Nazoratchi konteyner o'chib qolganini ("kutilgan, lekin yo'q") qanday biladi — qo'lda ro'yxat
yuritmasdan?

1. Agent har 30 soniyada barcha konteynerlarni (`all=1`) ko'radi.
2. Konteyner **kutilgan** deb belgilanadi, agar: (a) kamida 1 soat uzluksiz `running` bo'lgan **va**
   (b) `RestartPolicy` `no` dan farqli (`always`/`unless-stopped`/`on-failure`).
3. Kutilgan konteyner yo'qolsa yoki `exited` bo'lsa → AL-035 (`high`), 90 soniyadan keyin.
   *(S5)* "Kutilgan" belgisi agent xotirasida (`docker_container_expected`), core'da emas; agent qayta ishga tushsa 1 soat qaytadan kutiladi. Ro'yxatdan butunlay yo'qolgan konteyner 10 daqiqa alert beradi, keyin unutiladi: ataylab olib tashlash uchun alohida amal kerak emas (F3 da paneldagi tugma bilan almashadi).
4. **Ataylab olib tashlash:** operator panelda "kutilgan ro'yxatdan chiqarish" tugmasini bosadi
   yoki `appctl down <loyiha>` natijasida loyiha uchun avtomatik maintenance (F3). Shu holda alert
   yo'q.
5. Compose loyihada konteyner nomi (`nazar-web-1`) o'zgarmaydi; yangi image bilan qayta
   yaratilganda (`--build`) 1 daqiqagacha yo'q bo'lishi normal — shuning uchun 90 s `for`.

### 11.5.2. Crash loop

- Mezon: 10 daqiqada `docker_container_restarts_total` ≥ 3 ga oshdi (AL-036).
- Xabarda: konteyner, loyiha, oxirgi `exit code`, `OOMKilled` belgisi, runbook RB-020
  (`docker logs --tail 100 <konteyner>`).

### 11.5.3. Resurslar

| Mezon | Alert |
|---|---|
| RAM ≥ 90% limitdan 10 daqiqa (limit belgilangan bo'lsa) | AL-039 (`warning`) |
| `OOMKilled = true` | AL-038 (`high`) |
| Konteyner CPU ≥ 95% (bir yadro) 30 daqiqa | AL-040 (`info`) |
| Log fayli > 100 MB yoki log limiti yo'q | AL-041 (`warning`) — eski konteynerlarga `daemon.json` limiti qo'llanmaganini topadi |

### 11.5.4. Noma'lum konteynerlar

Reyestrdagi hech bir loyihaga bog'lanmagan konteynerlar "noma'lum" ro'yxatida; AL-042
(`info`): "Reyestrda yo'q konteyner ishlayapti" — yangi ko'tarilgan loyiha reyestrga qo'shilmagani
yoki ruxsatsiz konteyner (xavfsizlik) belgisi.

## 11.6. systemd servislari va cron

| Mezon | Alert |
|---|---|
| Sozlamadagi unit `failed` yoki kutilmagan `inactive` (90 s) | AL-043 (`high`) |
| `NRestarts` 10 daqiqada ≥ 3 | AL-044 (`high`) |
| `systemctl --failed` soni > 0 (1 soat) | AL-045 (`warning`) |
| `nginx -t` xato | AL-046 (`high`) |
| Heartbeat kutilgan oraliqda kelmadi | AL-047 (`high`) |
| Heartbeat `status=fail` | AL-048 (`high`) |

Boshlang'ich kuzatiladigan unit lar (S-01): `nginx`, `docker`, `cron`, `ssh`, `avlo-contact`
(`fail2ban` o'rnatilgach qo'shiladi). S-02: `nginx`, `docker`, `ssh`, `fail2ban`.

Boshlang'ich cron heartbeat'lar:

| Nom | Server | Kutilgan oraliq | Grace |
|---|---|---|---|
| `appctl-backup` | S-01 | 24 soat | 2 soat |
| `certbot-renew` | S-01 | 24 soat (certbot timer: kuniga 2 marta) | 12 soat |
| `asadbekashurov-certbot` | S-02 | 24 soat | 3 soat |
| `nazoratchi-self-backup` | S-00 | 24 soat | 2 soat |

## 11.7. Server darajasidagi ichki-tashqi mosligi

Quyidagi kombinatsiyalar diagnostika uchun alohida ko'rsatiladi (incident xulosasida):

| HTTP tashqaridan | Konteyner/servis ichkaridan | Taxminiy sabab | Birinchi qadam |
|---|---|---|---|
| ❌ | ✅ (hammasi ishlayapti) | nginx/DNS/firewall/sertifikat | `nginx -t`, DNS holati, `ufw status` |
| ❌ | ❌ (konteyner yo'q) | Ilova yiqilgan | `docker ps -a`, `docker logs` |
| ✅ | ❌ (worker yo'q) | Fon vazifalari to'xtagan (Celery worker/beat) | `appctl ps <loyiha>` |
| ❌ | ❌ + host jim | Server o'lgan | RB-001 |
| ✅ | ✅ | Hammasi joyida | — |

## 11.8. Qabul sinovlari (servis monitoringi)

| № | Sinov | Kutilgan natija |
|---|---|---|
| T-SVC-01 | Nginx'ni to'xtatish | 90 s ichida `http_down`, ichki servislar sog'lom ekani ko'rsatiladi |
| T-SVC-02 | Sinov konteynerini doimiy xato bilan ishga tushirish | AL-036 crash loop |
| T-SVC-03 | `systemctl stop avlo-contact` | AL-043 90 s ichida |
| T-SVC-04 | Sinov sertifikati (3 kunlik) | AL-059 `critical` |
| T-SVC-05 | A yozuvini boshqa IP ga o'zgartirish (sinov domen) | AL-062/AL-063 10 daqiqadan keyin |
| T-SVC-06 | Cut-over oldindan tekshiruv: sertifikati yo'q serverga | "sertifikat yo'q" aniq sababi bilan rad |
| T-SVC-07 | Xost reboot qilish | `reboot aniqlandi` voqeasi, `Server o'chdi` bo'lmasa — qisqa uzilish alerti yo'q (120 s dan oz) |
| T-SVC-08 | Yopiq bo'lishi kerak port (5432) ni ochish | AL-030 (`high`) |
| T-SVC-09 | `docker compose up -d --build` paytida konteyner 40 s yo'qolishi | Alert **yo'q** (90 s `for`) |
