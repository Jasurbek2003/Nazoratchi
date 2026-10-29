# 7. Agent spetsifikatsiyasi va metrikalar katalogi

## 7.1. Agentning vazifasi va chegaralari

`nazoratchi-agent` — kuzatiladigan serverda ishlaydigan yagona, statik Go binari. U:

- tizim, disk, tarmoq, Docker, systemd, zaxira, sertifikat va xavfsizlik ma'lumotlarini yig'adi;
- ularni paketlab core'ga yuboradi;
- core'dan kelgan cheklangan buyruqlarni (faqat interval o'zgartirish, qayta yuklash,
  o'z-o'zini yangilash) bajaradi.

Agent **qilmaydi**: serverda ixtiyoriy buyruq bajarmaydi (masofaviy shell yo'q), fayl
mazmunini yubormaydi, hech qanday kiruvchi port ochmaydi, konteynerlarni boshqarmaydi
(X-8, X-3).

## 7.2. Ichki tuzilma

```
┌────────────────────────── nazoratchi-agent ──────────────────────────┐
│  Scheduler (har kollektor o'z intervali bilan)                      │
│     │                                                               │
│     ├─ system  ──┐                                                  │
│     ├─ disk    ──┤                                                  │
│     ├─ net     ──┤                                                  │
│     ├─ docker  ──┼──► Batcher (15 s) ──► Queue (disk, 20 MB) ──► Sender ──► HTTPS ──► core
│     ├─ systemd ──┤        ▲                                  │      ▲
│     ├─ backup  ──┤        │                                  │      └ qayta urinish (backoff)
│     ├─ certs   ──┤   Facts (kam o'zgaradigan ma'lumot)       └ javob: server_time, commands
│     └─ ssh     ──┘                                                  │
│  Config (agent.yaml) ◄── SIGHUP/yangilanish          Logger (JSON, stderr → journald)
└────────────────────────────────────────────────────────────────────┘
```

| Qism | Tavsifi |
|---|---|
| Scheduler | Har kollektor mustaqil goroutine; `ticker` + jitter (±10%); kollektor `timeout` (interval/2) dan oshsa to'xtatiladi va `agent_collector_errors` oshadi |
| Batcher | Oxirgi 15 soniya ichidagi namunalarni bitta paketga yig'adi; `facts` o'zgarganda yoki 10 daqiqada bir marta qo'shadi |
| Queue | Diskdagi navbat `/var/lib/nazoratchi/queue/` (har paket alohida fayl `seq.json.gz`); maksimum 20 MB yoki 15 daqiqa; to'lsa eng eski o'chadi |
| Sender | HTTPS `POST`, TLS 1.2+, timeout 10 s; xato → eksponensial kutish (1, 2, 4, 8, 16, 30 s, jitter bilan); muvaffaqiyatda navbatni vaqt tartibida bo'shatadi |
| Config | `/etc/nazoratchi/agent.yaml`; xato bo'lsa agent ishga tushmaydi va aniq xabar beradi |
| Logger | JSON, `level`, `component`; token va maxfiy qiymatlar maskalanadi |

## 7.3. Metrika modeli va nomlash

### 7.3.1. Qoidalar

- Nom: `snake_case`, birlik oxirida (`_bytes`, `_percent`, `_seconds`, `_per_sec`), bitta nom bitta ma'no.
- Turi: **gauge** (lahzalik qiymat) yoki **counter** (faqat oshadi, qayta boshlanishi mumkin).
  Tezlikni (`*_per_sec`) agent o'zi hisoblaydi (ikki o'lchov farqi / vaqt); sanagichlar (counter)
  faqat "umumiy qayta ishga tushishlar" kabi hollarda xom holda yuboriladi.
- Belgilar (labels): kardinallik kichik bo'lishi kerak. Ruxsat: `device`, `mount`, `iface`,
  `container`, `project`, `service`, `unit`, `core`, `mode`, `name`, `kind`. **Taqiq:** URL,
  foydalanuvchi ID, IP manzillar (har safar yangi qiymat chiqadigan belgilar).
- Har host uchun noyob qatorlar (series) soni ≤ 1 000 (agent o'zi cheklaydi; oshsa
  `agent_series_dropped` metrikasi yuboriladi).
- Vaqt tamg'asi: namuna olingan paytdagi UTC, millisekund aniqligida.

### 7.3.2. Standart intervallar

| Kollektor | Interval | Sozlanadi |
|---|---|---|
| `system` | 15 s | ha (5–60 s) |
| `disk` (fayl tizimi) | 30 s | ha |
| `diskio` | 15 s | ha |
| `net` | 15 s | ha |
| `docker` | 30 s | ha |
| `systemd` | 30 s | ha |
| `backup` | 300 s | ha |
| `certs` | 21 600 s (6 soat) | ha |
| `ssh` | 300 s | ha |
| `facts` | 600 s | ha |
| `apt` | 86 400 s (kuniga 1) | ha |
| `reboot` | 300 s | ha |

## 7.4. Metrikalar katalogi

Quyidagi jadvallarda har metrika uchun: **Nom**, **Tur**, **Birlik**, **Belgilar**, **Manba**,
**Izoh**. Ustuvorlik belgisi (F1/F2/F3) — qaysi bosqichda amalga oshirilishi.

### 7.4.1. `system` kollektori

