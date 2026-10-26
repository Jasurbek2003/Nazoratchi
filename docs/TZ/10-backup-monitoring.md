# 10. Zaxira nusxalar (backup) monitoringi

## 10.1. Nima uchun alohida bo'lim

Zaxira — Nazoratchi'ning eng muhim qiymat beradigan qismi, chunki bu yerda xato **jim** bo'ladi:
zaxira ishlamayotgani faqat kerak bo'lgan kuni, tiklash paytida ma'lum bo'ladi. 2026-10 hodisasida
aynan shu xavf amalga oshishiga oz qoldi: zaxiralar faqat o'sha serverning o'zida edi.

Bu bo'limning printsipi: **"tekshirilmagan zaxira — zaxira emas".** Nazoratchi to'rt savolga
doim javob berishi kerak:

1. **Bormi?** Har loyiha uchun yaqinda zaxira olinganmi? (yosh)
2. **To'g'rimi?** Fayl butun va mazmunli ko'rinadimi? (hajm, yaxlitlik)
3. **Boshqa joydami?** Server o'lsa, nusxa boshqa serverda bormi? (offsite)
4. **Tiklasa bo'ladimi?** Oxirgi marta qachon haqiqatan tiklab ko'rilgan? (restore drill)

## 10.2. Chegaralar: kim nima qiladi

| Vazifa | Mas'ul |
|---|---|
| Zaxira olish (`pg_dump`, `tar`), saqlash muddati, offsite `rsync` | `appctl` (mavjud) |
| Zaxira fayllarini va holatini kuzatish, anomaliyani aniqlash, alert | **Nazoratchi** |
| Tiklash testining natijasini qayd etish, eslatish | **Nazoratchi** |
| Tiklash testining o'zini bajarish | Operator (qo'lda) yoki `appctl drill` (F3, 10.8) |
| Haqiqiy ma'lumotni tiklash (avariya) | Operator (`appctl restore`, 10.10) |

Nazoratchi zaxirani **o'zi olmaydi** va hech qachon `appctl restore` ni avtomatik ishga tushirmaydi
(`restore` mavjud bazani o'chiradi; X-7).

## 10.3. `appctl` ga kerakli o'zgartirishlar

Hozirgi `appctl backup` natijani faqat terminal chiqishi va `/var/log/appctl-backup.log` ga
yozadi. Nazoratchi uchun mashinada o'qiladigan natija kerak. Quyidagi ishlar Nazoratchi loyihasining
**F1 oldi shartidir** (17-bo'lim, ish E-01..E-03).

### 10.3.1. Loyiha holati fayli: `state.json`

Har `appctl backup <loyiha>` oxirida (muvaffaqiyat ham, xato ham) yoziladi:
`/opt/applications/backups/<loyiha>/state.json`. Yozish atomik (`.tmp` → `mv`).

```json
{
  "schema": 1,
  "project": "BiznesRadar",
  "host": "vmi3679093",
  "status": "ok",
  "started_at": "2026-10-22T03:15:01Z",
  "finished_at": "2026-10-22T03:15:41Z",
  "duration_s": 40,
  "daily": {
    "status": "ok",
    "file": "BiznesRadar-20261022-031501.sql.gz",
    "size_bytes": 48273114,
    "error": null
  },
  "weekly_files": {
    "status": "ok",
    "file": "BiznesRadar-files-20261018-031501.tar.gz",
    "size_bytes": 1204331520,
    "error": null
  }
}
```

Qoidalar:
- `status` — `ok` faqat barcha bajarilgan qadamlar muvaffaqiyatli bo'lsa; aks holda `fail` va
  `error` da bir qatorli sabab (maks. 300 belgi, yangi qatorsiz).
- `weekly_files` — haftalik fayl zaxirasi (yakshanba) bo'lmagan kunlarda `null`.
- `daily` — loyihada `DB_SERVICE` yo'q bo'lsa (baza dumpi olinmaydi) `null`. Dump xato bo'lsa `status: "fail"`,
  `file: null`, `size_bytes: 0`, `error` to'ldiriladi.
- Offsite natijasi `state.json` da **emas**, `_run.json` da (`rsync` barcha loyihalar uchun bir marta bajariladi).
- Haftalik `tar` xatosi ham `status: "fail"` beradi va `appctl backup` chiqish kodi 1 bo'ladi (asl skript
  bu holda jimgina 0 qaytarardi; E-01 da aniqlangan).
- `error`: faqat bosma ASCII, maks. 300 belgi, `token|secret|password|authorization` qiymatlari `***` bilan
  yopiladi.
- Vaqt — UTC, ISO-8601.
- `error` matnida parol/token bo'lishi mumkin emas (`pg_dump` xato matni odatda bunday
  ma'lumot bermaydi; baribir agent yuborishdan oldin `NFR-SEC-008` regex'i bilan maskalaydi).

