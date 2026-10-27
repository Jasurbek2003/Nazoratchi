# 12. Alert (ogohlantirish) tizimi

## 12.1. Tamoyillar

Yomon alert tizimi monitoringning o'zidan ham zararliroq: soxta xabarlar odamni charchatadi
va u haqiqiy xabarni ham e'tiborsiz qoldiradi. Shuning uchun quyidagi tamoyillar qat'iy:

1. **Har alert harakat talab qilishi kerak.** "Qiziq, lekin hech narsa qilmaydigan" ma'lumot
   alert emas — u panelda yoki haftalik hisobotda ko'rinadi (`info`).
2. **Alert simptomni emas, ta'sirni ko'rsatishi kerak.** Foydalanuvchiga ta'sir qiladigan holat
   (sayt ochilmayapti) yuqori ahamiyat; sababchi holat (CPU 92%) pastroq.
3. **Bir muammo — bitta xabar.** Server o'lsa, 40 ta alert emas, bitta incident (suppression).
4. **Xabar o'zi yetarli bo'lishi kerak:** nima, qayerda, qancha, qachondan, nima qilish kerak.
5. **Chegaralar sinab tanlanadi.** Standart qiymatlar boshlang'ich; 4 haftalik kuzatuvdan
   keyin sozlanadi (12.11).
6. **Tiklanish ham xabar qilinadi,** shunda odam "hal bo'ldimi?" deb tekshirib o'tirmaydi.
7. **Jimlik — signal.** Ma'lumotning yo'qligi (heartbeat, cron) ham alert.

## 12.2. Ahamiyat darajalari

| Daraja | Ma'nosi | Misol | Kutilgan reaksiya | Belgi |
|---|---|---|---|---|
| `critical` | Xizmat to'xtagan yoki darhol to'xtash xavfi, ma'lumot yo'qolishi xavfi | Server o'chdi, sayt ishlamayapti, disk 95%, sertifikat 3 kun, zaxira buzuq | **Zudlik bilan** (kechasi ham) | 🔴 |
| `high` | Jiddiy muammo; tez orada kritikka aylanishi mumkin yoki qisman ta'sir | Konteyner o'chdi, zaxira kechikdi, DNS mos emas | Bir necha soat ichida (ish vaqtida darrov) | 🟠 |
| `warning` | Diqqat talab qiladigan, lekin shoshilinch emas | CPU 90%, disk 80%, sertifikat 21 kun | Bugun-ertaga | 🟡 |
| `info` | Ma'lumot | Reboot kerak, agent eskirgan | Hisobotda ko'rib chiqiladi | 🔵 |

## 12.3. Qoida sxemasi

Qoida `alert_rules.condition` (JSONB) maydonida saqlanadi. Beshta shart turi:

### 12.3.1. `threshold` — chegara

```json
{
  "type": "threshold",
  "metric": "cpu_busy_percent",
  "labels": {},
  "op": ">",
  "value": 90,
  "aggregate": "avg",
  "window_s": 60
}
```

`aggregate`: `avg|min|max|last` — `window_s` oralig'ida; `for_seconds` shart shu holda uzluksiz
bajarilishi kerakligini bildiradi (qoida darajasida).

### 12.3.2. `absent` — ma'lumot yo'qligi

```json
{"type": "absent", "metric": "agent_up", "max_age_s": 120}
```

Berilgan qamrovdagi obyekt uchun metrikaning oxirgi namunasi `max_age_s` dan eski bo'lsa rost.

### 12.3.3. `rate` — o'zgarish tezligi

```json
{"type": "rate", "metric": "docker_container_restarts_total", "increase": 3, "window_s": 600}
```

`window_s` ichida qiymat `increase` dan ko'proqqa oshgan bo'lsa rost (counter qayta
boshlanishi hisobga olinadi).

### 12.3.4. `forecast` — bashorat

```json
{
  "type": "forecast",
  "metric": "fs_used_bytes",
  "labels": {"mount": "/"},
  "limit_metric": "fs_total_bytes",
  "horizon_s": 604800,
  "fit_window_s": 21600,
  "min_r2": 0.5,
  "min_used_percent": 50
}
```

Chiziqli regressiya (6.7.4) bo'yicha `horizon_s` ichida limitga yetsa rost. `min_r2` dan past
bo'lsa yoki bandlik `min_used_percent` dan kam bo'lsa — hisoblanmaydi (soxta bashorat oldini olish).

### 12.3.5. `state` — holat

```json
{"type": "state", "source": "probe", "field": "state", "equals": "down"}
```

`source`: `probe` (tekshiruv holati), `backup` (zaxira holati: `status`, `age_h`), `cert`
(`days_left`), `dns` (`status`), `heartbeat`. Boshqa manbalar uchun maxsus maydonlar 18.3-bo'limda.

Amalga oshirilgan manbalar (S3):

