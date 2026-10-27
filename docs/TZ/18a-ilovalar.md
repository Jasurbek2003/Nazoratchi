# 18. Ilovalar

## 18.1. `appctl --json` chiqish sxemalari

Mavjud `appctl` ga `list --json` va `status --json` qo'shiladi (FR-INT-001, FR-INT-002).
Qoidalar: faqat stdout'ga JSON (diagnostika stderr'ga); bir qator yoki chiroyli — farqi yo'q;
parol/token **hech qachon**; chiqish kodi 0 (muvaffaqiyat); xatoda `{"schema":1,"error":"..."}` va kod 1.

### 18.1.1. `appctl list --json`

```json
{
  "schema": 1,
  "host": "vmi3679093",
  "generated_at": "2026-10-22T09:35:00Z",
  "projects": [
    {
      "name": "Nazar",
      "compose_file": "docker-compose.prod.yml",
      "compose_extra": null,
      "state": "running",
      "running": 7,
      "total": 7,
      "health_url": "http://127.0.0.1:8020/healthz/",
      "db": {"service": "db", "user": "nazar", "name": "nazar"},
      "backup_paths": []
    },
    {
      "name": "lutfan_ai",
      "compose_file": "docker-compose.yml",
      "compose_extra": "docker-compose.server.yml",
      "state": "partial",
      "running": 5,
      "total": 6,
      "health_url": null,
      "db": {"service": "postgres", "user": "lutfan", "name": "lutfan"},
      "backup_paths": ["/var/lib/docker/volumes/lutfan_ai_media/_data"]
    }
  ]
}
```