### 10.3.2. Umumiy ishga tushirish holati: `_run.json`

`appctl backup all` (yoki cron) oxirida `/opt/applications/backups/_run.json`:

```json
{
  "schema": 1,
  "host": "vmi3679093",
  "run_id": "20261022-031501",
  "started_at": "2026-10-22T03:15:01Z",
  "finished_at": "2026-10-22T03:17:12Z",
  "projects": [
    {"name": "BiznesRadar", "status": "ok"},
    {"name": "Nazar", "status": "ok"},
    {"name": "lutfan_ai", "status": "ok"}
  ],
  "offsite": {
    "configured": true,
    "status": "ok",
    "target_host": "185.214.135.9",
    "exit_code": 0,
    "finished_at": "2026-10-22T03:17:12Z",
    "bytes_sent": 51237892
  }
}
```

`offsite.configured=false` bo'lsa, `status` yo'q (`null`) — bu AL-075 ni ishga tushiradi.

### 10.3.3. Yozish kodi (appctl ga qo'shiladigan eskiz)

```bash
json_escape() {
  local s=${1//\\/\\\\}
  s=${s//\"/\\\"}; s=${s//$'\n'/ }; s=${s//$'\t'/ }
  printf '%s' "${s:0:300}"
}

# write_state <loyiha> <status> <started> <kundalik_fayl> <hajm> <xato>
write_state() {
  local dir="$BACKUPS/$1" err="null"
  [ -n "${6:-}" ] && err="\"$(json_escape "$6")\""
  printf '{"schema":1,"project":"%s","host":"%s","status":"%s","started_at":"%s","finished_at":"%s","daily":{"status":"%s","file":"%s","size_bytes":%s,"error":%s},"weekly_files":null}\n' \
    "$1" "$(hostname)" "$2" "$3" "$(date -u +%FT%TZ)" "$2" "${4:-}" "${5:-0}" "$err" \
    > "$dir/state.json.tmp" && mv "$dir/state.json.tmp" "$dir/state.json"
}
```

> Bu eskiz yo'nalishni ko'rsatadi; haftalik fayl bloki va davomiylik hisobi amalga oshirishda
> qo'shiladi. `jq` ga bog'liq bo'lmaslik uchun (serverlarda bo'lmasligi mumkin) JSON `printf`
> bilan yoziladi.
>
> **Amalga oshirildi (E-01):** `deploy/appctl-patches/appctl` (README va 20 ta sinov bilan). Eskizdagi
> `json_escape` tuzatildi: 300 belgida kesishdan *keyin* qochirish `\"` ni bo'lib, yaroqsiz JSON berishi mumkin
> edi (avval kesiladi, keyin qochiriladi); ASCII bo'lmagan baytlar va boshqaruv belgilari yaroqsiz JSON/UTF-8
> hosil qilardi (bosma ASCII ga keltiriladi); maxfiy qiymatlar yopiladi.

### 10.3.4. `appctl list --json` va `appctl status --json`