| `source` | `field` | `equals` | Ma'nosi |
|---|---|---|---|
| `reachability` | `tcp22` | `"up"` / `"down"` | Serverning `public_ipv4` ga TCP:22 ulanish (3 s, natija 20 s keshlanadi). Loopback va link-local manzillar tekshirilmaydi. Bu to'liq prober (S4/S5) kelguncha AL-001/AL-002 uchun minimal tashqi tekshiruv. IP kiritilmagan bo'lsa natija "noma'lum" |
| `heartbeat_job` | `overdue` | `true` | `now − last_beat_at > expected_every_s + grace_s` (hali bir marta ham xabar bermagan bo'lsa — noma'lum) |
| `heartbeat_job` | `failed` | `true` | Oxirgi heartbeat `status=fail` |
| `channel` | `failing` | `true` | Kanalga oxirgi 3 yuborish ketma-ket `failed` |
| `fleet` | `mass_silent` | `true` | Hostlarning ≥ 50% (kamida 2 ta) 120 s dan beri jim (AL-008) |
| `probe` | `state` | `"down"` / `"up"` | Faol tekshiruv holati (S4). Ixtiyoriy `primary: true/false` filtri (`config.primary`). `unknown`/`paused` holat — noma'lum. Ko'chirilmagan (`moved=false`) va arxivlangan loyiha tekshiruvlari hisoblanmaydi. Incident qamrovi — `project:<id>` |
| `prober` | `stalled` | `true` | Yoqilgan tekshiruvlar bor, lekin hech biri 180 s da bajarilmagan (AL-085) |