`state`: `running` (hammasi ishlayapti) | `partial` (bir qismi ishlayapti) | `stopped` (hech biri ishlamayapti,
shu jumladan konteyner yo'q) | `unknown` (Docker javob bermadi; agent buni "to'xtagan" deb hisoblamasligi shart).
Inson rejimidagi `appctl list` 0/N ni "qisman" deb ko'rsatadi; JSON da ogohlantirish mantig'i uchun farqlanadi.
`db` — `.appctl` da `DB_SERVICE` bo'lmasa `null`. `health_url` dagi maxfiy qismlar (`token=…`) `***` bilan yopiladi;
`HEALTH_CURL_OPTS` (sarlavhalar) chiqarilmaydi. `backup_paths` — `BACKUP_PATHS` bo'yicha massiv.

### 18.1.2. `appctl status --json`

```json
{
  "schema": 1,
  "host": "vmi3679093",
  "generated_at": "2026-10-22T09:35:00Z",
  "disk": {"mount": "/", "total_bytes": 85899345920, "used_bytes": 66993537024, "used_percent": 78},
  "memory": {"total_bytes": 8321499136, "used_bytes": 3478923264, "available_bytes": 4842575872},
  "containers": [
    {"name": "nazar-web-1", "status": "Up 2 days", "running": true, "health": "healthy"},
    {"name": "nazar-db-1", "status": "Up 4 days", "running": true, "health": null}
  ],
  "certificates": [
    {"name": "nazar.avlo.ai", "not_after": "2026-12-02T04:11:00Z", "days_left": 41},
    {"name": "avlo.ai", "not_after": "2026-12-05T08:20:00Z", "days_left": 44}
  ],
  "backups": [
    {"project": "BiznesRadar", "last_daily_at": "2026-10-22T03:15:41Z", "daily_count": 7, "weekly_count": 5}
  ]
}
```

Status JSON qoidalari (E-02 da amalga oshirilgan va sinalgan):

- `memory.used_bytes = total_bytes − available_bytes` (`free -b`); `disk` — `df -P -B1 /` (ustunlar oxiridan o'qiladi:
  fayl tizimi nomida bo'shliq bo'lishi mumkin).
- `containers` — `docker ps -a`: to'xtaganlar ham kiradi (`running: false`). `health`: `healthy` | `unhealthy` |
  `starting` | `null` (healthcheck yo'q).
- `disk`, `memory`, `containers` olib bo'lmasa `null` ("yo'q" emas, "bilib bo'lmadi": Docker, `df` yoki `free`
  ishlamasa); `certificates` va `backups` bo'sh massiv bo'lishi mumkin. O'qilmaydigan sertifikat tushib qoladi va
  stderr'ga ogohlantirish chiqadi.
- `certificates` — `/etc/letsencrypt/live/*/cert.pem` (`APPCTL_LETSENCRYPT` bilan o'zgartiriladi), `not_after` UTC.
- `backups` — `<zaxira>/*/daily` bor loyihalar; `last_daily_at` — eng yangi `*.sql.gz` (`.tmp` siz) `mtime` si;
  `weekly_count` faqat `*.sql.gz` ni sanaydi (haftalik fayl zaxirasi `*.tar.gz` kirmaydi).
- Xatoda (masalan, buzuq `.appctl`) stdout'ga `{"schema":1,"error":"…"}` chiqadi va kod 1 bo'ladi.

### 18.1.3. Zaxira holati fayllari

`state.json` va `_run.json` sxemalari 10.3.1 va 10.3.2 bo'limlarda.

## 18.2. Runbook'lar

Har runbook: **Belgi** (qanday ko'rinadi), **Tezkor tekshiruv**, **Odatiy sabablar**, **Qadamlar**,
**Tekshirish** (hal bo'ldimi), **Keyin** (takrorlanmasligi uchun). Buyruqlar Ubuntu 24.04 va
`appctl` ga mos. `<...>` — almashtiriladigan qiymat.

### RB-001. Server o'chdi / aloqa yo'q (AL-001, AL-008)

**Tezkor tekshiruv:** Bu faqat agentmi yoki butun server? Mahalliy kompyuterdan:
`ping <ip>`; `ssh <user>@<ip>`; boshqa tarmoq/VPN orqali ham sinab ko'ring (muammo sizning
tarmog'ingizda bo'lishi mumkin).

**Odatiy sabablar:** provayder nosozligi; server ichida kernel/boot muammosi; fayl tizimi xatosi;
disk to'ldi; DDoS/tarmoq; tasodifiy o'chirish.

**Qadamlar:**
1. Provayder panelida server holati (Contabo: "running"/"stopped"), provayder statusi sahifasi.
2. Panel konsoli (VNC) orqali ekranni ko'rish. Nima ko'rinadi?
   - Login so'rovi → server tirik, tarmoq muammosi: `ip a`, `netplan`, firewall (`ufw status`).
   - `Booting from Hard Disk...` yoki bo'sh ekran → boot muammosi (2-qadamdan keyin: 4).
   - Kernel panic / `emergency mode` → fayl tizimi xatosi (5).
3. Oddiy qayta ishga tushirish (panel "Restart") — **faqat** snapshot olingandan keyin (agar imkon bo'lsa).
4. Yuklanmasa: Rescue System (provayderning "Rescue") rejimiga o'ting: SSH bilan kirib,
   `lsblk`, `blkid`, `mount /dev/<root> /mnt`, `journalctl -D /mnt/var/log/journal -b -1 -e`
   bilan oxirgi boot xatosini ko'ring. GRUB: eski ishlaydigan kernelni tanlash (`GRUB_DEFAULT`).
5. Fayl tizimi: `umount`, `fsck -f -y /dev/<root>` (rescue ichida, **mount qilinmagan** holda).
6. Agar hech narsa yordam bermasa: **ma'lumotni boshqa serverga ko'chirish** (rescue'dan `rsync -aHAX`
   yangi serverga) va loyihalarni qayta ko'tarish (2026-10 tajribasi; `deploy/server/` skriptlari).
7. Offsite zaxira bo'lsa — tiklash (RB-030).

**Tekshirish:** server ping/SSH javob beradi; `appctl list` barcha loyiha `ishlayapti`; Nazoratchi'da
AL-001 yopildi.

**Keyin:** sabab post-mortemda; snapshot/zaxira/offsite tekshiruvi; GCP/provayderga xos qoldiq
agentlar yo'qligini tekshirish; kernel yangilanishi bo'lgan bo'lsa — RB-015.

### RB-002. Agent javob bermayapti (AL-002, AL-005, AL-006)

**Tezkor tekshiruv:** server tirik (SSH ishlaydi)?

**Qadamlar:**
1. `systemctl status nazoratchi-agent`; `journalctl -u nazoratchi-agent -n 100 --no-pager`.
2. Core'ga yetib boradimi: `curl -sS -m 10 https://<core>/healthz`.
3. Token bekor qilinganmi (401 loglarda)? → panelda yangi enroll tokeni, `install.sh` qayta.
4. Disk to'lganmi (`df -h /var/lib/nazoratchi`)? → RB-004.
5. Soat noto'g'rimi? → RB-016.
6. Oddiy: `systemctl restart nazoratchi-agent`.
7. Yangilanish muammosi: `/usr/local/bin/nazoratchi-agent.old` borligini tekshirib, qaytarish (RB-043).

**Tekshirish:** 1 daqiqada heartbeat; navbat (`agent_queue_files`) kamayadi.

### RB-003. Kutilmagan reboot (AL-003)

1. `last -x reboot | head -n 5`; `last -x shutdown | head`.
2. Oldingi boot oxiri: `journalctl -b -1 -e --no-pager | tail -n 80`.
3. `dmesg -T | grep -i -E "oom|panic|mce|i/o error"`.
4. Provayder hodisalari (xost nosozligi, migratsiya) — panel/email.
5. Kernel o'zgarganmi? `uname -r` (RB-015 bilan solishtiring).
6. Loyihalar tiklandimi: `appctl list`; `docker ps -a | grep -v Up`.
7. Sabab topilmasa — kuzatuvni kuchaytirish (keyingi 7 kun).

### RB-004. Disk to'lmoqda (AL-019..AL-024, AL-028, AL-079)

1. `df -h`; `df -i` (inode).
2. Nima band: `du -xh / --max-depth=2 2>/dev/null | sort -h | tail -n 20`.
3. Docker: `docker system df`; `docker ps -a --size`; katta log: `ls -lhS /var/lib/docker/containers/*/*-json.log | head`.
   - Eski image: `docker image prune` (ehtiyotkorlik bilan; `-a` faqat nima o'chishini bilgan holda).
   - Log limiti yo'q konteynerlar: `docker inspect -f '{{.Name}} {{.HostConfig.LogConfig.Config}}' $(docker ps -q)`;
     `daemon.json` limiti qo'llanishi uchun konteynerni qayta yaratish (`appctl down X && appctl up X`).
4. Tizim loglari: `journalctl --disk-usage`; `journalctl --vacuum-size=500M`.
5. Eski kernel/paketlar: `apt autoremove --purge` (**faqat yangi kernel muvaffaqiyatli yuklangandan keyin**).
6. Zaxira papkasi: `du -sh /opt/applications/backups/*`; offsite ishlayotgan bo'lsa, eski haftalik nusxalarni qisqartirish.
7. Katta fayllar: `find / -xdev -type f -size +500M -printf '%s %p\n' | sort -n | tail`.
8. Hech narsa yordam bermasa — diskni kengaytirish (provayder) va `growpart`/`resize2fs`.

**Tekshirish:** bandlik < 80%; bashorat > 14 kun.

### RB-005. Fayl tizimi faqat o'qish (AL-025)

**Diqqat:** hech narsa yozishga urinmang; ma'lumot butunligi xavf ostida.
1. `mount | grep -E ' ro[ ,]'`; `dmesg -T | grep -i -E "ext4|xfs|i/o error|remount"`.
2. Provayder panelida snapshot (agar imkon bo'lsa) — avval.
3. Servislarni to'xtatish: `appctl down <loyiha>` (yozish xatolari bo'lmasligi uchun, agar ishlasa).
4. Rescue rejimida `fsck -f -y /dev/<root>` (mount qilinmagan).
5. Muammo takrorlansa — disk/provayder nosozligi: yangi serverga ko'chirish (RB-001/6-qadam).

### RB-006. Sertifikat muddati/yangilanish (AL-057..AL-061)

1. `certbot certificates` (qaysi domen, qachon tugaydi).
2. `certbot renew --dry-run` — xato matnini o'qing.
3. Odatiy sabablar: 80-port yopiq yoki boshqa nginx bloki ushlab turibdi; DNS boshqa serverga qaraydi
   (RB-007); `server_name` yo'q; `/etc/letsencrypt` ruxsatlari; certbot timer o'chiq (`systemctl list-timers | grep certbot`).
4. Qo'lda: `certbot renew --cert-name <domen>`; so'ng **`systemctl reload nginx`** (AL-061: yangilangan, lekin reload qilinmagan).
5. S-02 (konteyner variant): `docker run --rm -v /opt/asadbekashurov/letsencrypt:/etc/letsencrypt -v /opt/asadbekashurov/certbot-www:/var/www/certbot certbot/certbot:v2.11.0 renew`; `docker exec asadbekashurov-web-1 nginx -s reload`.
6. Tashqaridan tekshirish: `echo | openssl s_client -connect <domen>:443 -servername <domen> 2>/dev/null | openssl x509 -noout -dates`.

### RB-007. DNS kutilgan IP ga qaramaydi (AL-062..AL-065)

1. Domen qayerda boshqariladi (reyestr: DNS provayder, kim nazorat qiladi).
2. Haqiqat manbai: `dig +short A <domen> @<NS-server>` va ommaviy: `@8.8.8.8`, `@1.1.1.1`, `@9.9.9.9`.
3. Mos kelmasa — provayder panelida A yozuvini kutilgan IP ga o'zgartirish (ahost.uz / Namecheap /
   Google Cloud DNS / Beget). Mijoz nazoratida bo'lsa (masalan, `*.wmg.uz`) — mijozga aniq xabar:
   "A yozuvi: `<domen>` → `<IP>` ga o'zgartirilsin".
4. `www.` yozuvi ham bormi tekshiring.
5. O'zgartirishdan so'ng Nazoratchi'da "tarqalish rejimi"ni yoqing. Google DNS keshi: `https://dns.google/cache`
   orqali tozalash mumkin.
6. Yangi serverda **oldindan** tekshirib qo'yish: `curl -I --resolve <domen>:443:<yangi_ip> https://<domen>/`.
7. Domen **eski** (yopilgan) IP ga qaraydi (AL-063) — ko'chirishdan keyin unutilgan yozuv; xuddi shu qadamlar.

### RB-008. Domen muddati (AL-066, AL-067)

1. Registrar (reyestrda) hisobiga kiring; to'lov usuli va avto-yangilash holatini tekshiring.
2. Domenni yangilang (kamida 1 yil).
3. `.uz` bo'lsa — registrator/provayder (masalan, ahost.uz) orqali; yangi sanani Nazoratchi'da qo'lda kiriting.
4. Avto-yangilash yoqilganini tasdiqlang.

### RB-009. CPU yuqori (AL-009..AL-013, AL-018, AL-040)

1. `top -o %CPU` yoki `htop`; `docker stats --no-stream`; `systemd-cgtop`.
2. `st` (steal) yuqori bo'lsa — provayder resursi yetmayapti: `top` dagi `%st`; vaqt o'tib turaversa provayder bilan bog'laning.
3. Konteyner aybdor bo'lsa: `appctl logs <loyiha> <servis>`; Celery tsikli, cheksiz takrorlanish, qotgan so'rov.
4. Qayta ishga tushirish: `docker restart <konteyner>` (ma'lumot yo'qolmaydi, lekin jarayondagi ish uziladi).
5. Rejalashtirilgan ishlar bilan mos kelishi: 03:15 zaxira (`pg_dump`) — vaqtni siljitishni ko'rib chiqing.
6. Doimiy bo'lsa — resurs chegarasi (`deploy.resources.limits`) yoki server kuchaytirish.

### RB-010. RAM yuqori / OOM (AL-014..AL-017, AL-038, AL-039)

1. `free -h`; `ps aux --sort=-%mem | head -n 10`; `docker stats --no-stream --format 'table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}'`.
2. OOM bo'lganmi: `dmesg -T | grep -i -E "out of memory|killed process"`; `docker inspect -f '{{.State.OOMKilled}}' <konteyner>`.
3. Sizish (leak) belgisi: Nazoratchi grafigi — RAM sekin o'sib borsa, jarayonni qayta ishga tushirish vaqtinchalik yordam.
4. Konteynerga xotira limiti qo'ying (bitta konteyner butun serverni o'ldirmasligi uchun).
5. Swap: `swapon --show`; yo'q bo'lsa kichik swap (1–2 GB) xavfsizlik to'ri sifatida.
6. Doimiy — server RAM ini oshirish yoki yukni boshqa serverga ko'chirish.

### RB-011. Disk I/O va yuklama (AL-012, AL-026, AL-027)

1. `iostat -x 1 5` (paket `sysstat`); `iotop -oPa`.
2. Zaxira (`pg_dump`, `tar`) paytimi? `ps aux | grep -E "pg_dump|tar|rsync"`.
3. PostgreSQL: `docker exec <db> psql -U <user> -c "SELECT pid, now()-query_start AS dur, state, left(query,80) FROM pg_stat_activity WHERE state<>'idle' ORDER BY dur DESC LIMIT 10"`.
4. Jarayonni vaqtga siljitish yoki `ionice -c3`/`nice` bilan ishga tushirish.

### RB-012. Nazoratchi'ning o'zi ishlamayapti (watchdog, AL-008)

1. Core serveriga SSH: `docker compose -f /opt/applications/projects/Nazoratchi/docker-compose.yml ps`.
2. Loglar: `docker compose logs --tail 100 web evaluator db`.
3. Disk/RAM: `df -h`, `free -h` (core to'lgan bo'lishi mumkin — RB-004).
4. Qayta ishga tushirish: `appctl up Nazoratchi`; kerak bo'lsa `appctl restart Nazoratchi`.
5. `db` yiqilgan bo'lsa: loglar (`docker compose logs db`), disk, `shared_buffers`/xotira.
6. Server o'lgan bo'lsa — RB-001, so'ng RB-044 (tiklash).
7. **Shu orada** boshqa serverlar kuzatuvsiz: oraliq vosita (Uptime Kuma) va provayder paneli.
8. Tiklangandan keyin agentlar buferdan ma'lumot yuboradi; AL-084/AL-085 yopilishini tekshiring.

### RB-013. Tarmoq xatolari (AL-029)

1. `ip -s link show <iface>`; `ethtool -S <iface> | grep -i -E "err|drop"`.
2. `mtr -rwc 50 <tashqi_manzil>`; MTU: `ip link | grep mtu`.
3. Provayder tarmoq muammosi bo'lishi mumkin — status sahifa/murojaat.

### RB-014. SSH hujumi va xavfsizlik gumoni (AL-031)

1. Urinishlar: `journalctl -u ssh --since "-1h" | grep -E "Failed|Invalid" | awk '{print $(NF-3)}' | sort | uniq -c | sort -rn | head`.
2. `fail2ban-client status sshd` (o'rnatilgan bo'lsa); o'rnatilmagan bo'lsa — `setup.sh --fail2ban`.
3. Parol bilan SSH ochiq bo'lsa — kalitga o'tish (`setup.sh --harden-ssh`, avval kalit bilan kirishni tekshiring).
4. **Muvaffaqiyatli** kirish bormi: `last -a | head`; `grep "Accepted" /var/log/auth.log | tail`.
5. Buzilish gumoni bo'lsa: `authorized_keys`, yangi foydalanuvchilar (`getent passwd`), `crontab -l`, `/etc/cron.d`,
   noma'lum jarayonlar (`ps auxf`), tashqi ulanishlar (`ss -tnp`). Agar tasdiqlansa — serverni ajratish,
   barcha maxfiy qiymatlarni almashtirish, agent tokenini bekor qilish (14.12.1).

### RB-015. Kernel yangilanishi va reboot (AL-032..AL-034)

**Reboot oldidan (majburiy):**
1. Snapshot (provayder paneli) — tasdiqlang.
2. Oxirgi zaxira yangi va **offsite'da bor** (Nazoratchi zaxira sahifasi).
3. Texnik ish oynasi yarating (alertlar jim bo'ladi).
4. Eng kamida bitta ishlaydigan eski kernel o'rnatilgan (`dpkg -l | grep linux-image`), GRUB menyusida ko'rinadi.
5. VNC/konsol kirishi tayyor (parol/rescue).

**Bajarish:** `reboot`. 3–5 daqiqa kuting.

**Reboot'dan keyin:** `uname -r`; `docker ps`; `appctl list`; `systemctl --failed`; Nazoratchi'da barcha loyiha yashil.

**Yuklanmasa:** VNC → GRUB menyusi → eski kernel (Advanced options); yoki RB-001. Eski kernelni
`autoremove` bilan o'chirishni yangi kernel barqaror ishlagandan keyin (kamida 1 hafta) bajaring.

### RB-016. Vaqt sinxronligi (AL-007)

`timedatectl`; `chronyc tracking` yoki `timedatectl timesync-status`; `systemctl restart systemd-timesyncd`
(yoki `chrony`); `timedatectl set-ntp true`.

### RB-020. Konteyner ishlamayapti / crash loop (AL-035..AL-037, AL-042)

1. `docker ps -a --format 'table {{.Names}}\t{{.Status}}'`.
2. `docker logs --tail 100 <konteyner>`; `docker inspect -f '{{.State.ExitCode}} {{.State.OOMKilled}} {{.State.Error}}' <konteyner>`.
3. Loyiha orqali: `appctl ps <loyiha>`; `appctl logs <loyiha> <servis>`.
4. Odatiy sabablar: baza tayyor emas (`depends_on`), noto'g'ri `.env`, port band (`ss -ltnp | grep :<port>`), migratsiya xatosi, xotira (RB-010), disk (RB-004).
5. Tuzatgach: `appctl up <loyiha>`; `appctl status`; sog'liq: `curl -I -H 'Host: <domen>' -H 'X-Forwarded-Proto: https' http://127.0.0.1:<port>/`.
6. Reyestrda yo'q konteyner (AL-042): yangi loyiha reyestrga qo'shilmagan yoki ruxsatsiz konteyner — kim ko'targanini aniqlang.

### RB-021. Konteyner xotira/log muammolari (AL-038, AL-039, AL-041)

1. Log fayli katta: `docker inspect -f '{{.LogPath}}' <konteyner>`; hajm: `ls -lh <yo'l>`.
2. Log limiti yo'q (eski konteyner): `daemon.json` ni tekshiring; konteynerni qayta yaratish: `appctl down <loyiha> && appctl up <loyiha>`.
3. Shoshilinch joy kerak bo'lsa: `truncate -s 0 <LogPath>` (**faqat log**, konteyner ishlayotganda xavfsiz; ma'lumot yo'qoladi).
4. Xotira limiti: compose'da `mem_limit`/`deploy.resources.limits.memory`; ilova talabiga mos qiymat.

### RB-022. systemd servis (AL-043..AL-045)

1. `systemctl status <unit> --no-pager`; `journalctl -u <unit> -n 100 --no-pager`.
2. `EnvironmentFile` ruxsati (servis foydalanuvchisi o'qiy oladimi: `sudo -u <user> cat <fayl>`), `ExecStart` yo'li (`which node`).
3. Port band: `ss -ltnp | grep :<port>`.
4. `systemctl restart <unit>`; takrorlanadigan bo'lsa — `systemctl reset-failed`.
5. Namuna: `avlo-contact` — Node (`/usr/bin/node`), `.env` rejimi `0600`, egasi `avlo`.

### RB-023. nginx konfiguratsiyasi (AL-046)

1. `nginx -t` (xato matni qaysi fayl/qator ekanini aytadi).
2. Odatiy: yo'q sertifikat fayli, yo'q kesh papkasi (`/var/cache/nginx/<nom>` — yaratib `chown www-data`),
   takroriy `server_name`, `include` yo'li.
3. Tuzatgach: `nginx -t && systemctl reload nginx` (`appctl nginx`).
4. **Reload'dan keyin** 2 soniya kutib tekshiring (reload poygasi tufayli birinchi so'rov 5xx bo'lishi mumkin).

### RB-024. Cron / heartbeat (AL-047, AL-048)

1. Cron ishlayaptimi: `systemctl status cron`; fayl: `cat /etc/cron.d/appctl-backup`.
2. Qo'lda ishga tushirish: `appctl backup all`; chiqish va `tail -n 50 /var/log/appctl-backup.log`.
3. Heartbeat URL ga yetish: `curl -fsS -m 10 https://<core>/hb/<TOKEN>?status=ok` (tokenni hujjatga yozmang).
4. `status=fail` bo'lgan bo'lsa — cron bajargan buyruq xato bergan: RB-031.

### RB-025. Sayt ishlamayapti (AL-049, AL-051, AL-053)

Tashqaridan ichkariga ketma-ket:
1. **DNS:** `dig +short A <domen>` — kutilgan IP mi? Yo'q → RB-007.
2. **TLS:** `curl -vI https://<domen>/ 2>&1 | head -n 25` — sertifikat/ulanish → RB-006.
3. **Server tirikmi:** `ping`/SSH → RB-001.
4. **nginx:** `systemctl status nginx`; `nginx -t` → RB-023; 80/443 ochiqmi: `ufw status`; `ss -ltnp | grep -E ':80|:443'`.
5. **Ilovaga yetadimi (serverda):** `curl -I -H 'Host: <domen>' -H 'X-Forwarded-Proto: https' http://127.0.0.1:<port>/`.
6. **Konteynerlar:** RB-020.
7. Front-proksi (S-02): `/etc/nginx/nginx.conf` dagi `map` qoidalarida domen bormi (`grep -n <domen> /etc/nginx/nginx.conf`).
8. Hammasi ichkarida yaxshi, tashqaridan yo'q → firewall/provayder tarmog'i.

### RB-026. Sayt sekin (AL-050, AL-052)

1. Nazoratchi'da vaqt komponentlari: `dns_ms`, `connect_ms`, `tls_ms`, `ttfb_ms` — qaysi biri katta?
2. TTFB katta bo'lsa — ilova: CPU/RAM (RB-009/010), DB so'rovlari (RB-011/3-qadam), Celery to'planib qolgan navbat.
3. Connect/TLS katta — tarmoq yoki server yuklamasi.
4. Yaqinda deploy bo'lganmi (deploy belgilari, F3)? Qaytarish ko'rib chiqing.

### RB-027. Kutilmagan ochiq port (AL-030)

1. `ss -ltnp` — kim tinglayapti va qaysi manzilda (`0.0.0.0` yoki `127.0.0.1`).
2. Docker portlari: `docker ps --format '{{.Names}} {{.Ports}}'`. Docker nashr qilgan port `ufw` ni chetlab o'tadi.
3. Tuzatish: compose'da `ports: !override ["127.0.0.1:<port>:<port>"]` (yoki `.appctl` dagi `COMPOSE_EXTRA` orqali), `appctl up <loyiha>`.
4. Tashqaridan tasdiqlash: `nmap -Pn -p <port> <ip>` (yopiq bo'lishi kerak).
5. Ruxsatsiz konteyner/jarayon bo'lsa — RB-014 (xavfsizlik gumoni).

### RB-030. Avariya tiklash — ma'lumotni zaxiradan qaytarish

**Diqqat:** `appctl restore` mavjud bazani **o'chiradi**. Faqat tiklash kerak bo'lgan holatda.
1. Maqsadni aniqlang: qaysi loyiha, qaysi vaqtga (RPO).
2. Eng yangi **yaxlit** zaxira: Nazoratchi zaxira kartasi (`gz_ok`, hajm normal) — mahalliy yoki offsite.
   Offsite'dan olish: `rsync -a <offsite>:/<yo'l>/<loyiha>/daily/<fayl> /opt/applications/backups/<loyiha>/daily/`.
3. Joriy holatni saqlab qo'ying (agar baza hamon o'qilsa): `appctl backup <loyiha>` yoki qo'lda `pg_dump`.
4. `appctl restore <loyiha> /opt/applications/backups/<loyiha>/daily/<fayl>.sql.gz --yes`.
5. Media/fayl zaxirasi kerak bo'lsa: `tar -xzf <fayl>.tar.gz -C /` (yo'llar `BACKUP_PATHS` ga mos).
6. Tekshirish: `appctl ps <loyiha>`, sog'liq URL, ilovada ma'lumot borligi (oxirgi yozuvlar).
7. Ma'lumot tiklangan vaqtdan keyingi yo'qotish haqida foydalanuvchilarga xabar (zarur bo'lsa).
8. Hodisa tahlili va drill natijasini yangilash.

### RB-031. Zaxira kechikdi / muvaffaqiyatsiz (AL-068..AL-070, AL-074)

1. `tail -n 50 /var/log/appctl-backup.log` — xato matni.
2. Cron ishlaganmi: `grep CRON /var/log/syslog | tail`; `cat /etc/cron.d/appctl-backup`.
3. Qo'lda: `appctl backup <loyiha>` — xato aniq ko'rinadi.
4. Odatiy: DB konteyner o'chiq (RB-020); `.appctl` da noto'g'ri `DB_USER`/`DB_NAME`/`DB_SERVICE`; disk to'lgan (RB-004);
   ruxsat; `pg_dump` versiya nomuvofiqligi.
5. Tuzatgach: qo'lda zaxira → Nazoratchi'da yosh qayta hisoblanadi.

### RB-032. Zaxira shubhali yoki buzuq (AL-071..AL-073)

1. Hajm tarixi: Nazoratchi zaxira kartasida (kunlik hajm grafigi).
2. Fayl: `gzip -t <fayl>`; `zcat <fayl> | head -n 50` (PostgreSQL dump belgilari); `zcat <fayl> | grep -c '^COPY'`.
3. Manba bazada ma'lumot yo'qolganmi? (`SELECT count(*)` asosiy jadvallarda) — "kichik zaxira" haqiqiy ma'lumot yo'qolishining belgisi bo'lishi mumkin.
4. Darhol yangi zaxira oling; ikkalasini solishtiring. Eski yaxshi nusxalar o'chib ketmasligi uchun saqlash (`KEEP_DAILY`) ni vaqtincha oshiring yoki nusxalang.
5. Hajm o'sishi "katta" (AL-072) — odatda yangi ma'lumot yoki log jadvali; sabab topilsa `baseline_reset`.

### RB-033. Offsite zaxira (AL-075..AL-078, AL-080)

1. Sozlanmagan (AL-075): `/opt/applications/appctl.conf` da `OFFSITE=root@<host>:/yo'l`; kalit: `ssh-keygen -t ed25519`, `ssh-copy-id`; sinov: `ssh -o BatchMode=yes <host> 'df -h /yo\'l'`.
2. Eskirgan (AL-076/077): `appctl backup all` oxirida `→ offsite:` qatorini ko'ring; qo'lda: `rsync -a --dry-run -e "ssh -o BatchMode=yes" /opt/applications/backups/ <host>:/yo'l/`.
3. SSH muammo: host kaliti o'zgargan (`ssh-keygen -R`), kalit yo'q, maqsad server o'chiq (RB-001).
4. Maqsadda joy: `ssh <host> df -h`; eski nusxalarni tozalash (maqsadda alohida cron).
5. Mos emas (AL-078): oxirgi fayl nomi/hajmi; rsync oraliq holatida bo'lishi mumkin (30 daq kuting); davom etsa — qo'lda sinxronlash va log.

### RB-034. Restore drill (AL-081..AL-083)

10.8-bo'limdagi qadamlar. Qisqa: vaqtinchalik `postgres:<major>` konteyner → bazani yaratish →
`gunzip -c <fayl> | psql ... -v ON_ERROR_STOP=1` → jadval/qator sonini solishtirish → natijani panelga kiritish.
**Ishlab turgan bazaga tegmang.**

### RB-040. Alert dvigateli / prober qotdi (AL-055, AL-084, AL-085)

1. `docker compose ps`; `docker compose logs --tail 200 evaluator prober`.
2. Bazaga ulanish: `docker compose exec db pg_isready`; ulanishlar soni: `SELECT count(*) FROM pg_stat_activity`.
3. `advisory lock` ushlanib qolgan bo'lishi mumkin: `SELECT * FROM pg_locks WHERE locktype='advisory'`.
4. Qayta ishga tushirish: `docker compose restart evaluator prober`.
5. Tez-tez qotsa — xotira (`docker stats`), sekin so'rovlar (`EXPLAIN`), qoidalar soni.

### RB-041. Bildirishnoma kanali ishlamayapti (AL-086)

1. Panel → Sozlamalar → Kanallar → "Sinov" tugmasi; xato matni (`last_error`).
2. Telegram: tokenni tekshirish — `curl -sS https://api.telegram.org/bot<TOKEN>/getMe` (natijani/tokenni tashqariga chiqarmang);
   bot guruhdan chiqarilmaganmi; `chat_id` to'g'rimi.
3. Core'dan tashqariga 443: `curl -sS -m 10 https://api.telegram.org` (firewall/DNS).
4. Webhook: `getWebhookInfo` (`last_error_message`).
5. Email: SMTP ulanishi, parol; spam.
6. Vaqtincha: boshqa kanalni yoqing (email); tuzatgach "sinov".

### RB-042. Nazoratchi bazasi / saqlash muammolari (AL-087..AL-089)

1. Hajm: `SELECT hypertable_name, pg_size_pretty(hypertable_size(format('%I',hypertable_name)::regclass)) FROM timescaledb_information.hypertables;`.
2. Fon vazifalari: `SELECT job_id, application_name, last_run_status, next_start FROM timescaledb_information.job_stats js JOIN timescaledb_information.jobs j USING(job_id);`.
3. Siqish/retention ishlamayotgan bo'lsa — `CALL run_job(<job_id>)`; xato loglari.
4. Hajm o'ssa — retention qisqartirish (sozlama), kardinallik tekshiruvi (qaysi host ko'p `series` yaratyapti), diskni oshirish.
5. Ingest xatolari (AL-088): `docker compose logs web | grep -E "ingest|ERROR"`; agent versiyasi/sxema mosligi.

### RB-043. Agent versiyasi va yangilash (AL-004)

1. Panelda agent versiyasi va "yangilash kerak" belgisi.
2. Yangilash `update` buyrug'i bilan avtomatik; qo'lda: `curl -fsSL https://<core>/install.sh | sudo bash -s -- --upgrade`.
3. Imzo xatosi (`agent_update_rejected`): core'dagi fayl noto'g'ri imzolangan bo'lishi mumkin — **qo'lda o'rnatmang**, CI artefaktini tekshiring (14.5.4).
4. Rollback: `/usr/local/bin/nazoratchi-agent.old` ni qaytarib `systemctl restart nazoratchi-agent`.

### RB-044. Nazoratchi'ni yangi serverda tiklash

15.9-bo'limdagi qadamlar (RTO ≤ 60 daqiqa). Eslatma: `master.key` va `age` maxfiy kaliti parol menejeridan;
zaxira fayli Owner'ning Telegram chatidan olinadi.

## 18.3. `state` shart manbalari (12.3.5)

| `source` | Maydonlar | Qiymatlar |
|---|---|---|
| `probe` | `state`, `consecutive_failures`, `days_left`, `total_ms`, `ttfb_ms`, `uptime_30d` | `up/down/unknown`; sonlar |
| `backup` | `status`, `age_h`, `size_ratio`, `gz_ok`, `offsite_lag_h`, `offsite_in_sync`, `drill_age_days`, `drill_result` | `ok/fail/stale/...`; sonlar; bool |
| `cert` | `days_left`, `chain_ok`, `hostname_ok`, `renew_failures` | sonlar; bool |
| `dns` | `status`, `matches_expected`, `retired_ip`, `resolver_disagree_min` | `match/propagating/mismatch/retired_ip/nxdomain`; bool; daqiqa |
| `heartbeat` | `age_s`, `last_ok` | son; bool |
| `host` | `status`, `last_seen_age_s`, `tcp22_ok`, `agent_version_lag`, `kernel_pending` | `online/offline/paused`; sonlar; bool |
| `system` | `evaluator_age_s`, `probe_stall_s`, `db_size_ratio`, `ingest_error_ratio`, `channel_failures` | sonlar |

## 18.4. Tekshiruv (probe) konfiguratsiya sxemalari

### 18.4.1. `http`

```json
{
  "url": "https://nazar.avlo.ai/healthz/",
  "method": "GET",                       // GET | HEAD
  "expected_status": [200],              // [200] yoki ["200-299"] yoki [200, 301]
  "keyword": {"text": "ok", "mode": "contains"},   // contains | not_contains; null bo'lishi mumkin
  "follow_redirects": true,
  "max_redirects": 5,
  "headers": {"X-Check": "nazoratchi"},     // maxfiy qiymatli sarlavhalar secrets_enc da
  "verify_tls": true,
  "resolve_to": null,                    // "164.68.105.194" — cut-over oldindan tekshiruvi (SNI/Host saqlanadi)
  "latency_warn_ms": 3000,
  "max_body_bytes": 65536,
  "allow_private": false,   // faqat Owner o'rnatadi (SSRF)
  "primary": false          // true: AL-049 (critical), aks holda AL-049H (high)
}
```

### 18.4.2. `tcp`

```json
{ "host": "164.68.105.194", "port": 5432, "expect": "closed" }
```
`expect`: `open` (standart) yoki `closed` (xavfsizlik tekshiruvi). Qo'shimcha: `allow_private`, `primary` (http dagidek).

### 18.4.3. `tls`

```json
{ "host": "nazar.avlo.ai", "port": 443, "sni": "nazar.avlo.ai",
  "warn_days": 21, "high_days": 7, "critical_days": 3, "check_chain": true, "check_hostname": true }
```

### 18.4.4. `dns`

```json
{
  "name": "lutfanai.uz",
  "rtype": "A",
  "resolvers": ["8.8.8.8", "1.1.1.1", "9.9.9.9", "ns:auto"],
  "expected": ["164.68.105.194"],
  "retired_ips": ["34.173.220.247"],
  "mismatch_after_min": 10,
  "watch": {"enabled": false, "until": null, "interval_s": 60}
}
```
`ns:auto` — domenning haqiqiy NS serverlarini aniqlab so'raydi.

### 18.4.5. `whois`

```json
{ "domain": "avlo.ai", "source": "rdap", "warn_days": 30, "critical_days": 7 }
```
`.uz` uchun `"source": "manual"` va `expires_at` qo'lda.

## 18.5. Boshlang'ich reyestr (`seed/inventory.yaml`) formati va mazmuni

Quyidagi fayl 2026-10-22 holatidagi inventarni (2-bo'lim) Nazoratchi'ga yuklaydi. Qiymatlari
aniqlanmagan maydonlar (`?`) bo'sh qoldirilgan; ularni dasturchi birinchi ishga tushirishdan
oldin to'ldiradi.

```yaml
version: 1
retired_ips: [34.173.220.247]   # GCP o'chirilgan (Q-12)

servers:
  - { name: main-2,     provider: Contabo, public_ipv4: 164.68.105.194, role: production, tags: [contabo, docker, appctl, watchdog] }
  - { name: vmd208589,  provider: "",      public_ipv4: 173.249.37.152, role: production, tags: [docker, front-proxy, aaclub] }
  - { name: core-1,     provider: Contabo, public_ipv4: 185.214.135.9,  role: core,       tags: [contabo, core, offsite] }   # S-00, Owner qarori
  - { name: backup-1,   provider: "",      public_ipv4: 38.242.143.248, role: unused,     tags: [unused], status: archived }       # S-03 ishlatilmaydi (Q-07)

projects:
  - slug: Nazar
    name: Nazar (Beyondlinks)
    kind: compose
    servers: [{ server: main-2, environment: production, ports: [8020, 3020] }]
    domains:
      - { fqdn: nazar.avlo.ai,       primary: true, dns_provider: Namecheap }
      - { fqdn: app.beyondlinks.uz,  primary: true, dns_provider: "" }
    probes:
      - { type: http, url: "https://nazar.avlo.ai/healthz/", expected_status: [200] }
    backup: { expect_daily: true, require_offsite: true, db: postgres16 }

  - slug: BiznesRadar
    name: BiznesRadar
    kind: compose
    servers: [{ server: main-2, environment: production, ports: [8030, 4321] }]
    domains:
      - { fqdn: biznesradar.uz,        primary: true }
      - { fqdn: api.biznesradar.uz }
      - { fqdn: admin.biznesradar.uz }
      - { fqdn: cabinet.biznesradar.uz }
    backup: { expect_daily: true, expect_weekly_files: true, db: postgres17 }

  - slug: beyondlinks_landing
    name: Beyondlinks landing
    kind: static
    servers: [{ server: main-2, environment: production }]
    domains: [{ fqdn: beyondlinks.uz, primary: true }]
    backup: { expect_daily: false }

  - slug: freighthubllc
    name: FreightHub LLC
    kind: static
    servers: [{ server: main-2, environment: production }]
    domains: [{ fqdn: freighthubllc.co, primary: true }, { fqdn: freighthubllc.com }]
    backup: { expect_daily: false }

  - slug: lutfan_ai
    name: Lutfan AI
    kind: compose
    servers: [{ server: main-2, environment: production, ports: [8080, 9000] }]
    domains: [{ fqdn: lutfanai.uz, primary: true }, { fqdn: lutfan.israilov.uz }]
    backup: { expect_daily: true, expect_weekly_files: true, db: postgres15 }

  - slug: wmg
    name: WMG landing sahifalari
    kind: compose
    servers: [{ server: main-2, environment: production, ports: [8011, 8012] }]
    domains:
      - { fqdn: moliyaviyerkinlik.wmg.uz, controlled_by: client, dns_provider: Beget }
      - { fqdn: investitsiya.wmg.uz,      controlled_by: client, dns_provider: Beget }
    backup: { expect_daily: false, expect_weekly_files: true }      # SQLite + media

  - slug: avlo_site
    name: avlo.ai sayt va kontakt formasi
    kind: static
    servers: [{ server: main-2, environment: production, ports: [3017] }]
    domains: [{ fqdn: avlo.ai, primary: true, dns_provider: Namecheap }, { fqdn: www.avlo.ai }]
    services_systemd: [avlo-contact]
    backup: { expect_daily: false }

  - slug: asadbekashurov
    name: asadbekashurov.uz landing
    kind: static
    servers: [{ server: vmd208589, environment: production, ports: [38080, 38443] }]
    domains: [{ fqdn: asadbekashurov.uz, primary: true, dns_provider: ahost.uz }, { fqdn: www.asadbekashurov.uz }]
    backup: { expect_daily: false }

  - slug: aaclub_staging
    name: Aaclub (staging)
    kind: compose
    servers: [{ server: vmd208589, environment: staging, ports: [28080, 28443] }]
    domains: []        # *.staging.<domen> (aniqlanadi)
    backup: { expect_daily: false }    # aniqlanadi

  # Hali ko'chirilmagan (eski serverdan): reyestrda bor, tekshiruvsiz.
  - { slug: Matnchi,   name: Matnchi,   kind: compose, moved: false, domains: [{ fqdn: matnchi.avlo.ai }] }
  - { slug: CallAI,    name: CallAI,    kind: compose, moved: false, domains: [{ fqdn: call.avlo.ai }] }
  - { slug: Transcription, name: Transcription, kind: systemd, moved: false, domains: [{ fqdn: transcription.avlo.ai }] }
  - { slug: avlocorp,  name: avlocorp.com (Quran), kind: other, moved: false, domains: [{ fqdn: avlocorp.com }] }
  - { slug: avloai_uz, name: avloai.uz, kind: static, moved: false, domains: [{ fqdn: avloai.uz }] }

heartbeats:
  - { name: appctl-backup@main-2,         server: main-2,    expected_every_s: 86400, grace_s: 7200 }
  - { name: certbot-renew@main-2,         server: main-2,    expected_every_s: 86400, grace_s: 43200 }
  - { name: asadbekashurov-certbot@vmd208589, server: vmd208589, expected_every_s: 86400, grace_s: 10800 }
  - { name: nazoratchi-self-backup@core-1, server: core-1, expected_every_s: 86400, grace_s: 7200 }
```

## 18.6. Hujjat bilan bog'liq ma'lumotlar

| Mavzu | Qayerda |
|---|---|
| Talablar ro'yxati va sanog'i | 4, 5-bo'limlar va 18.7 |
| Alert qoidalari katalogi | 12.7 |
| Runbook'lar | 18.2 |
| Metrikalar katalogi | 7.4 |
| Ma'lumotlar modeli (DDL) | 8 |
| API | 9 |
| Rejalash va xavflar | 17 |