Ikkala buyruq ham `--json` bayrog'ini qo'llab-quvvatlaydi (sxema 18.1-bo'limda). Nazoratchi
agenti `appctl status --json` ni 5 daqiqada bir marta chaqiradi (yoki zaxira/sertifikat
ma'lumotini fayllardan o'zi o'qiydi; ikkala usul ham F1 da mumkin, ustuvor — fayllar, chunki
ular `appctl` bajarilishiga bog'liq emas).

### 10.3.5. Cron heartbeat

`appctl backup all` oxirida Nazoratchi heartbeat'i yuboradi (9.14-bo'lim). Bu `state.json` dan mustaqil
ikkinchi signal: cron umuman ishlamasa (masalan, `crond` o'chiq yoki fayl o'chirilgan), `state.json`
yangilanmaydi va heartbeat ham kelmaydi — AL-047 va AL-068 birgalikda aniqlaydi.

**Amalga oshirildi (E-03), TZ dagi dastlabki dizayndan farqli.** Heartbeat cron qatoriga emas, `appctl` ichiga
qo'yildi (`/etc/cron.d/appctl-backup` o'zgarmaydi). Sabablari:

1. `/etc/cron.d` qatorini `\` bilan bir necha qatorga bo'lib bo'lmaydi (cron buni qo'llab-quvvatlamaydi), 9.14
   dagi eski namuna cron'da ishlamasdi.
2. `A && curl ok || curl fail` zanjiri zaxira muvaffaqiyatli bo'lib, faqat birinchi `curl` yiqilsa, noto'g'ri
   "fail" yuborardi.
3. Token URL ichida; `/etc/cron.d` hamma o'qiy oladigan (0644) fayl, `appctl.conf` ni esa agent o'qiydi
   (7.8). Token `/opt/applications/appctl.secret` da (0600, `HEARTBEAT_URL`).

Xatti-harakat (barchasi sinalgan, `deploy/appctl-patches/`):

- Faqat `backup all` (cron ishi) yuboradi; bitta loyiha zaxirasi yubormaydi. Muvaffaqiyatda `status=ok&duration=<s>`,
  xatoda `status=fail&duration=<s>&msg=fail: <loyihalar>[,offsite]` (loyiha nomlari, maxfiy ma'lumotsiz).
- **R-109:** heartbeat zaxira natijasini, fayllarni va chiqish kodini hech qachon o'zgartirmaydi. Xato bo'lsa
  (core yetib bo'lmaydi, 500, `curl` yo'q) faqat stderr'ga ogohlantirish; URL (token) chop etilmaydi. `curl`
  `--connect-timeout 5 -m 10` (`HEARTBEAT_TIMEOUT`).
- Kutilmagan to'xtash (SIGTERM/SIGINT/SIGHUP) EXIT tuzog'i orqali bitta `fail` yuboradi (`... to'xtatildi (kod 143)`):
  jimlik (AL-047) o'rniga tezroq AL-048.
- `appctl heartbeat [ok|fail] [xabar]` — sozlamani qo'lda sinash; `appctl heartbeat-set <https-url>` URL ni qat'iy
  tekshirib (bash o'qiydigan fayl!) `appctl.secret` ga yozadi; `setup.sh --heartbeat-url=...` (yoki
  `NAZORATCHI_HEARTBEAT_URL`) shuni chaqiradi, noto'g'ri URL bo'lsa nginx o'zgartirilmasdan to'xtaydi.

E-03 da topilgan: asl skriptda buzuq `.appctl` `backup all` ichida jimgina o'tib ketardi (dump o'tkazib yuborilib,
loyiha `ok`). Endi shu loyiha `fail` bo'ladi, qolganlari zaxiralanadi.

## 10.4. Loyiha zaxira holati: qoidalar

Har loyiha uchun holat quyidagi tartibda (yuqoridan pastga, birinchi mos kelgani) hisoblanadi:

| Tartib | Holat | Shart | Rang |
|---|---|---|---|
| 1 | `failed` | oxirgi `state.json.status = fail` | qizil |
| 2 | `stale` | eng yangi muvaffaqiyatli kunlik zaxira yoshi > `max_age_h` (standart 26) | qizil |
| 3 | `suspicious` | hajm anomaliyasi (10.5.2) yoki `gz_ok = false` | qizil/to'q sariq |
| 4 | `warning` | offsite sozlanmagan yoki orqada; drill muddati o'tgan; haftalik fayl yo'q | sariq |
| 5 | `ok` | yuqoridagilarning hech biri | yashil |
| — | `unknown` | agent jim yoki loyiha uchun zaxira siyosati belgilanmagan | kulrang |

Eslatma: `failed` ham, `stale` ham bo'lishi mumkin; UI barcha muammolarni ro'yxat qilib
ko'rsatadi, eng og'iri belgilangan rangni beradi.