**"Ma'lumot yo'q" (uch qiymatli mantiq).** Shart hisoblanayotgan metrika yangi bo'lmasa (`last` uchun
`max(window_s, 120)` s dan eski) yoki hisoblash uchun nuqta yetmasa, natija `rost`/`yolg'on` emas, *noma'lum*.
Holat mashinasi noma'lumda `FIRING`/`RESOLVING` ni o'zgartirmaydi (6.7.1): agent jim bo'lganda CPU alerti
soxta "tiklandi" bo'lib qolmaydi; jimlikni AL-001/AL-002 ushlaydi. Birlashtirishda: `and` da bitta `yolg'on`
yetarli (qolganlari hisoblanmaydi: qimmat TCP tekshiruvi faqat agent jim bo'lganda bajariladi), `or` da bitta `rost`.

**Obyektlar (fan-out).** `threshold`, `rate`, `forecast` har mos seriya uchun alohida obyekt beradi (host × mount),
`absent`, `reachability` va birlashtirishlar — har host uchun bitta, `heartbeat_job` — har job, `channel` — har kanal.
Qoida `scope.tags`/`scope.ids` bilan serverlarga cheklanadi.

### 12.3.6. Birlashtirish

`and` / `or` / `not` (chuqurligi ≤ 3; operandlar `of` ro'yxatida, `not` uchun aynan bitta, `and`/`or` uchun 2..5; faqat
host darajasidagi shartlar: `threshold`, `absent`, `rate`, `forecast`, `reachability`):

```json
{"type": "and", "of": [
  {"type": "absent", "metric": "agent_up", "max_age_s": 120},
  {"type": "state", "source": "probe", "field": "tcp22", "equals": "down"}
]}
```

## 12.4. Yetkazish siyosati

### 12.4.1. Kanal va vaqt

| Ahamiyat | Telegram | Email | Sokin soatlarda (23:00–07:00) | Takroriy eslatma |
|---|---|---|---|---|
| `critical` | darhol | darhol | **darhol** | 30 daqiqada bir, ack bo'lguncha (6 marta, keyin 2 soatda bir) |
| `high` | darhol | 07:00 yig'ma | 07:00 da | 2 soatda bir, ack bo'lguncha (3 marta) |
| `warning` | darhol (kunduzi), ertalabki yig'ma (kechasi) | kunlik hisobot | 07:00 yig'ma | Bir marta; 24 soatdan keyin hali ochiq bo'lsa qayta |
| `info` | faqat kunlik hisobotda | haftalik | — | — |

Qiymatlar sozlamada kanal darajasida o'zgartiriladi (`min_severity`, `quiet_hours`).

### 12.4.2. Eskalatsiya (F3)

`critical` 15 daqiqa qabul qilinmasa — ikkinchi kontakt/kanalga yuboriladi; 45 daqiqada ham
qabul qilinmasa — "ikkala kontaktga ham" xabar.

### 12.4.3. Takroriy eslatma to'xtashi

- Incident `ack` qilinsa — eslatmalar to'xtaydi (lekin ahamiyat oshsa, qayta xabar).
- `silence` / `maintenance` — to'xtaydi.
- Incident yopilsa — "tiklandi".

## 12.5. Bostirish, guruhlash, titrashdan himoya

### 12.5.1. Bog'liqlik bo'yicha bostirish (suppression)

6.7.3 dagi qoidalarga qo'shimcha: bostirilgan alert "yo'qolmaydi" — incident ichida "ta'sirlangan"
ro'yxatida ko'rinadi va asosiy sabab hal bo'lganda, shart hamon rost bo'lsa, ularning o'zi
yangidan hisoblanadi (masalan, server qaytdi, lekin konteyner hamon ishlamayapti — yangi
xabar).

### 12.5.1a. Ahamiyat bo'yicha bostirish (amalga oshirilgan)

Bir obyekt va bir metrikada bir nechta chegara qoidasi bo'lsa (AL-019/020/021), ularning eng yuqori ahamiyatlisi
`FIRING` bo'lganda pastroqlari bostiriladi (80% → 90% → 95% da uchta xabar o'rniga bittasi, eng og'iri).
Yuqorisi yopilib pastrog'i hamon rost bo'lsa, pastrog'i xabar beradi. Bostirish sabablari: `pause`, `maintenance`,
`silence`, `host_down` (AL-001 dan keyin shu hostning boshqa alertlari), `mass_silence` (AL-008 dan keyin AL-001/002),
`superseded`. Bostirilgan alert incident'da qoladi.

> **S3 holati.** Guruhlash (12.5.2), titrash/beqarorlik va gisterezis (12.5.3), eskalatsiya (12.4.2), sokin soatlar va
> email hozircha yo'q (F2/F3). Tugma bilan `ack` (Telegram) S4 da; `ack` hozir API orqali.

### 12.5.2. Guruhlash

60 soniyalik oyna ichida bir qamrov (`scope_key`) bo'yicha 3 va undan ko'p alert bitta xabarga
birlashadi: sarlavha — eng og'ir alert, tanasida qisqa ro'yxat (maks. 10 ta, qolgani "+N ta").

### 12.5.3. Titrash (flapping)

- 1 soat ichida 5 martadan ko'p `FIRING ↔ OK` o'tishi — "beqaror" belgisi.
- Beqaror alert uchun har o'tishda xabar yuborilmaydi; o'rniga bitta "beqaror: N marta o'zgardi"
  xabari va 30 daqiqalik tinch davr kutiladi.
- Gisterezis: ko'p qoidada yoqish chegarasi va o'chirish chegarasi farqli (masalan, disk:
  yoqish 80%, o'chirish 78%).

### 12.5.4. Massaviy jimlik

Agar ≥ 2 host va ≥ 50% hostlar 2 daqiqa ichida jim bo'lsa — AL-008 (core tarmog'i yoki core
muammosi gumoni) bitta incident; alohida AL-001/AL-002 lar bostiriladi, chunki ularning
sababi Nazoratchi tomonida bo'lishi ehtimoli yuqori.

## 12.6. Silence va maintenance

### 12.6.1. Silence

- Moslash (matchers): `server`, `project`, `rule`, `severity`, `domain`, `container`, `tag`
  bo'yicha (`=`, `!=`, `=~` regex).
- Muddat: 15 daqiqa – 30 kun. Sabab majburiy.
- **Silence alertni o'chirmaydi:** holat hisoblanaveradi, incident ochiladi (`suppressed=true`),
  faqat bildirishnoma yuborilmaydi. Silence tugagach ham shart rost bo'lsa — xabar yuboriladi.
- Silence tugashiga 15 daqiqa qolganda `info` eslatma (agar o'sha qamrovda ochiq incident bo'lsa).

### 12.6.2. Maintenance oynasi

- Qamrov: server(lar) yoki loyiha(lar); boshlanish/tugash vaqti.
- Oyna ichida: bildirishnoma yuborilmaydi; uptime hisobida "rejalashtirilgan to'xtash"
  sifatida alohida; boshqa incidentlar kabi yig'iladi.
- Oyna tugagach: ochiq `firing` alertlar yuboriladi ("texnik ish tugadi, hali hal bo'lmagan: ...").
- **Reboot oldidan nazorat ro'yxati** (L-4 saboq): oyna yaratilganda panel eslatadi:
  "Snapshot olindimi? Zaxira yangimi? Offsite'dagi nusxa tekshirildimi?" (12.9-bo'lim).

### 12.6.3. Ustuvorlik

`pause` (server) > `maintenance` > `silence` > oddiy yuborish. Hammasi audit jurnalida.

## 12.7. Qoidalar katalogi (AL-001 … AL-089)

Ustunlar: **ID**; **Nom**; **Qamrov**; **Shart**; **`for`** — shart shuncha vaqt uzluksiz rost
bo'lishi; **Ahamiyat**; **Faza**; **Runbook**.
Metrika nomlari 7-bo'limdagi katalogga mos. `*` — chegara sozlanadi.

### 12.7.1. Server va agent (A)

| ID | Nom | Qamrov | Shart | `for` | Ahamiyat | Faza | RB |
|---|---|---|---|---|---|---|---|
| AL-001 | Server o'chdi | host | Heartbeat ≥ 120 s yo'q **va** TCP:22/ICMP tashqi tekshiruv muvaffaqiyatsiz | 0 | critical | F1 | RB-001 |
| AL-002 | Agent javob bermayapti | host | Heartbeat ≥ 120 s yo'q, lekin TCP:22 javob beradi | 3 daq | high | F1 | RB-002 |
| AL-003 | Kutilmagan reboot | host | `boot_time_seconds` o'zgardi va maintenance oynasi yo'q | 0 | high | F1 | RB-003 |
| AL-004 | Agent eskirgan | host | Agent versiyasi core'dagi so'nggi versiyadan ≥ 2 minor orqada | 1 soat | info | F2 | RB-043 |
| AL-005 | Agent navbati o'smoqda | host | `agent_queue_files` > 10 | 10 daq | warning | F2 | RB-002 |
| AL-006 | Agent kollektor xatolari | host | `agent_collector_errors` o'sish tezligi > 0 | 15 daq | warning | F2 | RB-002 |
| AL-007 | Soat siljishi | host | `abs(agent_clock_skew_seconds)` > 5 | 10 daq | warning | F2 | RB-016 |
| AL-008 | Ko'p host jim (core tarmog'i) | global | ≥ 50% hostlar (kamida 2) heartbeat'siz | 2 daq | critical | F1 | RB-012 |

### 12.7.2. CPU, RAM (B)

| ID | Nom | Qamrov | Shart | `for` | Ahamiyat | Faza | RB |
|---|---|---|---|---|---|---|---|
| AL-009 | CPU yuqori | host | `cpu_busy_percent` > 90* | 10 daq | warning | F1 | RB-009 |
| AL-010 | CPU to'yingan | host | `cpu_busy_percent` > 97* | 15 daq | high | F2 | RB-009 |
| AL-011 | Yuklama yuqori | host | `load_per_core_1m` > 2* | 15 daq | warning | F2 | RB-009 |
| AL-012 | Disk kutish (iowait) | host | `cpu_usage_percent{mode=iowait}` > 30* | 10 daq | warning | F2 | RB-011 |
| AL-013 | CPU steal yuqori | host | `cpu_usage_percent{mode=steal}` > 15* (provayder resursi yetmayapti) | 15 daq | warning | F2 | RB-009 |
| AL-014 | RAM yuqori | host | `mem_used_percent` > 90* | 10 daq | warning | F1 | RB-010 |
| AL-015 | RAM kritik | host | `mem_used_percent` > 96* | 5 daq | critical | F1 | RB-010 |
| AL-016 | Swap faol ishlatilmoqda | host | `swap_used_percent` > 50 **va** `swap_in_pages_per_sec` > 100 | 10 daq | warning | F2 | RB-010 |
| AL-017 | Yadro OOM o'ldirdi | host | `oom_kill_total` oshdi (rate, 10 daq) | 0 | high | F2 | RB-010 |
| AL-018 | Zombi jarayonlar ko'p | host | `procs_zombie` > 20 | 30 daq | info | F3 | RB-009 |

### 12.7.3. Disk va fayl tizimi (C)

| ID | Nom | Qamrov | Shart | `for` | Ahamiyat | Faza | RB |
|---|---|---|---|---|---|---|---|
| AL-019 | Disk 80% | host × mount | `fs_used_percent` > 80* | 5 daq | warning | F1 | RB-004 |
| AL-020 | Disk 90% | host × mount | `fs_used_percent` > 90* | 5 daq | high | F1 | RB-004 |
| AL-021 | Disk 95% | host × mount | `fs_used_percent` > 95* | 2 daq | critical | F1 | RB-004 |
| AL-022 | Disk 7 kunda to'ladi (bashorat) | host × mount | Bashorat < 7 kun (R² ≥ 0.5, band ≥ 50%) | 30 daq | warning | F1 | RB-004 |
| AL-023 | Disk 24 soatda to'ladi (bashorat) | host × mount | Bashorat < 24 soat | 15 daq | critical | F1 | RB-004 |
| AL-024 | Inode yuqori | host × mount | `fs_inodes_used_percent` > 85* | 10 daq | warning | F2 | RB-004 |
| AL-025 | Fayl tizimi faqat o'qish | host × mount | `fs_readonly = 1` (real FS) | 1 daq | critical | F1 | RB-005 |
| AL-026 | Disk I/O to'yingan | host × device | `disk_io_util_percent` > 90* | 15 daq | warning | F2 | RB-011 |
| AL-027 | Disk kechikishi yuqori | host × device | `disk_await_ms` > 100* | 10 daq | warning | F2 | RB-011 |
| AL-028 | Docker tozalab bo'ladigan hajm katta | host | `docker_reclaimable_bytes` > 20 GB yoki > 25% disk | 1 soat | info | F3 | RB-004 |

### 12.7.4. Tarmoq, OS, xavfsizlik (D)

| ID | Nom | Qamrov | Shart | `for` | Ahamiyat | Faza | RB |
|---|---|---|---|---|---|---|---|
| AL-029 | Tarmoq xatolari | host × iface | `net_rx_errors_per_sec + net_tx_drops_per_sec` > 10* | 10 daq | warning | F2 | RB-013 |
| AL-030 | Kutilmagan ochiq port | host | TCP tekshiruvi `expect: closed` portlardan biri ochiq **yoki** `facts.listen_ports` kutilgan ro'yxatdan tashqari | 2 daq | high | F2 | RB-027 |
| AL-031 | SSH hujumi (bruteforce) | host | `ssh_failed_logins_1h` > 200* | 0 | warning | F3 | RB-014 |
| AL-032 | Reboot uzoq kutilmoqda | host | `reboot_required_age_seconds` > 14 kun | 0 | warning | F2 | RB-015 |
| AL-033 | Yangi kernel kutilmoqda | host | `kernel_reboot_pending = 1` | 24 soat | info | F2 | RB-015 |
| AL-034 | Xavfsizlik yangilanishlari | host | `apt_security_upgradable_total` > 0 | 7 kun | warning | F3 | RB-015 |

### 12.7.5. Docker (E)

| ID | Nom | Qamrov | Shart | `for` | Ahamiyat | Faza | RB |
|---|---|---|---|---|---|---|---|
| AL-035 | Konteyner ishlamayapti | container | Kutilgan konteyner `running` emas (11.5.1) | 90 s | high | F1 | RB-020 |
| AL-036 | Konteyner crash loop | container | `docker_container_restarts_total` 10 daq ≥ 3 ga oshdi | 0 | high | F1 | RB-020 |
| AL-037 | Konteyner sog'lom emas | container | `docker_container_health = 2` | 2 daq | high | F2 | RB-020 |
| AL-038 | Konteyner OOM bilan o'ldi | container | `docker_container_oom_killed = 1` | 0 | high | F2 | RB-021 |
| AL-039 | Konteyner xotirasi limitga yaqin | container | `docker_container_mem_percent` > 90* (limit bor bo'lsa) | 10 daq | warning | F2 | RB-021 |
| AL-040 | Konteyner CPU yuqori | container | `docker_container_cpu_percent` > 95* | 30 daq | info | F3 | RB-009 |
| AL-041 | Konteyner logi katta / limitsiz | container | `docker_container_log_bytes` > 100 MB* | 1 soat | warning | F2 | RB-021 |
| AL-042 | Reyestrda yo'q konteyner | container | Hech bir loyihaga bog'lanmagan konteyner ishlayapti | 1 soat | info | F2 | RB-020 |

### 12.7.6. systemd va cron (F)

| ID | Nom | Qamrov | Shart | `for` | Ahamiyat | Faza | RB |
|---|---|---|---|---|---|---|---|
| AL-043 | Servis ishlamayapti | unit | `systemd_unit_active = 0` yoki `systemd_unit_failed = 1` | 90 s | high | F1 | RB-022 |
| AL-044 | Servis qayta ishga tushish halqasi | unit | `systemd_unit_restarts_total` 10 daq ≥ 3 ga oshdi | 0 | high | F2 | RB-022 |
| AL-045 | Muvaffaqiyatsiz unitlar bor | host | `systemd_failed_units_total` > 0 | 1 soat | warning | F2 | RB-022 |
| AL-046 | nginx konfigi yaroqsiz | host | `nginx_config_ok = 0` | 5 daq | high | F3 | RB-023 |
| AL-047 | Heartbeat kelmadi | job | `now − last_beat_at` > `expected_every_s + grace_s` | 0 | high | F1 | RB-024 |
| AL-048 | Heartbeat "xato" dedi | job | Oxirgi heartbeat `status=fail` | 0 | high | F1 | RB-024 |

### 12.7.7. HTTP va TCP tekshiruvlari (G)

| ID | Nom | Qamrov | Shart | `for` | Ahamiyat | Faza | RB |
|---|---|---|---|---|---|---|---|
| AL-049 | Sayt ishlamayapti | probe (http) | Holat `down` (3 ketma-ket muvaffaqiyatsiz) | 0 | critical (teg `primary`) / high | F1 | RB-025 |
| AL-050 | Sayt sekin | probe (http) | `total_ms` > `latency_warn_ms` (3000*) | 5 daq | warning | F2 | RB-026 |
| AL-051 | Kalit so'z mos emas | probe (http) | Kalit so'z tekshiruvi 3 marta xato | 0 | high | F2 | RB-025 |
| AL-052 | TTFB yuqori | probe (http) | `ttfb_ms` > 2000* | 10 daq | warning | F3 | RB-026 |
| AL-053 | TCP port ishlamayapti | probe (tcp) | `expect: open` bo'lgan port 3 marta ulanmadi | 0 | high | F2 | RB-025 |
| AL-054 | Uptime past | probe | 30 kunlik uptime < 99.5%* | 1 soat | info | F3 | RB-025 |
| AL-055 | Tekshiruv bajarilmayapti | probe | `now − last_run_at` > 3 × interval | 0 | high | F2 | RB-040 |
| AL-056 | Tekshiruv titrayapti | probe | 1 soatda > 5 holat o'zgarishi | 0 | warning | F2 | RB-025 |

### 12.7.8. Sertifikat (H)

| ID | Nom | Qamrov | Shart | `for` | Ahamiyat | Faza | RB |
|---|---|---|---|---|---|---|---|
| AL-057 | Sertifikat 21 kunda tugaydi | domain | `days_left` ≤ 21* | 0 | warning | F1 | RB-006 |
| AL-058 | Sertifikat 7 kunda tugaydi | domain | `days_left` ≤ 7* | 0 | high | F1 | RB-006 |
| AL-059 | Sertifikat 3 kunda tugaydi / tugadi | domain | `days_left` ≤ 3* | 0 | critical | F1 | RB-006 |
| AL-060 | Sertifikat yaroqsiz | domain | Zanjir to'liq emas yoki hostname SAN da yo'q | 10 daq | high | F2 | RB-006 |
| AL-061 | Sertifikat yangilanmayapti | domain/host | Yangilash ketma-ket 2 marta xato; yoki agentdagi sertifikat yangi, tashqaridagi eski (nginx reload qilinmagan) | 0 | high | F2 | RB-006 |

### 12.7.9. DNS va domen (I)

| ID | Nom | Qamrov | Shart | `for` | Ahamiyat | Faza | RB |
|---|---|---|---|---|---|---|---|
| AL-062 | DNS kutilgan IP ga qaramaydi | domain | NS serveri kutilgan IP ni bermaydi (yoki NXDOMAIN) | 10 daq | high (NXDOMAIN: critical) | F1 | RB-007 |
| AL-063 | Domen yopilgan IP ga qaraydi | domain | A yozuvi `retired_ips` ro'yxatida | 10 daq | high | F1 | RB-007 |
| AL-064 | NS yozuvi o'zgardi | domain | NS to'plami o'zgardi | 0 | info | F3 | RB-007 |
| AL-065 | Resolverlar bir-biriga mos emas | domain | NS to'g'ri, lekin ≥ 1 ommaviy resolver boshqa javob beradi | 30 daq | warning | F2 | RB-007 |
| AL-066 | Domen muddati 30 kunda tugaydi | domain | `whois.expires_at − now` ≤ 30 kun | 0 | warning | F2 | RB-008 |
| AL-067 | Domen muddati 7 kunda tugaydi | domain | ≤ 7 kun | 0 | critical | F2 | RB-008 |

### 12.7.10. Zaxira (J)

| ID | Nom | Qamrov | Shart | `for` | Ahamiyat | Faza | RB |
|---|---|---|---|---|---|---|---|
| AL-068 | Zaxira kechikdi | project | Eng yangi muvaffaqiyatli zaxira yoshi > 26 soat* | 0 | high | F1 | RB-031 |
| AL-069 | Zaxira uzoq vaqt olinmadi | project | Yosh > 50 soat* | 0 | critical | F1 | RB-031 |
| AL-070 | Zaxira muvaffaqiyatsiz | project | Oxirgi `state.json.status = fail` | 0 | high | F1 | RB-031 |
| AL-071 | Zaxira shubhali: juda kichik | project | Hajm < median(7) × 0.5* | 0 | high | F1 | RB-032 |
| AL-072 | Zaxira shubhali: juda katta | project | Hajm > median(7) × 3* | 0 | info | F2 | RB-032 |
| AL-073 | Zaxira fayli buzuq | project | `backup_gz_ok = 0` | 0 | critical | F2 | RB-032 |
| AL-074 | Haftalik fayl zaxirasi yo'q | project | Haftalik fayl yoshi > 192 soat* | 0 | warning | F2 | RB-031 |
| AL-075 | Offsite zaxira sozlanmagan | host | `backup_offsite_configured = 0` | 0 | warning (doimiy) | F1 | RB-033 |
| AL-076 | Offsite eskirdi | project | Offsite'dagi eng yangi fayl orqada > 26 soat* | 0 | high | F2 | RB-033 |
| AL-077 | Offsite uzoq vaqt yangilanmadi | project | Orqada > 50 soat* | 0 | critical | F2 | RB-033 |
| AL-078 | Offsite nusxa mos emas | project | Nom/hajm mos kelmaydi 30 daqiqadan ortiq | 30 daq | warning | F2 | RB-033 |
| AL-079 | Zaxira bo'limida joy kam | host | `backup_root_free_bytes` < 15% yoki < 5 GB* | 10 daq | warning (< 5%: critical) | F2 | RB-004 |
| AL-080 | Offsite serverda joy kam | host (offsite) | Xuddi shu, offsite serverda | 10 daq | warning | F2 | RB-033 |
| AL-081 | Restore drill muddati yaqin | project | Oxirgi muvaffaqiyatli drill > `drill_every_days − 14` kun | 0 | info | F2 | RB-034 |
| AL-082 | Restore drill muddati o'tdi | project | Oxirgi muvaffaqiyatli drill > `drill_every_days` kun (yoki hech qachon) | 0 | warning | F2 | RB-034 |
| AL-083 | Restore drill muvaffaqiyatsiz | project | Oxirgi drill natijasi `failed` | 0 | high | F2 | RB-034 |

### 12.7.11. Nazoratchi'ning o'zi (K)

| ID | Nom | Qamrov | Shart | `for` | Ahamiyat | Faza | RB |
|---|---|---|---|---|---|---|---|
| AL-084 | Alert dvigateli qotdi | system | `evaluator_heartbeat` > 60 s eskirgan | 0 | critical | F1 | RB-040 |
| AL-085 | Prober qotdi | system | Hech bir tekshiruv 3 daqiqada bajarilmadi | 0 | high | F1 | RB-040 |
| AL-086 | Bildirishnoma kanali ishlamayapti | channel | Kanalga yuborish ketma-ket 3 marta xato | 0 | high | F1 | RB-041 |
| AL-087 | Nazoratchi bazasi katta | system | Baza hajmi > 80% byudjetdan (NFR-CAP-002) | 1 soat | warning | F2 | RB-042 |
| AL-088 | Qabul qilishda xatolar ko'p | system | Ingest xatolari > 5% (10 daq) | 10 daq | warning | F2 | RB-042 |
| AL-089 | Saqlash vazifasi bajarilmadi | system | Retention/agregat vazifasi 26 soatdan beri muvaffaqiyatsiz | 0 | warning | F2 | RB-042 |

> **Eslatma (AL-086).** Telegram kanali ishlamayotgan bo'lsa, bu alert o'sha kanalga yuborila
> olmaydi. Shuning uchun u har doim ikkinchi kanal (email) va panel orqali ko'rsatiladi,
> tashqi watchdog ham uni qayd etadi (FR-NTF-004).

### 12.7.12. Faza bo'yicha xulosa

| Faza | Alertlar soni |
|---|---|
| F1 (MVP) | 32 ta (muhim: server o'chdi, disk, RAM, konteyner, sayt, sertifikat, DNS, zaxira, heartbeat, o'zini kuzatish) |
| F2 | 48 ta |
| F3 | 9 ta |
| **Jami** | **89 ta** |

Ahamiyat bo'yicha (asosiy daraja): `critical` 13, `high` 30, `warning` 36, `info` 10.

> **S3 da yoqilgan standart qoidalar (16 ta):** AL-001, 002, 003, 008, 009, 014, 015, 019, 020, 021, 022, 023, 025,
> 047, 048, 086.
> **S4 da qo'shilgan (3 ta):** AL-049 (asosiy sayt, `critical`), AL-049H (asosiy bo'lmagan, `high`: katalogdagi "critical (teg `primary`) / high" ikki qoidaga bo'lingan), AL-085 (prober qotdi). Tekshiruv alertlari loyihaning HAMMA serveri pauzada/texnik ishda yoki o'chgan bo'lsa bostiriladi (6.7.3). Qolgan F1 qoidalari (docker, tekshiruvlar, sertifikat, DNS, zaxira) ularning ma'lumoti paydo bo'lgan
> sprintda qo'shiladi. AL-084/085 tashqi kuzatuvchi (watchdog, S7) bilan. Standart qoidalar bazada yo'q bo'lsagina
> yaratiladi: foydalanuvchi o'zgartirgan chegaraga tegilmaydi.

## 12.8. Qoidani sozlash

- Har qoida uchun: yoqish/o'chirish, chegara, `for`, ahamiyat, qamrov (teg/ID), kanallar.
- **Qoida testi** (`POST /alert-rules/{id}/test`): joriy ma'lumotda quruq hisoblash va "hozir
  firing bo'ladigan obyektlar" ro'yxatini ko'rsatadi; alert yuborilmaydi. Yangi chegarani
  qo'llashdan oldin shu bilan tekshiriladi.
- Qoida tarixi: har o'zgarish audit jurnalida (kim, eski/yangi qiymat).
- O'rnatilgan qoidalar (`built_in`) o'chirilmaydi, faqat o'chirib qo'yiladi; yangi
  versiyada standart qiymatlar yangilanganda, foydalanuvchi o'zgartirgan qiymatlar saqlanadi.

## 12.9. Xabar shablonlari (Telegram, o'zbek tilida)

### 12.9.0. Yuborish va qayta urinish (FR-NTF-004)

Xabar avval `notifications` ga `queued` bo'lib yoziladi, `notifier` jarayoni yuboradi. Vaqtinchalik xatoda
(tarmoq, `5xx`, `429`) jami 5 urinish: 1-dan keyin 5 s, 2-dan 15 s, 3-dan 60 s, 4-dan 300 s kutiladi;
`429` da Telegram bergan `retry_after` ishlatiladi. Doimiy xatoda (`400`, `401`, `403`: noto'g'ri token yoki
chat, bot bloklangan) qayta urinilmaydi: darhol `failed`, sabab `channels.last_error` da (panelda ko'rinadi).
Telegram HTML rejimida yuboriladi, o'zgaruvchan matn (server nomi, log satri) ekranlanadi; sarlavha 150
belgigacha, butun xabar 1000 belgigacha (uzun bo'lsa o'rtadagi satrlar qisqartiriladi, runbook va havola qoladi).
Email zaxira kanali F2 da (FR-NTF-005); hozircha kanal ishlamasa faqat panelda ko'rinadi.

Umumiy tuzilma: **ahamiyat belgisi + sarlavha**, bo'sh qator, **qayerda**, **nima bo'ldi**
(qiymat va chegara), **qachondan**, **ta'sir**, **nima qilish kerak** (runbook), tugmalar.

### 12.9.1. Server o'chdi (AL-001)

```
🔴 Server o'chdi: main-2 (164.68.105.194)

