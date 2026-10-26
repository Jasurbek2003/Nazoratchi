# `appctl` ga Nazoratchi o'zgartirishlari

TZ 10.3, 18.1, 9.14 va F0 ishlari E-01…E-03 (hammasi bajarildi). Asl skript `Nazar/deploy/server/appctl` (218 qator) boshqa repoda va
jonli serverlarga o'rnatiladi, shuning uchun bu yerdagi nusxaga o'zgartirish kiritildi, **asl fayl va serverlarga
tegilmagan** (R-109).

| Fayl | Nima |
|---|---|
| `appctl.orig` | Asl skript (sha256 `c2b2e5b5…`), solishtirish va qaytarish uchun |
| `appctl` | O'zgartirilgan skript |
| `appctl.diff` | `appctl.orig` → `appctl` (E-01…E-03, `patch -p1` bilan qo'llanadi) |
| `setup.sh.orig`, `setup.sh`, `setup.diff` | `Nazar/deploy/server/setup.sh` (sha256 `ab3b9f96…`) va `--heartbeat-url` qo'shilgan nusxa |
| `tests/test_state.py` | E-01: 21 ta sinov (soxta `docker`/`rsync`/`date`, asl skript bilan solishtirib) |
| `tests/test_json.py` | E-02: 16 ta sinov (soxta `docker`/`df`/`free`/`openssl`) |
| `tests/test_heartbeat.py` | E-03: 31 ta sinov (haqiqiy `curl` va mahalliy HTTP server) |
| `tests/test_setup.py` | E-03: `setup.sh` bir martalik Debian konteynerida (root, soxta `nginx`/`systemctl`) |

## E-01: `state.json` va `_run.json` (bajarildi)

**`<BACKUPS>/<loyiha>/state.json`** — har `appctl backup <loyiha>` oxirida (muvaffaqiyat ham, xato ham).
Maydonlar TZ 10.3.1 bo'yicha: `schema`, `project`, `host`, `status` (`ok`|`fail`), `started_at`, `finished_at`,
`duration_s`, `daily`, `weekly_files`. Vaqt UTC, yozuv atomik (`.tmp` → `mv`), rejim `0644`.

**`<BACKUPS>/_run.json`** — faqat `appctl backup all` oxirida: `run_id`, `projects[{name,status}]`, `offsite`
(`configured`, `status`, `target_host`, `exit_code`, `finished_at`, `bytes_sent`). Offsite sozlanmagan bo'lsa
`configured=false`, qolgani `null`.

### Asl skriptdan farqlar (barchasi sinalgan)

1. **Haftalik `tar` xatosi endi zaxirani muvaffaqiyatsiz deb hisoblaydi** (`status=fail`, `appctl` chiqish kodi 1,
   yarim fayl o'chiriladi). Asl skript bu holda **0 qaytarardi** (jim nosozlik, `|| failed=1` ga yetmasdi).
   Natija: cron'dagi heartbeat zanjirida bu holat `fail` bo'ladi. Boshqa barcha holatlarda chiqish kodi va
   fayllar asl skript bilan bir xil (`test_exit_code_and_dump_match_original_script`).
2. **`rsync` ga `--stats` qo'shildi** va chiqishi faylga olinib, tugagach logga chop etiladi (jonli emas).
   `bytes_sent` shundan olinadi.
3. **`pg_dump` stderr'i** vaqtincha faylga olinadi (xato matni `state.json` ga tushishi uchun), so'ng aynan
   shu matn `stderr` ga chop etiladi: log o'zgarmaydi.

Dump muvaffaqiyatsiz bo'lsa asl xatti-harakat saqlanadi: haftalik fayllar va eski nusxalarni tozalash
o'tkazib yuboriladi.

### Xavfsizlik chorasi (R-109)

- `state.json`/`_run.json` yozilmasa, faqat `ogohlantirish` chiqadi; zaxira va chiqish kodi o'zgarmaydi.
- Xato matni: faqat bosma ASCII, maks. 300 belgi, `token|secret|password|authorization` qiymatlari `***`
  bilan yopiladi (`Authorization: Bearer <token>` ham). TZ 10.3.3 eskizidagi `json_escape` buni qilmasdi va
  300 belgida kesganda `\"` ni bo'lib, yaroqsiz JSON hosil qilishi mumkin edi: bu yerda avval kesiladi, keyin
  qochiriladi.
- Vaqtinchalik fayl yo'li uchun `mktemp` ishlamasa, `/dev/null` emas, `<zaxira>/.stderr.$$` ishlatiladi
  (aks holda `rm -f` `/dev/null` ni o'chirishi mumkin edi).
- `hostname` bo'lmasa `unknown`; `jq` kerak emas.

## E-02: `list --json` va `status --json` (bajarildi)

Sxema TZ 18.1 bo'yicha (`docs/TZ/18a-ilovalar.md`). Faqat stdout'ga bitta qator JSON, tashxis stderr'ga, kod 0;
xatoda `{"schema":1,"error":"…"}` va kod 1 (buzuq `.appctl` ham shunday). `jq` kerak emas.

- **`list --json`:** har loyiha uchun `state` (`running|partial|stopped|unknown`), `running`/`total`, `compose_file`,
  `compose_extra`, `health_url` (maxfiy qismlari yopiladi), `db{service,user,name}`, `backup_paths[]`.
  Parol va `HEALTH_CURL_OPTS` chiqmaydi.
- **`status --json`:** `disk`, `memory`, `containers` (`docker ps -a`, `health`), `certificates` (`days_left`),
  `backups` (`last_daily_at`, `daily_count`, `weekly_count`). Olib bo'lmagan bo'lim `null`, "yo'q" ma'nosida emas.
- **Inson rejimi o'zgarmadi:** `appctl list` va `appctl status` chiqishi asl skript bilan bayt-baytiga bir xil
  (sinov bilan tasdiqlangan, haqiqiy Docker'da ham).
- Yagona yangi kirish: `APPCTL_LETSENCRYPT` (standart `/etc/letsencrypt/live`), faqat `status --json` o'qiydi.

Sinov jarayonida topilgan va tuzatilgan: `weekly` papkasi yo'q bo'lsa `find` + `pipefail` + `set -e` skriptni
jimgina to'xtatardi; `df` chiqishida fayl tizimi nomida bo'shliq bo'lsa (Windows/Git Bash) ustunlar siljirdi.

## E-03: heartbeat (bajarildi)

`appctl backup all` oxirida Nazoratchi'ga `GET <HEARTBEAT_URL>?status=ok|fail&duration=<s>[&msg=...]` yuboradi
(TZ 9.14). Cron qatori o'zgarmaydi; heartbeat `appctl` ichida (TZ dagi cron zanjiri `/etc/cron.d` da ishlamasdi,
qator bo'linmaydi va faqat `curl` yiqilganda ham noto'g'ri `fail` berardi: TZ 10.3.5 da izohlangan).

| Nima | Qanday |
|---|---|
| Sozlash | `sudo bash setup.sh --heartbeat-url=https://<core>/hb/<TOKEN>` yoki `appctl heartbeat-set <url>`. Token `/opt/applications/appctl.secret` ga (0600). `NAZORATCHI_HEARTBEAT_URL` muhit o'zgaruvchisi shell tarixida qoldirmaydi |
| Sinash | `appctl heartbeat` (ok) / `appctl heartbeat fail "xabar"`; muvaffaqiyatsiz bo'lsa kod 1 |
| Qachon yuboriladi | Faqat `backup all`. Xatoda `msg=fail: Alpha,offsite` |
| Kutilmagan to'xtash | SIGTERM/INT/HUP da bitta `fail` (`kod 143`) |
| **R-109** | Heartbeat zaxira natijasi, fayllari va chiqish kodiga ta'sir qilmaydi; `curl` xatosi faqat ogohlantirish; token chop etilmaydi; `curl -m 10` |
| Xavfsizlik | `heartbeat-set` URL ni qat'iy tekshiradi (faqat https va xavfsiz belgilar; qo'shtirnoq, `$`, teskari qiyshiq chiziq, bo'shliq taqiqlangan): fayl bash tomonidan o'qiladi |

Qo'shimcha tuzatish: buzuq `.appctl` `backup all` ichida jimgina o'tib ketardi (dump o'tkazib yuborilib, loyiha
`ok`). Endi o'sha loyiha `fail`, boshqalari zaxiralanadi (chiqish kodi 1). Boshqa buyruqlarda (`up`, `list`)
bunday xatoda chiqish kodi 2 o'rniga 3.

## Serverga o'rnatishdan oldin (tavsiya)

1. Serverda asl nusxani saqlang: `cp /usr/local/bin/appctl /usr/local/bin/appctl.orig`.
2. Yangisini o'rnating: `install -m 0755 appctl /usr/local/bin/appctl` va `bash -n /usr/local/bin/appctl`.
3. **Bitta** loyihada sinang: `appctl backup <loyiha>`; `cat /opt/applications/backups/<loyiha>/state.json`
   (JSON yaroqli, `status: ok`, fayl hajmi `ls -l` bilan bir xil).
4. Keyin `appctl backup all`, `_run.json` ni tekshiring; ertasi kuni cron natijasini (`/var/log/appctl-backup.log`).
5. Qaytarish: `cp /usr/local/bin/appctl.orig /usr/local/bin/appctl`. (`state.json` fayllari zararsiz, qolaveradi.)

## Sinovlar

```bash
uv run --with pytest pytest deploy/appctl-patches/tests -q     # 69 ta (Linux: 68 + docker'li setup testi)
docker run --rm -v "$PWD:/mnt" koalaman/shellcheck:stable -e SC2034 /mnt/deploy/appctl-patches/appctl
```

Tekshirilgan: Windows (Git Bash), Linux (`python:3.13-slim`, haqiqiy `free`/`df`/`openssl`/`find`), haqiqiy
PostgreSQL 16 konteyneri (zaxira va `pg_dump` xatosi) hamda haqiqiy `docker compose` loyihalari (`list --json`).
`SC2034` — asl skriptdagi eski ogohlantirish (`for i in …`), o'zgartirilmagan.

## Keyingi

- **E-03:** `setup.sh`/cron: heartbeat chaqiruvi (TZ 10.3.5, 9.14). `|| true` bilan, zaxira zanjirini buzmasdan.