### 10.4.1. Siyosat (har loyiha uchun sozlanadi)

| Parametr | Standart | Izoh |
|---|---|---|
| `expect_daily` | `true` | Kunlik DB dump kutiladi (statik saytlar uchun `false`) |
| `max_age_h` | 26 | 24 soat + 2 soat zaxira (cron kechikishi, katta dump) |
| `critical_age_h` | 50 | Ikki kun o'tkazib yuborilgan |
| `expect_weekly_files` | `BACKUP_PATHS` bor bo'lsa `true` | Yakshanba tar.gz |
| `weekly_max_age_h` | 192 | 8 kun |
| `size_floor_bytes` | 1 024 | `appctl` ning o'z chegarasi |
| `size_min_ratio` | 0.5 | Median'ning 50% idan kichik — shubhali |
| `size_max_ratio` | 3.0 | Median'ning 300% idan katta — shubhali |
| `require_offsite` | `true` | Offsite sinxron kutiladi |
| `drill_every_days` | 90 | Tiklash testi davriyligi |
| `retention_daily` / `retention_weekly` | 7 / 5 | `appctl` bilan mos |

## 10.5. Hisoblash qoidalari (aniq)

### 10.5.1. Zaxira yoshi

`age_h = (now − finished_at_of_latest_successful_daily) / 3600`.

"Eng yangi muvaffaqiyatli" manbalari ustuvorlik tartibida:
1. `state.json` (`daily.status = ok` → `finished_at`);
2. agar `state.json` yo'q yoki eskirgan — papka skaneri: eng yangi `*.sql.gz` (`.tmp` siz) `mtime` si.