Aloqa yo'q: 2 daqiqa (oxirgi marta 09:33 da ko'rilgan)
TCP:22 — javob yo'q, ICMP — javob yo'q

Ta'sirlangan loyihalar (6): Nazar, BiznesRadar, beyondlinks.uz, avlo.ai,
freighthubllc, wmg

Nima qilish kerak: RB-001 → provayder panelidan holatni tekshiring (VNC/Rescue)
Incident: https://nazoratchi.example.uz/incidents/0193...

[ Qabul qilaman ]  [ 1 soat jim ]  [ Panelda ochish ]
```

### 12.9.2. Disk to'lmoqda (AL-022)

```
🟡 Disk 7 kunda to'ladi: main-2 ( / )

Hozir: 78% (62.4 GB / 80 GB)
O'sish: +1.9 GB/kun → to'lishga ≈ 9.3 kun (7 kundan kam bashorat: oxirgi 24 soat bo'yicha 6.1 kun)

Eng katta: /var/lib/docker (41 GB), /opt/applications/backups (12 GB)

Nima qilish kerak: RB-004 → `docker system df`, eski image/log tozalash

[ Qabul qilaman ]  [ 24 soat jim ]  [ Panelda ochish ]
```

### 12.9.3. Zaxira kechikdi (AL-068)

```
🟠 Zaxira kechikdi: BiznesRadar

Oxirgi muvaffaqiyatli: 2 kun 3 soat oldin (2026-10-20 03:15 UTC)
Kutilgan: har 24 soatda (chegara 26 soat)
Oxirgi log (appctl-backup.log):
  [BiznesRadar] XATO: dump muvaffaqiyatsiz

Nima qilish kerak: RB-031 → `appctl backup BiznesRadar` ni qo'lda ishga tushiring

[ Qabul qilaman ]  [ Panelda ochish ]
```

### 12.9.4. Tiklandi

```
✅ Tiklandi: Server o'chdi — main-2

Davomiyligi: 12 daqiqa (09:33 – 09:45)
Sabab: (kiritilmagan)  ← panelda izoh qo'shing

[ Panelda ochish ]
```

### 12.9.5. Sertifikat (AL-058)

```
🟠 Sertifikat 7 kunda tugaydi: nazar.avlo.ai

Tugash: 2026-10-29 (qolgan: 7 kun)
Chiqaruvchi: Let's Encrypt (R11)
Server: main-2. Oxirgi yangilash urinishi: 2026-10-21 04:12 — muvaffaqiyatsiz

Nima qilish kerak: RB-006 → `certbot renew --dry-run`, `journalctl -u certbot`

[ Qabul qilaman ]  [ Panelda ochish ]
```

### 12.9.6. DNS (AL-063)

```
🟠 Domen yopilgan IP ga qaraydi: lutfanai.uz

Hozir: 34.173.220.247 (o'chirilgan GCP serveri)
Kutilgan: 164.68.105.194
DNS provayder: (reyestrda ko'rsatiladi)

Nima qilish kerak: RB-007 → DNS A yozuvini yangilang

[ Qabul qilaman ]  [ Panelda ochish ]
```

### 12.9.7. Yig'ma (guruhlangan) xabar

```
🔴 main-2: 7 ta muammo (1 incident)

• Server o'chdi (asosiy sabab)
• Sayt ishlamayapti: nazar.avlo.ai, biznesradar.uz, avlo.ai (+3)
• Konteyner ishlamayapti: 14 ta
• Zaxira holati noma'lum

[ Qabul qilaman ]  [ Panelda ochish ]
```

### 12.9.8. Texnik ish oldidan nazorat ro'yxati (maintenance yaratilganda)

```
🛠 Texnik ish rejalashtirildi: main-2, 22 okt 14:00–15:00

Reboot oldidan tekshiring:
 ☐ Snapshot olindi (Contabo panel)
 ☐ Oxirgi zaxira yangi (BiznesRadar 6 soat, Nazar 6 soat) — avto-tekshiruv ✅
 ☐ Offsite nusxa mos — ❌ OFFSITE sozlanmagan
 ☐ DNS TTL pasaytirildi (agar kesib o'tish bo'lsa)
```

(Avtomatik belgilanadigan bandlar Nazoratchi ma'lumotidan hisoblanadi; qo'lda bandlarni
operator belgilaydi.)

## 12.10. Davriy hisobotlar

### 12.10.1. Kunlik (08:00 Asia/Tashkent, Telegram)

```
📊 Kunlik xulosa — 22 oktyabr

Serverlar: 3/3 onlayn   Loyihalar: 9 ta (hammasi sog'lom)
Ochiq incident: 1 (🟡 disk 80%)
Zaxira: 8/8 yangi (eng eskisi 6 soat), offsite: ❌ sozlanmagan
Muddatlar: sertifikat ≥ 41 kun, domen ≥ 118 kun, drill muddati o'tgan: 6
Kecha: 2 incident (jami 14 daqiqa)
```

### 12.10.2. Haftalik (dushanba 09:00, email + Telegram qisqa)

Tarkibi: uptime (har loyiha, 7 kun), incidentlar jadvali (ahamiyat, davomiyligi, sabab),
MTTR, eng ko'p alert bergan qoidalar (shovqin nazorati), disk/RAM tendensiyalari
(7 kunlik o'zgarish), zaxira va drill holati, yaqin muddatlar (sertifikat, domen),
hal qilinmagan "doimiy" ogohlantirishlar (masalan, offsite yo'q).

## 12.11. Alert sifatini boshqarish

| Ko'rsatkich | Maqsad | Qanday o'lchanadi |
|---|---|---|
| Haftalik "qo'ng'iroq" (high+critical) alertlar soni | ≤ 10 (barqaror holatda) | Panel hisoboti |
| Soxta alertlar ulushi | ≤ 5% | Operator incidentni "soxta" deb belgilaydi (maxsus yopish sababi) |
| Aniqlanmay qolgan haqiqiy muammo | 0 (har post-mortemda tekshiriladi) | Incident tahlili |
| Ack vaqti (critical) | median ≤ 10 daqiqa | Incident hodisalaridan |

**Oylik ko'rib chiqish (30 daqiqa):** eng ko'p ishga tushgan 5 qoida → chegarasini
oshirish/`for` ni uzaytirish/o'chirish; soxta deb belgilangan incidentlarni tahlil qilish;
yangi post-mortemdan yangi qoida qo'shish.

**Post-mortem qoidasi:** har `critical` incidentdan keyin "Bu muammoni oldinroq aniqlay
olardikmi?" savoliga javob yoziladi va kerak bo'lsa yangi qoida (yoki chegara) qo'shiladi.

## 12.12. Alert tizimi testlari

| № | Sinov | Kutilgan natija |
|---|---|---|
| T-ALR-01 | Sun'iy "agent_up" to'xtatish (agentni stop) | 120 s dan keyin AL-002 yoki AL-001 (TCP:22 ga qarab) |
| T-ALR-02 | `for` davomiyligi: 4 daqiqa CPU 95% (chegara 10 daq) | Alert yo'q |
| T-ALR-03 | `for` davomiyligi: 11 daqiqa CPU 95% | AL-009 |
| T-ALR-04 | Bostirish: serverni o'chirish | Faqat bitta incident, ta'sirlanganlar ro'yxati bilan |
| T-ALR-05 | Titrash: 10 marta tez holat o'zgarishi | "Beqaror" xabari, ≤ 2 xabar |
| T-ALR-06 | Silence: 1 soatga | Xabar yo'q; incident `suppressed`; tugagach xabar |
| T-ALR-07 | Maintenance oynasi | Xabar yo'q; oyna tugagach hal bo'lmagan alertlar yuboriladi |
| T-ALR-08 | Ack tugmasi (Telegram) | Incident `acknowledged`, eslatmalar to'xtaydi |
| T-ALR-09 | Telegram'ni bloklash | Email zaxira kanal, AL-086 |
| T-ALR-10 | Evaluator qayta ishga tushishi | Ochiq incidentlar saqlanadi, takroriy "yangi alert" xabarlari yo'q |
| T-ALR-11 | Sokin soatlar | Kechasi `warning` kelmaydi; `critical` keladi |
| T-ALR-12 | Disk forecast: sun'iy o'sish | AL-022/AL-023 to'g'ri vaqtda |
| T-ALR-13 | Takroriy eslatma | `critical` 30 daqiqada bir (ack gacha) |
