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

| Nom | Tur | Birlik | Belgilar | Manba | Izoh | Faza |
|---|---|---|---|---|---|---|
| `docker_container_running` | gauge | 0/1 | `container`, `project`, `service` | `GET /containers/json?all=1` | `project`/`service` — `com.docker.compose.*` labellaridan | F1 |
| `docker_container_health` | gauge | kod | `container`, `project`, `service` | `State.Health.Status` | 0 — healthcheck yo'q, 1 — healthy, 2 — unhealthy, 3 — starting | F2 |
| `docker_container_restarts_total` | counter | son | `container`, `project`, `service` | `RestartCount` | | F1 |
| `docker_container_uptime_seconds` | gauge | s | `container`, … | `State.StartedAt` | | F1 |
| `docker_container_cpu_percent` | gauge | % | `container`, … | `GET /containers/{id}/stats?stream=false` | Bir yadro = 100% | F2 |
| `docker_container_mem_bytes` | gauge | bayt | `container`, … | stats (`memory_stats.usage − cache`) | | F2 |
| `docker_container_mem_limit_bytes` | gauge | bayt | `container`, … | stats (`memory_stats.limit`) | Limit xost RAM ga teng bo'lsa — "cheksiz" deb belgilanadi | F2 |
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

Offsite zaxira S-00 da turadi; u yerdagi agent bir xil kollektor bilan, lekin `BACKUP_ROOT=/srv/backups/main-server`
ko'rsatkichi bilan ishlaydi; core mahalliy va offsite natijalarni loyiha nomi bo'yicha solishtiradi
(FR-BKP-012).

### 7.4.7. `certs` kollektori

| Nom | Tur | Birlik | Belgilar | Manba | Izoh | Faza |
|---|---|---|---|---|---|---|
| `cert_not_after_timestamp` | gauge | unix s | `name` (papka nomi), `path` | `/etc/letsencrypt/live/*/cert.pem` + sozlamadagi qo'shimcha yo'llar | Faylni agent o'qiy olishi kerak (7.8) | F2 |
| `cert_days_left` | gauge | kun | `name` | hisoblangan | | F2 |
| `certbot_last_renew_status` | gauge | 0/1 | — | `/var/log/letsencrypt/letsencrypt.log` oxirgi `renew` natijasi | | F3 |
| `certbot_last_renew_timestamp` | gauge | unix s | — | xuddi shu | | F3 |

### 7.4.8. `ssh` va `apt` kollektorlari

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
| `agent_clock_skew_seconds` | gauge | s | — | Core javobidagi vaqt bilan farq |
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

1. `root` ekanini, `systemd`, `curl`, `sha256sum` borligini tekshiradi.
2. Arxitekturani (`uname -m`) aniqlaydi → `amd64` yoki `arm64`.
3. `https://<core>/agent/v1/nazoratchi-agent-<arch>` va `SHA256SUMS`, `SHA256SUMS.sig` ni yuklaydi.
4. **Imzoni tekshiradi** (`minisign` ochiq kaliti skript ichiga joylangan); mos kelmasa to'xtaydi.
5. `/usr/local/bin/nazoratchi-agent` ga o'rnatadi (rejim `0755`).
6. `nazoratchi` tizim foydalanuvchisini yaratadi (`--system --no-create-home --shell /usr/sbin/nologin`),
   `adm`, `systemd-journal` guruhlariga qo'shadi.
7. Docker mavjud bo'lsa `docker-socket-proxy` konteynerini (`127.0.0.1:2375`) ko'taradi.
8. `/etc/nazoratchi/agent.yaml` ni yaratadi (mavjud bo'lsa **o'zgartirmaydi**).
9. Enroll qiladi (`--token`) → doimiy tokenni `/etc/nazoratchi/token` ga yozadi.
10. `/etc/systemd/system/nazoratchi-agent.service` ni yozadi, `daemon-reload`, `enable --now`.
11. 30 soniya kutib, birinchi paket yuborilganini tekshiradi va natijani chop etadi
    ("Nazoratchi'ga ulandi: <host_name>").

Skript idempotent: qayta ishga tushirilsa, mavjud sozlama va tokenni saqlab, binarni yangilaydi.

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
> (`--deploy-hook`) muddatlarni `/var/lib/nazoratchi/certs.json` ga yozadi. Ikkinchisi tavsiya etiladi.

### 7.7.3. O'z-o'zini yangilash

1. Core javobida `update` buyrug'i: `{"type":"update","version":"1.1.0","sha256":"...","url":"/agent/v1/..."}`.
2. Agent faylni yuklaydi, SHA-256 va imzoni tekshiradi.
3. Yangi binarni `/usr/local/bin/nazoratchi-agent.new` ga yozadi, joriyni `.old` ga nusxalaydi,
   `rename` bilan almashtiradi va `systemd` orqali qayta ishga tushadi (`exit 0` + `Restart=always`).
4. 60 soniyada yangi agent birinchi muvaffaqiyatli paketni yubormasa, `ExecStopPost` skripti
   `.old` ni qaytaradi (rollback).
5. Core versiyani qayd etadi; panelda "yangilandi" voqeasi.

### 7.7.4. O'chirish

`nazoratchi-agent uninstall`: servisni to'xtatadi va o'chiradi, binar va unit faylini o'chiradi,
`/etc/nazoratchi` va `/var/lib/nazoratchi` ni o'chiradi (`--keep-config` bilan saqlash mumkin),
`nazoratchi` foydalanuvchisini o'chiradi, core'ga `POST /ingest/v1/goodbye` yuboradi (host "arxiv").

## 7.8. Ruxsatlar va xavfsizlik chegaralari (agent)

| Nimaga kirish kerak | Qanday | Nima uchun xavfsiz |
|---|---|---|
| `/proc`, `/sys` | Oddiy foydalanuvchi o'qiy oladi | Tizim statistikasi |
| `journalctl` (SSH loglari) | `systemd-journal` guruhi | Faqat o'qish |
| Docker ma'lumoti | `docker-socket-proxy` (`127.0.0.1:2375`, GET faqat) | Agent konteyner yarata/to'xtata olmaydi |
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