Ikkala manba farq qilsa (masalan, `state.json` "ok", lekin fayl yo'q), **fayl** haqiqat
manbai: `backup_state_mismatch` belgisi qo'yiladi va holat `suspicious`.

**Soat zonasi.** Serverlar `UTC` da; cron `03:15` = `08:15 Asia/Tashkent`. UI vaqtni
foydalanuvchi zonasida ko'rsatadi; hisoblash UTC da.

### 10.5.2. Hajm anomaliyasi

- Asos: oxirgi 7 ta **muvaffaqiyatli kunlik** zaxira hajmlarining medianasi (`M`).
- Yangi zaxira hajmi `S` bo'lsa:
  - `S < size_floor_bytes` → `failed` (appctl o'zi qabul qilmaydi, ammo tekshiriladi);
  - `S < M × size_min_ratio` → "shubhali (juda kichik)" (AL-071);
  - `S > M × size_max_ratio` → "shubhali (juda katta)" (AL-072, `info`).
- 7 tadan kam tarix bo'lsa (yangi loyiha) — faqat `size_floor_bytes` tekshiriladi.
- Qo'lda "bu normal" deb belgilash mumkin (`baseline_reset`): bazada katta ma'lumot
  o'chirilgan/qo'shilgan bo'lsa, tarix qayta boshlanadi.

### 10.5.3. Yaxlitlik

Agent eng yangi `*.sql.gz` ga kuniga 1 marta `gzip -t` (o'qish orqali) bajaradi (CPU: 50 MB fayl
≈ 0.3 s). Natija `backup_gz_ok`. Fayl o'zgarish vaqti oxirgi tekshiruvdan keyin o'zgarmagan
bo'lsa, qayta tekshirilmaydi. `gzip -t` xato bersa — `suspicious` + AL-073 (`critical`).

### 10.5.4. Haftalik fayl zaxirasi

`BACKUP_PATHS` bor loyihalar (BiznesRadar media, lutfan_ai media+minio, wmg sqlite+media) uchun
yakshanba kuni `...-files-*.tar.gz` chiqishi kerak. 8 kundan eski bo'lsa — AL-074.
`tar` fayli ham `gzip -t` bilan tekshiriladi (haftada 1 marta; hajmi katta bo'lsa — faqat
`gzip -t` ning birinchi 64 MB si, F3).

### 10.5.5. Saqlash siyosati

Kunlik fayllar soni ≤ `retention_daily + 2`, haftalik ≤ `retention_weekly + 2` bo'lishi kerak;
oshsa — `info` belgi (appctl tozalamayapti, disk to'lishi mumkin).

## 10.6. Offsite monitoringi

### 10.6.1. Ikki darajali tekshiruv

| Daraja | Manba | Nimani isbotlaydi | Ishonchlilik |
|---|---|---|---|
| 1 | `_run.json.offsite` (asosiy serverdagi `appctl` natijasi) | `rsync` xatosiz tugadi | O'rtacha (rsync "muvaffaqiyat" qaytarsa ham mazmun to'liq bo'lmasligi mumkin) |
| 2 | Offsite papkadagi agent skaneri (S-00) | Fayl **haqiqatan** u yerda, hajmi mos | Yuqori |

Nazoratchi ikkalasini ham ishlatadi. Offsite serverda agent bo'lmasa, faqat 1-daraja ishlaydi
va panelda "offsite tasdiqlanmagan (agent yo'q)" belgisi ko'rinadi.

### 10.6.2. Solishtirish algoritmi

Har loyiha uchun, har 15 daqiqada:

1. Mahalliy eng yangi kunlik fayl: `(nom, hajm, mtime)`.
2. Offsite'dagi shu loyiha papkasi (`<offsite_root>/<loyiha>/daily/`) eng yangi fayli: `(nom, hajm, mtime)`.
3. Agar `nom` bir xil va `hajm` bir xil → `in_sync = true`.
4. Aks holda `lag_h = (mahalliy.mtime − offsite.mtime)`; `lag_h` > 26 (AL-076) yoki > 50 (AL-077) bo'lsa alert.
5. Nom farqi, lekin hajm mos kelmasa: `out_of_sync` (AL-078) — rsync oraliq holatda bo'lishi mumkinligi
   uchun 30 daqiqa kutiladi.

Offsite'da `--delete` bo'lmagani sababli, u yerda mahalliydan ko'ra **ko'p** fayl bo'lishi normal.

### 10.6.3. Offsite serverni tayyorlash (spetsifikatsiya)

| Parametr | Qiymat |
|---|---|
| Joy | **S-00** (Owner qarori): asosiy S-01 dan boshqa server, core bilan bir serverda; bir provayder (Contabo) — R-110. S-03 ishlatilmaydi |
| Papka | `/srv/backups/main-server`, alohida foydalanuvchi (`appctl.conf` `OFFSITE` shunga moslanadi) |
| Kirish | Faqat SSH-kalit; asosiy serverning kalitiga `command="rrsync /srv/backups/main-server"` cheklovi (faqat shu papkaga yozish) |
| Agent | S-00 dagi `nazoratchi-agent`, `backup.root` shu papkaga ko'rsatilgan |
| Disk | 200 GB SSD S-00 da core bazasi (≈ 6–14 GB), Docker va offsite uchun; offsite papkasi alohida kvota/bo'lim bilan cheklanadi, 25% bo'sh |
| Tozalash | Offsite'da alohida cron: 30 kundan eski kunlik, 12 haftadan eski haftalik fayllarni o'chirish |
| Xavfsizlik | Asosiy server buzilsa, hujumchi offsite zaxirani o'chira olmasligi uchun: `rrsync` yozuv-faqat (`--ro` emas, lekin `--delete` yo'q) yoki offsite'da `chattr +a` / kunlik snapshot |

> Bu talablar `rsync -a` (`--delete`siz) tanlovi bilan bog'liq: hujumchi yoki xato asosiy
> serverda fayllarni o'chirsa ham, offsite'dagi nusxalar o'chmaydi.

## 10.7. Zaxira hajmi va disk

- `backup_dir_bytes` (har loyiha) va `backup_root_free_bytes` kuzatiladi.
- 90 kunlik o'sish chizig'i bo'yicha "zaxira bo'limi to'lishiga N kun" bashorati (FR-BKP-008).
- `backup_root_free_bytes` < 15% (yoki < 5 GB) → AL-079 (`warning`); < 5% → `critical` (rejalashtirilgan
  zaxira yozilmay qolishi mumkin).
- Offsite uchun ham xuddi shu (AL-080).

## 10.8. Restore drill (tiklash testi)

### 10.8.1. Maqsad

Zaxiradan haqiqatan ma'lumotni tiklab ko'rish, shuni isbotlash: (a) fayl o'qiladi,
(b) bazaga yuklanadi, (c) ma'lumot mazmunli (jadvallar va qatorlar bor), (d) ilova
shu bilan ishlay oladi (F3), (e) qancha vaqt ketishini bilish (RTO).

### 10.8.2. Xavfsizlik qoidasi (juda muhim)

> **`appctl restore` ni ishlab turgan (production) bazaga drill uchun ishlatish qat'iyan
> taqiqlanadi** — u bazani `DROP DATABASE ... WITH (FORCE)` bilan o'chiradi. Drill faqat
> **alohida (vaqtinchalik) bazada** bajariladi.

### 10.8.3. Qo'lda drill tartibi (PostgreSQL loyihalar, F2)

1. Eng yangi (yoki tanlangan) `*.sql.gz` ni aniqlash.
2. Shu loyihaning **PostgreSQL asosiy versiyasi bilan bir xil** vaqtinchalik konteyner
   ko'tarish (masalan, BiznesRadar — 17, Nazar — 16, lutfan_ai — 15):
   ```bash
   docker run -d --rm --name drill-pg -e POSTGRES_PASSWORD=drill -p 127.0.0.1:55432:5432 postgres:17
   ```
3. Bazani va rolni yaratish (dump rol nomiga bog'liq bo'lsa):
   ```bash
   docker exec drill-pg psql -U postgres -c "CREATE ROLE biznesradar LOGIN; CREATE DATABASE biznesradar OWNER biznesradar;"
   ```
4. Yuklash va vaqtni o'lchash:
   ```bash
   time gunzip -c BiznesRadar-20261022-031501.sql.gz | docker exec -i drill-pg psql -U postgres -d biznesradar -v ON_ERROR_STOP=1 -q
   ```
5. Tekshirish: jadvallar soni va asosiy jadvallardagi qatorlar soni; ularni ishlab turgan
   bazadagi qiymat bilan (taxminan, zaxira vaqtidan keyingi o'sishni hisobga olib) solishtirish:
   ```bash
   docker exec drill-pg psql -U postgres -d biznesradar -Atc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"
   docker exec drill-pg psql -U postgres -d biznesradar -Atc "SELECT relname, n_live_tup FROM pg_stat_user_tables ORDER BY n_live_tup DESC LIMIT 5"
   ```
6. Konteynerni to'xtatish (`docker stop drill-pg`) — `--rm` tufayli o'chadi.
7. Natijani panelda qayd etish (FR-BKP-016): sana, fayl, davomiylik, jadval/qator soni,
   natija, izoh.

**Muvaffaqiyat mezonlari:** xatosiz yuklandi; jadvallar soni ishlab turgan bazadagi bilan
bir xil (yoki kamida shu); eng katta 3 jadvalning qator soni ishlab turgan bazadagidan
5% dan ko'p kam emas.

### 10.8.4. Boshqa turdagi loyihalar

| Tur | Drill usuli | Tekshiruv |
|---|---|---|
| SQLite (wmg) | `.sqlite3` nusxasini vaqtinchalik papkaga ochish, `sqlite3 db 'PRAGMA integrity_check'` va `SELECT count(*)` | `integrity_check = ok`; asosiy jadvallar bo'sh emas |
| Media (tar.gz) | `tar -tzf` ro'yxat; tasodifiy 20 fayl ni vaqtinchalik papkaga chiqarib solishtirish (`sha256sum`) | Xatosiz; fayllar soni kutilganga yaqin |
| MinIO ma'lumoti | Vaqtinchalik MinIO konteyneriga tiklab, bucket ro'yxatini ko'rish | Bucketlar bor, ob'ektlar ochiladi |
| Nazoratchi'ning o'zi | Yangi bo'sh serverda tiklash yo'riqnomasi (15.9) bo'yicha | Panel ochiladi, reyestr to'liq |

### 10.8.5. Davriylik va eslatma

- Har loyiha uchun `drill_every_days` (standart 90). Eslatma: muddatdan 14 kun oldin `info`,
  muddati o'tganda `warning` (AL-082), 100 kun — yuqoriroq.
- Birinchi drill — Nazoratchi F1 ishga tushishi bilan, **hammasi uchun** (hozirgi zaxiralar hech
  qachon tiklab ko'rilmagan).
- Drill xato bilan tugasa (`failed`) — AL-083 (`high`) va zaxira holati `warning` → `failed`
  (agar oxirgi muvaffaqiyatli drill 100 kundan eski bo'lsa).

### 10.8.6. Avtomatik drill (`appctl drill`, F3, ixtiyoriy)

`appctl drill <loyiha> [fayl]` — yuqoridagi 1–6 qadamlarni o'zi bajaradi (vaqtinchalik
konteyner, yuklash, hisoblash, tozalash) va natijani API orqali yuboradi
(`POST /backups/drills`, API token bilan). Haftada bir marta bitta tasodifiy loyiha uchun
cron orqali. Bu talab FR-BKP-020 (4-bo'lim).

## 10.9. Zaxira sahifasi va alertlar bilan bog'lanish

| Ko'rsatkich / hodisa | Alert (12-bo'lim) | UI joyi |
|---|---|---|
| Yosh > 26 s / > 50 s | AL-068 / AL-069 | Zaxiralar jadvali, loyiha kartasi |
| `status = fail` | AL-070 | Loyiha kartasi, incident |
| Hajm kichik / katta | AL-071 / AL-072 | Hajm grafigi (anomaliya nuqtasi) |
| `gz_ok = false` | AL-073 | Kartada qizil belgi |
| Haftalik fayl yo'q | AL-074 | Kartada |
| Offsite sozlanmagan | AL-075 | Dashboard va jadvalda doimiy belgi |
| Offsite eskirdi / farq | AL-076, AL-077, AL-078 | "Offsite" ustuni |
| Zaxira bo'limi to'ldi | AL-079, AL-080 | Server sahifasi |
| Drill muddati / xato | AL-081, AL-082, AL-083 | Kartadagi "Oxirgi drill" |

## 10.10. Avariya holatida tiklash (ma'lumot uchun)

Nazoratchi bu jarayonni bajarmaydi, lekin panel zarur ma'lumotni bir joyda ko'rsatadi
("Tiklash yo'riqnomasi" tugmasi → runbook RB-030):

1. Eng yangi **tekshirilgan** zaxira (`gz_ok = true`, hajm normal) — mahalliy yoki offsite.
2. Zaxira fayli joyi va serveri.
3. `appctl restore <loyiha> <fayl.sql.gz> --yes` buyrug'i (ogohlantirish: mavjud bazani o'chiradi).
4. Oxirgi drill natijasi: davomiylik (RTO bahosi) va muvaffaqiyat.
5. Loyiha `.appctl` konfigi va `docker-compose` fayli joylashuvi.

## 10.11. Qabul mezonlari (zaxira moduli)

| № | Sinov | Kutilgan natija |
|---|---|---|
| T-BKP-01 | `appctl backup BiznesRadar` muvaffaqiyatli | `state.json` yozildi; panel 5 daqiqada yangilandi |
| T-BKP-02 | Cron'ni o'chirib 27 soat kutish (yoki vaqtni siljitish) | AL-068 `high` alerti |
| T-BKP-03 | Dump faylini kesib qo'yish (`truncate`) | AL-073 `critical` |
| T-BKP-04 | `pg_dump` xatosini keltirib chiqarish (noto'g'ri `DB_USER`) | `state.json: fail`, AL-070, xato matni xabarda |
| T-BKP-05 | `OFFSITE` bo'sh | AL-075 doimiy ogohlantirish |
| T-BKP-06 | Offsite'ga rsync'ni to'xtatish | 26 soatdan keyin AL-076 |
| T-BKP-07 | Offsite'da faylni o'chirish/kichraytirish | AL-078 |
| T-BKP-08 | Bo'sh (1 KB) dump | `appctl` rad etadi; Nazoratchi `failed` ko'rsatadi |
| T-BKP-09 | Drill natijasini kiritish | Kartada yangilandi, eslatma muddati qayta boshlandi |
| T-BKP-10 | `state.json` ni o'chirib, fayl qoldirish | Skaner manbasi ishlaydi, `unknown` emas |