| Nom | Tur | Birlik | Belgilar | Manba | Izoh | Faza |
|---|---|---|---|---|---|---|
| `cpu_usage_percent` | gauge | % | `mode` = user, nice, system, idle, iowait, irq, softirq, steal | `/proc/stat` (ikki o'lchov farqi) | Hamma yadro bo'yicha o'rtacha | F1 |
| `cpu_busy_percent` | gauge | % | — | `/proc/stat` | `100 − idle − iowait` | F1 |
| `cpu_core_busy_percent` | gauge | % | `core` | `/proc/stat` | Har yadro (kardinallik = yadro soni) | F2 |
| `load1`, `load5`, `load15` | gauge | — | — | `/proc/loadavg` | | F1 |
| `load_per_core_1m` | gauge | — | — | `load1 / cpu_count` | 1.0 dan oshsa — yuklama yadro soniga teng | F1 |
| `mem_total_bytes` | gauge | bayt | — | `/proc/meminfo` `MemTotal` | | F1 |
| `mem_available_bytes` | gauge | bayt | — | `MemAvailable` | Haqiqiy mavjud xotira | F1 |
| `mem_used_bytes` | gauge | bayt | — | `MemTotal − MemAvailable` | | F1 |
| `mem_used_percent` | gauge | % | — | hisoblangan | Alert shu asosida | F1 |
| `mem_free_bytes` | gauge | bayt | — | `MemFree` | | F1 |
| `mem_cached_bytes`, `mem_buffers_bytes` | gauge | bayt | — | `Cached`, `Buffers` | | F2 |
| `swap_total_bytes`, `swap_used_bytes` | gauge | bayt | — | `SwapTotal`, `SwapTotal−SwapFree` | | F1 |
| `swap_used_percent` | gauge | % | — | hisoblangan | | F1 |
| `swap_in_pages_per_sec`, `swap_out_pages_per_sec` | gauge | sahifa/s | — | `/proc/vmstat` (`pswpin`, `pswpout`) | Faol swap = xotira bosimi | F2 |
| `oom_kill_total` | counter | son | — | `/proc/vmstat` (`oom_kill`) | Yadro xotira yetishmasligidan jarayon o'ldirganlari soni (host darajasi) | F2 |
| `procs_total`, `procs_running`, `procs_blocked` | gauge | son | — | `/proc/stat`, `/proc/loadavg` | | F2 |
| `procs_zombie` | gauge | son | — | `/proc/[pid]/stat` | | F2 |
| `threads_total` | gauge | son | — | `/proc/loadavg` | | F2 |
| `fd_allocated`, `fd_max` | gauge | son | — | `/proc/sys/fs/file-nr` | | F2 |
| `context_switches_per_sec` | gauge | 1/s | — | `/proc/stat` `ctxt` | | F3 |
| `uptime_seconds` | gauge | s | — | `/proc/uptime` | | F1 |
| `boot_time_seconds` | gauge | unix s | — | `/proc/stat` `btime` | O'zgarsa — reboot voqeasi | F1 |
| `psi_cpu_some_avg10`, `psi_memory_some_avg10`, `psi_io_some_avg10` | gauge | % | — | `/proc/pressure/*` | Resurs bosimi (agar yadro qo'llasa) | F3 |
| `clock_offset_seconds` | gauge | s | — | `chronyc tracking` yoki `timedatectl timesync-status` | Mavjud bo'lsa | F2 |
| `ntp_synchronized` | gauge | 0/1 | — | `timedatectl show -p NTPSynchronized` | | F2 |
| `top_cpu_process_percent`, `top_mem_process_bytes` | gauge | %/bayt | `name`, `rank` (1..5) | `/proc/[pid]/stat` | Faqat bajariladigan fayl nomi (argumentsiz), NFR-DAT-001 | F3 |

### 7.4.2. `disk` va `diskio` kollektorlari

| Nom | Tur | Birlik | Belgilar | Manba | Izoh | Faza |
|---|---|---|---|---|---|---|
| `fs_total_bytes` | gauge | bayt | `mount`, `device`, `fstype` | `statfs()` | `tmpfs`, `overlay`, `squashfs`, `devtmpfs`, `proc`, `sysfs`, `cgroup*` e'tiborsiz | F1 |
| `fs_used_bytes` | gauge | bayt | xuddi shunday | `statfs()` | | F1 |
| `fs_avail_bytes` | gauge | bayt | xuddi shunday | `statfs()` (`f_bavail`) | Oddiy foydalanuvchi uchun bo'sh | F1 |
| `fs_used_percent` | gauge | % | xuddi shunday | hisoblangan | `used / (used + avail)` (`df` ga mos) | F1 |
| `fs_inodes_total`, `fs_inodes_used` | gauge | son | xuddi shunday | `statfs()` | | F2 |
| `fs_inodes_used_percent` | gauge | % | xuddi shunday | hisoblangan | | F2 |
| `fs_readonly` | gauge | 0/1 | `mount`, `device` | `/proc/mounts` opsiyalari (`ro`) | **Muhim:** fayl tizimi xato tufayli faqat o'qish rejimiga o'tganini aniqlaydi | F1 |
| `disk_read_bytes_per_sec`, `disk_write_bytes_per_sec` | gauge | bayt/s | `device` | `/proc/diskstats` | Faqat jismoniy/virtual blok qurilmalar (`sd*`, `vd*`, `nvme*`); `loop*`, `ram*`, `dm-*` hisoblanmaydi | F2 |
| `disk_read_iops`, `disk_write_iops` | gauge | 1/s | `device` | `/proc/diskstats` | | F2 |
| `disk_io_util_percent` | gauge | % | `device` | `/proc/diskstats` (io_ticks) | | F2 |
| `disk_await_ms` | gauge | ms | `device` | `/proc/diskstats` | O'rtacha so'rov kutish vaqti | F2 |

### 7.4.3. `net` kollektori

| Nom | Tur | Birlik | Belgilar | Manba | Izoh | Faza |
|---|---|---|---|---|---|---|
| `net_rx_bytes_per_sec`, `net_tx_bytes_per_sec` | gauge | bayt/s | `iface` | `/proc/net/dev` | Standart: `lo`, `veth*`, `br-*`, `docker0` yashirin | F1 |
| `net_rx_packets_per_sec`, `net_tx_packets_per_sec` | gauge | 1/s | `iface` | `/proc/net/dev` | | F2 |
| `net_rx_errors_per_sec`, `net_tx_errors_per_sec` | gauge | 1/s | `iface` | `/proc/net/dev` | | F2 |
| `net_rx_drops_per_sec`, `net_tx_drops_per_sec` | gauge | 1/s | `iface` | `/proc/net/dev` | | F2 |
| `tcp_established` | gauge | son | — | `/proc/net/snmp` (`CurrEstab`) | | F2 |
| `tcp_time_wait` | gauge | son | — | `/proc/net/sockstat` (`tw`) | | F3 |
| `sockets_used` | gauge | son | — | `/proc/net/sockstat` | | F3 |
| `net_listen_ports` | gauge | son | — | `/proc/net/tcp*` | Tashqariga (`0.0.0.0`/`::`) ochiq tinglovchi portlar soni; ro'yxat `facts` da (kutilmagan ochiq port aniqlash, FR-HTTP-007) | F2 |

### 7.4.4. `docker` kollektori

Docker ma'lumoti `docker-socket-proxy` orqali (faqat GET) olinadi. Konteyner nomi `/` siz.
Kardinallik chegarasi: bitta hostda ≤ 100 konteyner kuzatiladi (oshsa — `docker_series_dropped`).

> **S5 da amalga oshirilgan (F1):** `docker_container_running`, `_restarts_total`, `_uptime_seconds`, `_health`, `_oom_killed`, `docker_containers_running/total` va `docker_container_expected` (quyida). Manzil: `tcp://127.0.0.1:2375` (proksi) yoki `unix:///var/run/docker.sock`. Konteyner holati `/containers/json?all=1`, qolgani har konteyner uchun `/containers/{id}/json` dan (≤ 100 so'rov/30 s). `health` faqat ishlayotgan konteynerda hisoblanadi (Docker to'xtagan konteynerda eski holatni saqlaydi). Resurs sarfi (`cpu_percent`, `mem_*`), `system/df` va log hajmi — **S11 da amalga oshirilgan (F2)**: `GET /containers/{id}/stats?stream=false&one-shot=true` (faqat ishlayotgan konteynerlar; `one-shot` oldingi namunani bermaydi, shuning uchun agent CPU o'lchovini xotirasida saqlab, farqdan foiz hisoblaydi), `GET /system/df` (10 daqiqada bir, 20 s timeout; katta xostda 10 s dan oshishi mumkin), `LogPath` va uning aylantirilgan nusxalari (`<id>-json.log*`) `stat` orqali. Proksi uchun `SYSTEM=1` kerak (`/system/df`); `POST` baribir `403`.
> **Kardinallik:** har konteyner ~11 qator (F1: 6, F2: 5). Core `MAX_SERIES_PER_HOST = 1000` (7.3.1), shuning uchun amalda ~70 konteynergacha. `max_containers: 100` chegarasi bilan birga qaralsin: 70 dan ortiq konteynerli xostda chegara oshirilishi yoki F2 qatorlari qisqartirilishi kerak.
> **`docker_container_expected` (0/1):** konteyner kamida 1 soat uzluksiz ishlagan va `RestartPolicy` `no` dan farqli bo'lsa 1 (11.5.1). Bu holat agent **xotirasida** saqlanadi (agent qayta ishga tushsa, qaytadan 1 soat kerak). Kutilgan konteyner ro'yxatdan yo'qolsa 10 daqiqagacha `running=0` yuboriladi, keyin ataylab olib tashlangan deb unutiladi.

| Nom | Tur | Birlik | Belgilar | Manba | Izoh | Faza |
|---|---|---|---|---|---|---|
| `docker_container_running` | gauge | 0/1 | `container`, `project`, `service` | `GET /containers/json?all=1` | `project`/`service` — `com.docker.compose.*` labellaridan | F1 |
| `docker_container_health` | gauge | kod | `container`, `project`, `service` | `State.Health.Status` | 0 — healthcheck yo'q, 1 — healthy, 2 — unhealthy, 3 — starting | F2 |
| `docker_container_restarts_total` | counter | son | `container`, `project`, `service` | `RestartCount` | | F1 |
| `docker_container_uptime_seconds` | gauge | s | `container`, … | `State.StartedAt` | | F1 |
| `docker_container_cpu_percent` | gauge | % | `container`, … | `GET /containers/{id}/stats?stream=false` | Bir yadro = 100% | F2 |
| `docker_container_mem_bytes` | gauge | bayt | `container`, … | stats (`usage` − `total_inactive_file`/`inactive_file`/`cache`) | Sahifa keshi hisobga olinmaydi (cgroup v1 va v2) | F2 |
| `docker_container_mem_limit_bytes` | gauge | bayt | `container`, … | stats (`memory_stats.limit`) | Limit xost RAM ga (`/info` `MemTotal`) teng yoki cgroup v1 "cheksiz" qiymati bo'lsa **0 = cheksiz** yuboriladi va `mem_percent` hisoblanmaydi | F2 |
| `docker_container_mem_percent` | gauge | % | `container`, … | hisoblangan | | F2 |
| `docker_container_net_rx_bytes_per_sec`, `..._tx_...` | gauge | bayt/s | `container`, … | stats | | F3 |
| `docker_container_blk_read_bytes_per_sec`, `..._write_...` | gauge | bayt/s | `container`, … | stats | | F3 |
| `docker_container_oom_killed` | gauge | 0/1 | `container`, … | `State.OOMKilled` | | F2 |
| `docker_container_log_bytes` | gauge | bayt | `container`, … | log fayli hajmi (agent o'qiy olsa) yoki `LogPath` `stat` | `/var/lib/docker/containers` ga o'qish huquqi kerak (7.8 ga qarang) | F2 |
| `docker_containers_running`, `docker_containers_total` | gauge | son | — | `GET /info` | | F1 |
| `docker_images_bytes`, `docker_containers_bytes`, `docker_volumes_bytes`, `docker_build_cache_bytes` | gauge | bayt | — | `GET /system/df` | Kuniga ko'p marta emas, 10 daqiqada bir | F2 |
| `docker_reclaimable_bytes` | gauge | bayt | — | `GET /system/df` | Tozalab qaytariladigan | F3 |
| `docker_log_limit_configured` | gauge | 0/1 | — | `GET /info` (`LoggingDriver`) + `/etc/docker/daemon.json` (o'qiy olsa) | | F3 |

### 7.4.5. `systemd` kollektori

| Nom | Tur | Birlik | Belgilar | Manba | Izoh | Faza |
|---|---|---|---|---|---|---|
| `systemd_unit_active` | gauge | 0/1 | `unit` | D-Bus (`ListUnits`) yoki `systemctl show` | Faqat sozlamadagi unit lar | F1 |
| `systemd_unit_failed` | gauge | 0/1 | `unit` | `ActiveState == failed` | | F1 |
| `systemd_unit_restarts_total` | counter | son | `unit` | `NRestarts` | | F2 |
| `systemd_unit_uptime_seconds` | gauge | s | `unit` | `ActiveEnterTimestamp` | | F2 |
| `systemd_failed_units_total` | gauge | son | — | `systemctl --failed` | | F2 |
| `nginx_config_ok` | gauge | 0/1 | — | `nginx -t` (kuniga + o'zgarishda; `sudo` kerak: 7.8) | | F3 |
| `cron_job_last_success_timestamp` | gauge | unix s | `job` | Heartbeat'lar `/var/lib/nazoratchi/heartbeats/<job>` | Cron skript oxirida `nazoratchi-agent beat <job>` chaqiradi (FR-SVC-004) | F1 |

> **S6 da amalga oshirilgan (agent):** `systemd_unit_active`, `systemd_unit_failed` (`systemctl show`, shell yo'q; unit nomi `^[A-Za-z0-9:_.@\-]{1,100}$` ga mos, aks holda sozlama xato), `cron_job_last_success_timestamp{job}` (`heartbeats_dir` fayllari `mtime`; cron skript oxirida `nazoratchi-agent beat <job>`). Yo'q unit (`LoadState=not-found`) — `active=0, failed=0`. F2 metrikalari (`restarts_total`, `uptime`, `failed_units_total`) va `nginx_config_ok` hali yo'q.

### 7.4.6. `backup` kollektori

Manba — `appctl` yozgan `state.json` (FR-INT-003) **va** papka skaneri (qo'shimcha tekshiruv).
Agent `BACKUP_ROOT` (standart `/opt/applications/backups`) ni ko'radi; ichidagi har papka —
loyiha.

| Nom | Tur | Birlik | Belgilar | Manba | Izoh | Faza |
|---|---|---|---|---|---|---|
| `backup_last_status` | gauge | 0/1 | `project` | `state.json` (`status`) | 1 — ok, 0 — fail | F1 |
| `backup_last_success_timestamp` | gauge | unix s | `project` | `state.json` (`finished_at` agar ok) | | F1 |
| `backup_last_size_bytes` | gauge | bayt | `project` | `state.json` yoki eng yangi fayl hajmi | | F1 |
| `backup_last_duration_seconds` | gauge | s | `project` | `state.json` | | F2 |
| `backup_newest_file_age_seconds` | gauge | s | `project`, `kind` = daily, weekly, files | papka skaneri (`mtime`) | `.tmp` fayllar hisobga olinmaydi | F1 |
| `backup_files_count` | gauge | son | `project`, `kind` | papka skaneri | | F1 |
| `backup_dir_bytes` | gauge | bayt | `project` | papka skaneri (`du`) | | F2 |
| `backup_gz_ok` | gauge | 0/1 | `project` | `gzip -t` (eng yangi `.sql.gz`) | Kuniga 1 marta | F2 |
| `backup_offsite_configured` | gauge | 0/1 | — | `/opt/applications/appctl.conf` (`OFFSITE` bo'sh emasmi) | FR-BKP-010 | F1 |
| `backup_offsite_last_status` | gauge | 0/1 | — | `state.json` (`offsite.status`) | | F2 |
| `backup_offsite_last_success_timestamp` | gauge | unix s | — | `state.json` (`offsite.finished_at`) | | F2 |
| `backup_root_free_bytes` | gauge | bayt | — | `statfs(BACKUP_ROOT)` | Zaxira bo'limidagi bo'sh joy | F2 |

> **S6 da amalga oshirilgan (F1 metrikalari):** `backup_last_status`, `backup_last_success_timestamp`, `backup_last_size_bytes`, `backup_newest_file_age_seconds{kind}`, `backup_files_count{kind}`, `backup_offsite_configured`. Loyiha papkasi nomi `^[A-Za-z0-9_\-]{1,60}$`, `_` bilan boshlanganlari loyiha emas, ≤ 100 loyiha. `*.tmp` va yashirin fayllar, simvolik havolalar hisobga olinmaydi. `kind`: `daily/` — `daily`; `weekly/` da nomida `-files-` bo'lsa `files`, aks holda `weekly`. `backup_last_success_timestamp`: `state.json` `ok` bo'lsa `finished_at`, aks holda eng yangi kunlik fayl `mtime`. `state.json` yo'q bo'lsa (appctl hali yozmagan) xato emas — faqat skaner metrikalari chiqadi; buzuq bo'lsa kollektor xatosi (qolgan loyihalar davom etadi). `error` matni hech qachon metrikaga tushmaydi. `backup_offsite_configured`: avval `_run.json` `offsite.configured`, bo'lmasa `appctl.conf` dagi `OFFSITE=` (matn sifatida o'qiladi, `source` qilinmaydi). `backup_gz_ok`, `backup_dir_bytes`, `backup_root_free_bytes`, `backup_offsite_last_*` — F2.

Offsite zaxira S-00 da turadi; u yerdagi agent bir xil kollektor bilan, lekin `BACKUP_ROOT=/srv/backups/main-server`
ko'rsatkichi bilan ishlaydi; core mahalliy va offsite natijalarni loyiha nomi bo'yicha solishtiradi
(FR-BKP-012).

### 7.4.7. `certs` kollektori

| Nom | Tur | Birlik | Belgilar | Manba | Izoh | Faza |
|---|---|---|---|---|---|---|
| `cert_not_after_timestamp` | gauge | unix s | `name` (papka nomi) | `/etc/letsencrypt/live/*/cert.pem` + sozlamadagi qo'shimcha yo'llar yoki `certs.json` (deploy-hook) | **S11 da amalga oshirilgan.** `path` belgisi yuborilmaydi: core ruxsat etilgan belgilar ro'yxatida yo'q (7.3.1) va fayl yo'lini panelga chiqarish ortiqcha. Bir xil nomli ikkinchi fayl `-2` qo'shimchasi bilan keladi. Bevosita o'qish `certs.json` dan ustun. Ikkalasida ham o'qib bo'lmasa — `agent_collector_errors{collector=certs}` | F2 |
| `cert_days_left` | gauge | kun | `name` | hisoblangan | | F2 |
| `certbot_last_renew_status` | gauge | 0/1 | — | `/var/log/letsencrypt/letsencrypt.log` oxirgi `renew` natijasi | | F3 |
| `certbot_last_renew_timestamp` | gauge | unix s | — | xuddi shu | | F3 |

### 7.4.8. `ssh`, `apt` va `reboot` kollektorlari

> **S11 da amalga oshirilgan (F2):** `reboot_required*` va `kernel_reboot_pending` alohida **`reboot`** kollektorida (5 daqiqa): `apt` ning standart intervali 24 soat, reboot yoshi va yangi kernel uchun juda sekin. `kernel_reboot_pending` — `uname -r` (`/proc/sys/kernel/osrelease`) va `/boot/vmlinuz-*` ning eng yuqori versiyasi solishtiriladi; ikkalasidan biri noma'lum bo'lsa 0 (noto'g'ri signal bermaslik uchun).

| Nom | Tur | Birlik | Belgilar | Manba | Izoh | Faza |
|---|---|---|---|---|---|---|
| `ssh_failed_logins_1h` | gauge | son | — | `journalctl -u ssh --since -1h` (`Failed password`, `Invalid user`) | IP/foydalanuvchi nomi **yuborilmaydi**, faqat son | F3 |
| `ssh_failed_unique_ips_1h` | gauge | son | — | xuddi shu | | F3 |
| `ssh_accepted_logins_1h` | gauge | son | — | `Accepted ...` | Kutilmagan kirishni sezish uchun | F3 |
| `fail2ban_banned_ips` | gauge | son | `jail` | `fail2ban-client status sshd` | Mavjud bo'lsa | F3 |
| `apt_upgradable_total`, `apt_security_upgradable_total` | gauge | son | — | `apt-get -s upgrade` | Kuniga 1 marta | F3 |
| `reboot_required` | gauge | 0/1 | — | `/var/run/reboot-required` | | F2 |
| `kernel_reboot_pending` | gauge | 0/1 | — | ishlayotgan kernel ≠ o'rnatilgan eng yangi kernel | FR-HST-009 | F2 |
| `reboot_required_age_seconds` | gauge | s | — | `/var/run/reboot-required` mtime | | F2 |

### 7.4.9. Agent o'zining metrikalari

| Nom | Tur | Birlik | Belgilar | Izoh |
|---|---|---|---|---|
| `agent_up` | gauge | 1 | — | Har paketda 1 (heartbeat) |
| `agent_version_info` | gauge | 1 | `version`, `go` | Versiya belgi sifatida |
| `agent_collector_errors` | counter | son | `collector` | Kollektor xatolari |
| `agent_collect_duration_seconds` | gauge | s | `collector` | Yig'ish vaqti |
| `agent_queue_files`, `agent_queue_bytes` | gauge | son/bayt | — | Yuborilmagan navbat |
| `agent_send_failures_total` | counter | son | — | Yuborish xatolari |
| `agent_series_dropped` | counter | son | — | Kardinallik chegarasidan tashlangan |
| `agent_clock_skew_seconds` | gauge | s | — | Core javobidagi `server_time` bilan farq (musbat = core oldinda; tarmoq kechikishi ~0,1 s xatolik beradi). **S11 (FR-AGT-012):** \|farq\| > 5 s bo'lsa agent logga ogohlantirish yozadi (10 daqiqada bir marta, tuzalganda xabar), panel server sahifasida "Soat siljigan" belgisini ko'rsatadi. `chrony`/`timesyncd` holati (FR-HST-013) hali yo'q |
| `agent_update_rejected_total` | counter | son | — | Imzo/xesh/versiya tekshiruvidan o'tmagan yangilanishlar (14.5.4 `agent_update_rejected`). Alohida hodisa kanali yo'q, shuning uchun hisoblagich sifatida; alert F2 (S13/S14) |
| `agent_rss_bytes`, `agent_cpu_percent` | gauge | bayt/% | — | Agentning o'z resurs sarfi |

### 7.4.10. Faktlar (`facts`) — kam o'zgaradigan ma'lumot

Metrika emas; JSON obyekt. O'zgarganda core voqea (`host_fact_changed`) yozadi.

| Kalit | Misol | Manba |
|---|---|---|
| `hostname` | `vmi3679093` | `os.Hostname()` |
| `os` | `Ubuntu 24.04.3 LTS` | `/etc/os-release` |
| `kernel_running` | `6.8.0-139-generic` | `uname -r` |
| `kernel_latest_installed` | `6.8.0-147-generic` | `/boot/vmlinuz-*` (eng yuqori versiya) |
| `arch` | `amd64` | `runtime.GOARCH` |
| `agent_build_time` | `2026-11-01T10:00:00+00:00` | `-ldflags -X main.buildTime` (reliz commit vaqti; dev build'da yo'q). **S11 (FR-AGT-011)** |
| `go_version` | `go1.26.10` | `runtime.Version()`. **S11 (FR-AGT-011)** |
| `cpu_model`, `cpu_count` | `AMD EPYC ...`, `4` | `/proc/cpuinfo` |
| `mem_total_bytes` | `8321499136` | `/proc/meminfo` |
| `boot_id` | UUID | `/proc/sys/kernel/random/boot_id` |
| `ips` | `["164.68.105.194"]` | interfeyslar (ommaviy IP larni, `lo`/docker siz) |
| `timezone` | `Etc/UTC` | `timedatectl` |
| `docker` | `{"version":"28.x","compose":"2.x","log_driver":"json-file"}` | Docker API |
| `listen_ports` | `[22,80,443]` | `/proc/net/tcp*` (tashqariga ochiqlari) |
| `systemd_failed` | `[]` | `systemctl --failed` |
| `nginx_domains` | `["avlo.ai","nazar.avlo.ai"]` | `nginx -T` dan `server_name` (reyestr bilan solishtirish uchun, F3) |

## 7.5. Agent ↔ core protokoli (v1)

### 7.5.1. Enroll (bir martalik token → doimiy token)

```
POST /ingest/v1/enroll
Content-Type: application/json

{
  "enroll_token": "enr_********",
  "hostname": "vmi3679093",
  "agent_version": "1.0.0",
  "facts": { "os": "Ubuntu 24.04.3 LTS", "arch": "amd64", "cpu_count": 4, "mem_total_bytes": 8321499136 }
}
```

Javob (`200`):

```
{
  "host_id": "0193c0de-7a4e-7b3a-9d41-2f6c8e5a1b90",
  "agent_token": "agt_********",
  "interval_seconds": 15,
  "server_time": "2026-10-22T09:35:00Z"
}
```

Xatolar: `401 invalid_enroll_token`, `410 enroll_token_expired`, `409 host_already_enrolled`.
Xato tanasi umumiy formatda (`{"error": {"code":..., "message":..., "request_id":...}}`, 9.1.1). Doimiy token agent tomonida
`0600` rejimli faylda saqlanadi (enroll token bir martalik, qayta ishga tushganda yana kerak bo'lmasligi uchun);
prototip agent: `--enroll-token` + `--token-file`. IP bo'yicha chegara: 10 so'rov/soat (14.7.3).

### 7.5.2. Metrika yuborish

> Quyidagi namunadagi `//` izohlar faqat tushuntirish uchun; haqiqiy JSON da izoh bo'lmaydi.
> `sent_at` majburiy va **har yuborishda yangilanadi** (qayta urinishda ham): core agent soati siljishini
> shundan aniqlaydi (6.10). `batch_id` esa qayta urinishda o'zgarmaydi.

```
POST /ingest/v1/metrics
Authorization: Bearer agt_********
Content-Type: application/json
Content-Encoding: gzip
X-Nazoratchi-Agent: nazoratchi-agent/1.0.0

{
  "batch_id": "b-5f3c2a90",          // takrorlanmasin, idempotentlik kaliti
  "seq": 128443,                     // monoton oshuvchi
  "sent_at": "2026-10-22T09:35:15.120Z",
  "samples": [
    {"n": "cpu_busy_percent",        "t": 1761125700000, "v": 12.4},
    {"n": "mem_used_percent",        "t": 1761125700000, "v": 41.8},
    {"n": "fs_used_percent",         "t": 1761125700000, "v": 23.1, "l": {"mount": "/", "device": "/dev/sda1", "fstype": "ext4"}},
    {"n": "docker_container_running","t": 1761125700000, "v": 1,    "l": {"container": "nazar-web-1", "project": "nazar", "service": "web"}}
  ],
  "facts": { "kernel_running": "6.8.0-139-generic", "kernel_latest_installed": "6.8.0-147-generic" },
  "events": [
    {"type": "cron_beat", "job": "appctl-backup", "t": 1761125700000, "ok": true}
  ]
}
```

Javob (`200`):

```
{
  "ok": true,
  "accepted": 4,
  "duplicate": false,
  "server_time": "2026-10-22T09:35:15.200Z",
  "interval_seconds": 15,
  "commands": [ {"type": "set_interval", "collector": "docker", "seconds": 60} ]
}
```

Xatolar:

| Kod | Ma'nosi | Agent harakati |
|---|---|---|
| 400 | Sxema/qiymat xato | Paket tashlab yuboriladi (navbatda qolmaydi), `agent_send_failures_total` oshadi, logga yoziladi |
| 401 | Token noto'g'ri/bekor qilingan | 5 daqiqa kutib qayta urinadi; 10 marta ketma-ket 401 → logga "token bekor qilingan", yig'ishda davom etadi (navbatni to'ldiradi) |
| 413 | Paket juda katta (> 1 MB) | Paket bo'laklanadi |
| 429 | Tezlik chegarasi | `Retry-After` kutiladi |
| 5xx / tarmoq | Core muammosi | Navbatga qoladi, eksponensial kutish |

### 7.5.3. Core buyruqlari (cheklangan to'plam)

| Buyruq | Ta'siri |
|---|---|
| `set_interval` | Kollektor intervalini o'zgartirish (5–600 s) |
| `reload_config` | Sozlamani qayta yuklash |
| `update` | Yangi versiyaga yangilanish (7.7) |
| `collect_now` | Bir martalik zudlik bilan yig'ish (diagnostika) |

Boshqa hech qanday buyruq yo'q. Agent noma'lum buyruqni e'tiborsiz qoldiradi va logga yozadi.

> **Holat (S11):** agent faqat **`update`** ni bajaradi (7.7.3). `set_interval`, `reload_config` va `collect_now` hali
> bajarilmaydi, faqat logga yoziladi (sozlamani qayta o'qish `SIGHUP` bilan ishlaydi).

## 7.6. Sozlama fayli

`/etc/nazoratchi/agent.yaml` (egasi `root:nazoratchi`, rejim `0640`; token alohida `/etc/nazoratchi/token`, rejim `0600`, egasi `nazoratchi`):

```yaml
core:
  url: https://nazoratchi.example.uz        # ommaviy manzil
  ca_file: ""                            # ixtiyoriy: o'zi imzolagan CA
  timeout: 10s
host:
  name: ""                               # bo'sh bo'lsa hostname
collectors:
  system:  { enabled: true,  interval: 15s }
  disk:    { enabled: true,  interval: 30s, ignore_fstypes: [tmpfs, overlay, squashfs, devtmpfs] }
  diskio:  { enabled: true,  interval: 15s }
  reboot:  { enabled: true,  interval: 5m }
  net:     { enabled: true,  interval: 15s, ignore_ifaces: ["lo", "veth*", "br-*", "docker0"] }
  docker:
    enabled: true
    interval: 30s
    endpoint: tcp://127.0.0.1:2375       # docker-socket-proxy
    max_containers: 100
  systemd:
    enabled: true
    interval: 30s
    units: [nginx, docker, cron, ssh, avlo-contact]
  backup:
    enabled: true
    interval: 300s
    root: /opt/applications/backups
    appctl_conf: /opt/applications/appctl.conf
  certs:
    enabled: true
    interval: 6h
    globs: ["/etc/letsencrypt/live/*/cert.pem"]
    state_file: /var/lib/nazoratchi/certs.json   # certbot deploy-hook yozadi
  ssh:     { enabled: true, interval: 5m }
  apt:     { enabled: true, interval: 24h }
queue:
  dir: /var/lib/nazoratchi/queue
  max_bytes: 20971520
  max_age: 15m
log:
  level: info
```

## 7.7. O'rnatish, yangilash, o'chirish

### 7.7.1. O'rnatish skripti (`install.sh`) bosqichlari

1. `root` ekanini, `systemd`, `curl`, `sha256sum`, `minisign` borligini tekshiradi.
2. Arxitekturani (`uname -m`) aniqlaydi → `amd64` yoki `arm64`.
3. `https://<core>/agent/v1/nazoratchi-agent-<arch>` va `SHA256SUMS`, `SHA256SUMS.minisig` ni yuklaydi.
4. **Imzoni tekshiradi** (`minisign` ochiq kaliti skript ichiga joylangan); mos kelmasa to'xtaydi.
5. `/usr/local/bin/nazoratchi-agent` ga o'rnatadi (rejim `0755`).
6. `nazoratchi` tizim foydalanuvchisini yaratadi (`--system --no-create-home --shell /usr/sbin/nologin`),
   `adm`, `systemd-journal` guruhlariga qo'shadi.
7. Docker mavjud bo'lsa `docker-socket-proxy` konteynerini (`127.0.0.1:2375`; `CONTAINERS=1 INFO=1 SYSTEM=1 POST=0`) ko'taradi. Proksi allaqachon mavjud bo'lsa **o'zgartirilmaydi**: S11 dan oldin o'rnatilgan xostlarda `SYSTEM=1` yo'q, `docker system df` uchun proksini qayta yaratish kerak (`docker rm -f nazoratchi-docker-proxy` va `install.sh` ni qayta ishga tushirish).
7b. `/etc/letsencrypt` mavjud bo'lsa certbot deploy-hook'ini (`renewal-hooks/deploy/nazoratchi-certs.sh`) o'rnatadi va bir marta ishga tushiradi.
8. `/etc/nazoratchi/agent.yaml` ni yaratadi (mavjud bo'lsa **o'zgartirmaydi**).
9. Enroll qiladi (`--token`) → doimiy tokenni `/etc/nazoratchi/token` ga yozadi.
10. `/etc/systemd/system/nazoratchi-agent.service` ni yozadi, `daemon-reload`, `enable --now`.
11. 30 soniya kutib, birinchi paket yuborilganini tekshiradi va natijani chop etadi
    ("Nazoratchi'ga ulandi: <host_name>").

Skript idempotent: qayta ishga tushirilsa, mavjud sozlama va tokenni saqlab, binarni yangilaydi.

> **S7:** `deploy/agent/install.sh`, Debian konteynerida sinalgan (`bash deploy/agent/test.sh`): imzo/SHA-256 rad etish, idempotentlik, enroll. Agent birinchi muvaffaqiyatli paketni `paket yuborildi (birinchi)` deb Info darajasida yozadi (skript 30 s shuni kutadi). `ReadOnlyPaths` yo'llari `-` prefiksli (papka yo'q bo'lsa unit yiqilmaydi). `uninstall` core'ga `goodbye` yuboradi.

### 7.7.2. systemd unit

```ini
[Unit]
Description=Nazoratchi monitoring agent
After=network-online.target docker.service
Wants=network-online.target

[Service]
User=nazoratchi
Group=nazoratchi
SupplementaryGroups=adm systemd-journal
ExecStartPre=+/usr/local/lib/nazoratchi/agent-prestart.sh   # 7.7.3: yangilanishni almashtirish/rollback (root)
ExecStart=/usr/local/bin/nazoratchi-agent run --config /etc/nazoratchi/agent.yaml
Restart=always
RestartSec=5
MemoryMax=100M
CPUQuota=20%
# Qattiqlashtirish
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
ReadWritePaths=/var/lib/nazoratchi
ReadOnlyPaths=/opt/applications/backups /etc/letsencrypt
CapabilityBoundingSet=
LockPersonality=true

[Install]
WantedBy=multi-user.target
```

> Eslatma: `/etc/letsencrypt/live` odatda `root` uchun yopiq (`0700`). Sertifikat muddatini
> o'qish uchun agent `cert.pem` (ommaviy, maxfiy emas) ni o'qishi kerak, lekin `privkey.pem`
> ni **hech qachon**. Yechim: `setfacl -m u:nazoratchi:rx /etc/letsencrypt/{live,archive}` va
> `privkey*.pem` ga `setfacl` **qo'llanmaydi**; yoki root'da ishlaydigan kichik `certbot` ilgagi
> (`--deploy-hook`) muddatlarni `/var/lib/nazoratchi/certs.json` ga yozadi. Ikkinchisi tavsiya etiladi va **S11 da amalga oshirilgan**: `install.sh` hook'ni o'rnatadi; hook faqat ommaviy `cert.pem` muddatini `openssl x509 -enddate` bilan o'qiydi (`privkey*.pem` ga tegmaydi) va `/var/lib/nazoratchi/certs.json` ga `{"certs":[{"name":..., "not_after":<unix s>}]}` yozadi (atomik, rejim `0640`, guruh `nazoratchi`). Agent yaroqsiz nomlarni (`[A-Za-z0-9._-]{1,200}` ga mos kelmaganni) va 200 dan ortiq yozuvni tashlaydi.

### 7.7.3. O'z-o'zini yangilash

> **S11 da amalga oshirilgan (F2, FR-AGT-008).** Agent root emas va `ProtectSystem=strict` tufayli `/usr/local/bin` ga
> yoza olmaydi, shuning uchun yangilanish **ikki bosqichli** (avvalgi "agent o'zi almashtiradi" sxemasi o'rniga).

1. Owner panelda (yoki `POST /servers/{id}/agent-update`, 9.3) yangilashni so'raydi. Core `VERSION` (tarqatish papkasi)
   dan nishon versiyani oladi va host unga yetguncha **har ingest javobiga** buyruq qo'shadi:
   `{"type":"update","version":"1.1.0","sha256":"...","url":"/agent/v1/nazoratchi-agent-amd64"}`.
   Bu buyruq faqat **maslahat**: agent `url` va `sha256` ga ishonmaydi.
2. **Stage (agent, `nazoratchi` foydalanuvchisi).** Manzil faqat `core.url` + qat'iy fayl nomlaridan quriladi (`VERSION`,
   `SHA256SUMS`, `SHA256SUMS.minisig`, `nazoratchi-agent-<arch>`; yo'naltirishga ergashilmaydi). Agent: (a) `SHA256SUMS`
   imzosini binarga joylangan minisign ochiq kaliti bilan tekshiradi (`Ed` va `ED`/BLAKE2b, global imzo ham); (b) `VERSION`
   va binar xeshini **imzolangan** ro'yxat bilan solishtiradi; (c) versiya hozirgidan **qat'iy katta** ekanini tekshiradi;
   (d) core e'lon qilgan versiya/xesh imzolanganiga mosligini tekshiradi. Faqat shundan keyin `/var/lib/nazoratchi/update/`
   ga yozadi (oxirida `staged` belgisi) va toza chiqadi (`exit 0`); systemd `Restart=always` bilan qayta ishga tushiradi.
   Tekshiruvdan o'tmasa: `agent_update_rejected_total` oshadi, sabab logga yoziladi, agent eski binar bilan ishlaydi.
   Buyruq takrorlansa ham 5 daqiqada bir marta qayta ishlanadi.
3. **Apply (root).** Unit: `ExecStartPre=+/usr/local/lib/nazoratchi/agent-prestart.sh` -> `nazoratchi-agent apply-update`
   (o'rnatilgan, root-egalik, ishonchli binar). U staged to'plamni **noldan qayta tekshiradi** (agent yozgan hech narsaga
   ishonilmaydi: buzilgan agent rootda ixtiyoriy binar o'rnata olmasligi shart), fayllarni `O_NOFOLLOW` bilan bir
   marta xotiraga o'qiydi (TOCTOU yo'q), joriy binarni `.old` ga saqlaydi, `pending.json` yozadi va binarni atomik
   (`rename`) almashtiradi. Holat papkasi `/var/lib/nazoratchi-update/` faqat root yozadi; hamma yoza oladigan bo'lsa
   rad etiladi.
4. **Tasdiq va rollback.** Yangi agent core'ga birinchi paketni yuborgach `update/confirmed` ga o'z versiyasini yozadi.
   Keyingi ishga tushishda `apply-update`: tasdiq bor -> `pending` o'chiriladi; tasdiq yo'q va **10 daqiqa ichida**
   qayta ishga tushgan bo'lsa -> `.old` qaytariladi va `rolled_back.json` yoziladi (shu versiya qayta urinilmaydi, undan
   yangi reliz kutiladi); 10 daqiqadan keyingi tasdiqsiz qayta ishga tushish (masalan, core uzoq vaqt o'chiq bo'lib, host
   reboot bo'lgan) oddiy deb hisoblanadi. Yangi binar `apply-update` ni ham ishga tushira olmasa, o'rov skripti
   (`agent-prestart.sh`) kutilayotgan `pending` bo'lganda `.old` ni o'zi qaytaradi.
5. Core ingest'da `X-Nazoratchi-Agent` versiyasi o'zgarganini ko'radi: `agent_updated` (yoki rollbackda
   `agent_downgraded`) voqeasi yoziladi va nishonga yetgan so'rov yopiladi.

Cheklovlar: reliz versiyasi `X.Y.Z` bo'lishi shart (pre-reliz va `dev` yangilanmaydi); S11 dan oldin o'rnatilgan
xostlarda o'rov skripti va unit yo'q, shuning uchun **bir marta `install.sh` ni qayta ishga tushirish** kerak.

### 7.7.4. O'chirish

`nazoratchi-agent uninstall`: servisni to'xtatadi va o'chiradi, binar va unit faylini o'chiradi,
`/etc/nazoratchi` va `/var/lib/nazoratchi` ni o'chiradi (`--keep-config` bilan saqlash mumkin),
`nazoratchi` foydalanuvchisini o'chiradi, core'ga `POST /ingest/v1/goodbye` yuboradi (host "arxiv").

## 7.8. Ruxsatlar va xavfsizlik chegaralari (agent)

| Nimaga kirish kerak | Qanday | Nima uchun xavfsiz |
|---|---|---|
| `/proc`, `/sys` | Oddiy foydalanuvchi o'qiy oladi | Tizim statistikasi |
| `journalctl` (SSH loglari) | `systemd-journal` guruhi | Faqat o'qish |
| Docker ma'lumoti | `docker-socket-proxy` (`127.0.0.1:2375`, `CONTAINERS`, `INFO`, `SYSTEM`; `POST` yopiq) | Agent konteyner yarata/to'xtata olmaydi |
| Docker log hajmi | `/var/lib/docker/containers` — `root` uchun; yechim: Docker API `LogPath` + `stat` o'rniga `docker system df`/`inspect` dan hajm; zarur bo'lsa `setfacl -m u:nazoratchi:rx` papka darajasida (**fayl mazmuni emas**, faqat `stat`) | Mazmunni o'qimaydi |
| Zaxira papkasi | `ReadOnlyPaths` + `setfacl -R -m u:nazoratchi:rX /opt/applications/backups` | Faqat nomlari/hajmi/`gzip -t` (o'qish) |
| `appctl.conf` | O'qish (`OFFSITE` bo'sh emasmi) | Faqat bitta bayroq yuboriladi, qiymati (host/manzil) emas |
| `nginx -t` | Kam huquqli `sudo` qoidasi yoki root ilgagi natijani faylga yozadi | Agent `sudo` olmaydi; faqat natija faylini o'qiydi |
| Tarmoq | Faqat chiquvchi 443 core'ga | Kiruvchi port yo'q |

## 7.9. Agent sifat mezonlari va testlari

| Test | Tavsifi |
|---|---|
| Birlik testlari | Har kollektor uchun `/proc` namunalari (fixtures) bilan; qiymatlar `top`, `free`, `df` bilan solishtiriladi |
| Moslik testi | Ubuntu 22.04 va 24.04, amd64 va arm64 (Docker + QEMU) |
| Yuklama testi | 15 s intervalda 24 soat; CPU/RAM chegarasi (NFR-PRF-007) |
| Xato testlari | Core o'chirilgan, DNS ishlamaydi, sekin tarmoq, 401/429/500 javoblari, disk to'lgan |
| Xavfsizlik | `gosec`, `govulncheck`; token loglarda yo'qligi; imzo tekshiruvi |
| Yangilash | Normal va buzuq binar bilan rollback |

## 7.10. Versiyalash va chiqarish

- Semantik versiya (`MAJOR.MINOR.PATCH`). Core `MAJOR` bir xil bo'lgan agentlarni qabul qiladi.
- Chiqarish artefaktlari: `nazoratchi-agent-linux-amd64`, `-arm64`, `SHA256SUMS`, `SHA256SUMS.minisig`,
  `install.sh`. CI da `goreleaser`; core o'z ichida bu fayllarni `/agent/v1/` orqali tarqatadi.
- Imzo kaliti (`minisign` maxfiy kaliti) CI sirlarida; ochiq kalit `install.sh` ichida.
