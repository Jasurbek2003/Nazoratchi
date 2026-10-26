# 2. Hozirgi infratuzilma inventari

Bu bo'lim 2026-10-22 holatiga ko'ra mavjud tizimni tasvirlaydi. Nazoratchi reyestri
(FR-REG-*) birinchi marta shu ma'lumot bilan to'ldiriladi. Aniq noma'lum qiymatlar
"aniqlanadi" deb belgilangan; ularni yig'ish buyruqlari 2.9-bo'limda.

## 2.1. Serverlar

| ID | Nomi | Provayder | IP | Rol | Holat |
|---|---|---|---|---|---|
| S-01 | vmi3679093 ("main-2") | Contabo VPS | 164.68.105.194 | Asosiy ishchi server: Nazar, BiznesRadar, lutfan_ai, wmg, avlo.ai, landinglar; keyinchalik Nazoratchi watchdog | Ishlayapti |
| S-02 | vmd208589 | (aniqlanadi) | 173.249.37.152 | Aaclub staging + production stek, asadbekashurov.uz landingi | Ishlayapti |
| S-03 | (nomi aniqlanadi) | (aniqlanadi) | 38.242.143.248 | Egasiniki; zaxira uchun **ishlatilmaydi** (Owner qarori, 2026-10-26) | Zaxiralanmaydi |
| S-00 | vmi3628663 ("Avlo main server") | Contabo VPS, 200 GB SSD | 185.214.135.9 | **Nazoratchi core + S-01 uchun offsite zaxira** (Owner qarori). Oldin yuklanmagan, tozalanib qayta o'rnatilmoqda | Qayta o'rnatilmoqda |
| S-GCP | (Google Cloud) | GCP | 34.173.220.247 | Eski bulut, **endi mavjud emas** (Owner, 2026-10-26); lutfanai.uz, wmg.uz subdomenlari hali shu IP ga qaraydi | O'CHIRILGAN, DNS yangilanishi kerak |

### 2.1.1. S-01 batafsil

| Parametr | Qiymat |
|---|---|
| OS | Ubuntu 24.04 LTS |
| Kernel (ishlayotgan) | 6.8.0-139-generic |
| Kernel (o'rnatilgan, kutilayotgan) | 6.8.0-147-generic (reboot kerak) |
| Docker | Docker Engine + Compose v5; `daemon.json`: `json-file` 10m×3, `live-restore: true` |
| Veb-server | nginx (host), konfiglar `/opt/applications/nginx/*.conf` |
| Sertifikat | certbot (nginx authenticator); `/etc/letsencrypt` |
| Node.js | 22.23.3 (NodeSource), `avlo-contact` uchun |
| Tarmoq | Tashqariga faqat 22, 80, 443; qolgan portlar `127.0.0.1` da |
| Boshqaruv | `appctl` (`/usr/local/bin/appctl`), `/opt/applications/{projects,nginx,scripts,backups,sites,services}` |
| Zaxira | Kunlik 03:15 `appctl backup all`; log `/var/log/appctl-backup.log` |
| SSH | Parol bilan (kalit keyinroq rejalashtirilgan) |
| CPU / RAM / disk | aniqlanadi (2.9-bo'lim) |

### 2.1.2. S-02 batafsil

| Parametr | Qiymat |
|---|---|
| Disk | 193 GB, ~19 GB band (10%) |
| nginx | 1.24.0, faqat front-proksi (`stream` + `http` map), konfig yagona fayl `/etc/nginx/nginx.conf` |
| Yo'naltirish | `*.staging.*` → 127.0.0.1:28080/28443; qolgan hamma → 127.0.0.1:18080/18443 (production, hozir ishlamayapti); `asadbekashurov.uz` → 127.0.0.1:38080/38443 |
| Docker | `aaclub-staging-*` (≈ 25 konteyner: api, worker-*, beat, postgres, redis, minio, qdrant, prometheus, loki, grafana, alertmanager, node-exporter, cadvisor va h.k.), `asadbekashurov-web-1` |
| Himoya | ufw (22, 80, 443), fail2ban (sshd) |
| Eslatma | Serverda **allaqachon** Prometheus+Grafana+node-exporter (staging steki ichida) bor; Nazoratchi ularni almashtirmaydi, lekin ularning mavjudligini hisobga oladi |
| Maxsus | nginx.conf "TO'LIQ fayl" deb belgilangan, aaclub repo'sidan boshqariladi; bizning qo'shgan qoidalarimiz qayta yozilishi xavfi bor (R-009) |

## 2.2. Loyihalar (S-01)

Barcha loyihalar `/opt/applications/projects/<Nomi>/` da. Portlar `127.0.0.1` ga bog'langan.

| Loyiha | Domen(lar) | Backend port | Frontend port | Turi | Baza | Zaxira |
|---|---|---|---|---|---|---|
| Nazar | nazar.avlo.ai, app.beyondlinks.uz | 8020 | 3020 | Docker Compose (`docker-compose.prod.yml`): db, redis, web, worker, worker-yandex, beat, frontend | PostgreSQL 16 | pg_dump kunlik |
| BiznesRadar | biznesradar.uz, api./admin./cabinet. | 8030 | 4321 | Docker Compose | PostgreSQL 17 | pg_dump kunlik + media haftalik |
| beyondlinks_landing | beyondlinks.uz | — | statik | nginx | — | — |
| freighthubllc | freighthubllc.co / .com | — | statik | nginx | — | — |
| lutfan_ai | lutfanai.uz, lutfan.israilov.uz | — | 8080 (+MinIO 9000) | Docker Compose + `docker-compose.server.yml` | PostgreSQL 15 | pg_dump + media/minio haftalik |
| wmg | moliyaviyerkinlik.wmg.uz, investitsiya.wmg.uz | — | 8011, 8012 | Docker Compose (2 servis, gunicorn) | SQLite | sqlite+media haftalik |
| avlo.ai sayt | avlo.ai, www.avlo.ai | 3017 (`avlo-contact`) | statik `/opt/applications/sites/avlo` | nginx + systemd | — | — |

### 2.2.1. Servis nomlari va `appctl` konfiguratsiyasi

Har loyiha papkasida `.appctl` fayli (bash sintaksisi) bor:

| O'zgaruvchi | Ma'nosi |
|---|---|
| `DB_SERVICE`, `DB_USER`, `DB_NAME` | pg_dump uchun |
| `PROJECT_NAME` | Compose loyiha nomi |
| `COMPOSE_EXTRA` | Qo'shimcha compose fayl (serverga xos portlar) |
| `HEALTH_URL`, `HEALTH_CURL_OPTS` | Sog'liq tekshiruvi (masalan, `-H Host:nazar.avlo.ai -H X-Forwarded-Proto:https`) |
| `BACKUP_PATHS` | Haftalik fayl zaxirasi yo'llari |

Nazoratchi bu faylni **o'qimaydi**; ma'lumotni `appctl list --json` / `appctl status --json`
orqali oladi (talab FR-INT-001..003, 4-bo'lim).

## 2.3. Loyihalar (S-02)

| Loyiha | Domen | Port | Izoh |
|---|---|---|---|
| Aaclub staging | *.staging.<domen> | 28080/28443 | Docker, to'liq stek |
| Aaclub production | (kutilmoqda) | 18080/18443 | `/opt/aaclub`; hozir ishlamayapti |
| asadbekashurov.uz | asadbekashurov.uz, www | 38080/38443 | Statik landing, `nginx:1.27-alpine`, `/opt/asadbekashurov`; sertifikat kunlik cron bilan yangilanadi |

## 2.4. Hali ko'chirilmagan loyihalar (eski serverdagi nusxa `/root/old-server`)

| Loyiha | Domen | Ishlash usuli (eski serverda) | Izoh |
|---|---|---|---|
| avlocorp.com (Quran) | avlocorp.com | `projects/Quran`, backend :8200 | Keyinga qoldirilgan |
| Matnchi | matnchi.avlo.ai | Django + PostgreSQL | Tavsiya etilgan keyingi loyiha |
| CallAI | call.avlo.ai | Django (`CallAI_back`) + front | |
| Transcription / TranscriptionBot | transcription.avlo.ai | systemd (`transcriptionbot-django`, `audio-analysis`) | |
| bot.avlo.ai, najotnur.avlo.ai, asror-iskandarov.avlo.ai | | aniqlanmagan | |
| Bitrix* | | systemd (`bitrix`, `bitrix-celery`, `celery-beat`) | |
| receipt_bot, xatmbot, AvloAIBot-IG, consultation | | systemd/boshqa | |
| avloai.uz | avloai.uz | statik (avlo.ai ning nusxasi) | Egasi ko'chirmaslikka qaror qildi |
| ai-journalist | | `/opt/ai-journalist` | |

Nazoratchi reyestri bu loyihalarni "ko'chirilmagan" holati bilan ham saqlashi kerak (FR-REG-007).

## 2.5. Domenlar va DNS

| Domen | NS / DNS provayder | Hozirgi A yozuvi | Egasi / nazorati |
|---|---|---|---|
| avlo.ai | Namecheap (registrar-servers.com) | 164.68.105.194 | Buyurtmachi |
| avloai.uz, asadbekashurov.uz | ahost.uz (rdns1/2) | avloai.uz → 185.214.135.9 (endi core serveri IP si, ko'chirilishi kerak); asadbekashurov.uz → 173.249.37.152 | Buyurtmachi |
| beyondlinks.uz, biznesradar.uz, freighthubllc.co/.com | (aniqlanadi) | 164.68.105.194 | Buyurtmachi/mijoz |
| lutfanai.uz, lutfan.israilov.uz | (aniqlanadi) | 34.173.220.247 (GCP, mavjud emas) | DNS yangilanishi kerak |
| *.wmg.uz | Beget | 34.173.220.247 (GCP, mavjud emas) | **Mijoz** nazorati; DNS yangilanishi kerak |

## 2.6. Zaxira tuzilmasi (S-01)

```
/opt/applications/backups/
  <loyiha>/
    daily/    <loyiha>-YYYYMMDD-HHMMSS.sql.gz        (7 kun)
    weekly/   <loyiha>-YYYYMMDD-HHMMSS.sql.gz        (yakshanba nusxasi, 5 hafta)
              <loyiha>-files-YYYYMMDD-HHMMSS.tar.gz  (BACKUP_PATHS, haftalik)
```

Qoidalar (appctl):
- `pg_dump | gzip`, fayl `.tmp` ga yoziladi, hajmi > 1024 bayt bo'lsa qayta nomlanadi.
- `KEEP_DAILY=7`, `KEEP_WEEKLY=5` (kun hisobida `*7`).
- `OFFSITE` (`/opt/applications/appctl.conf`): bo'sh bo'lsa offsite o'chiq; to'ldirilsa
  `rsync -a -e "ssh -o BatchMode=yes"` bilan butun papka yuboriladi (`--delete` yo'q).
- Cron: `15 3 * * * root /usr/local/bin/appctl backup all >> /var/log/appctl-backup.log 2>&1`.

Hozirgi holat: `OFFSITE` hali **sozlanmagan** (egasi "keyinroq" degan). Bu eng katta ochiq xavf
(R-001) va Nazoratchi'ning birinchi muhim tekshiruvlaridan biri bo'ladi.

## 2.7. systemd servislar (S-01)

| Servis | Vazifa | Foydalanuvchi | Holat |
|---|---|---|---|
| `avlo-contact` | avlo.ai kontakt formasi → Telegram (Node, 127.0.0.1:3017) | `avlo` | Ishlayapti |
| `nginx`, `docker`, `cron`, `ssh`, `fail2ban`(rejada) | Tizim servislari | root | Ishlayapti |

Eski serverdan ko'chirilishi kutilayotganlar: 2.4-bo'limga qarang.

## 2.8. Ma'lum xavflar (joriy)

| ID | Xavf | Ta'sir | Nazoratchi qanday yordam beradi |
|---|---|---|---|
| R-001 | Offsite zaxira yo'q | Server o'lsa, barcha ma'lumot yo'qoladi | FR-BKP-010..014 |
| R-002 | Kernel yangilanishi kutilmoqda; reboot o'tgan safar muammo keltirgan | Reboot'dan keyin server ko'tarilmasligi mumkin | FR-HST-009 "reboot kerak" + nazorat ro'yxati |
| R-003 | SSH faqat parol bilan, bruteforce ehtimoli | Server buzilishi | FR-HST-014 (SSH urinishlari soni), tavsiya: kalitga o'tish |
| R-004 | DNS bir necha provayderda, bir nechtasi mijoz qo'lida | Domen noto'g'ri IP ga qarab qoladi | FR-DNS-* |
| R-005 | Sertifikat yangilanishi (S-01 certbot, S-02 konteyner cron) xato bersa jim qoladi | Sayt "xavfsiz emas" | FR-TLS-* |
| R-006 | Bitta server — bitta nosozlik nuqtasi (SPOF) | Hamma loyiha to'xtaydi | Heartbeat + offsite |
| R-007 | Ko'chirilmagan loyihalar eski serverga bog'liq | Ular hozir ishlamayapti | Reyestrda ko'rinadi |
| R-008 | Docker log hajmi (limit endi qo'yilgan, lekin eski konteynerlar qayta yaratilmagan bo'lishi mumkin) | Disk to'lishi | FR-DKR-006 |
| R-009 | S-02 nginx.conf qayta yozilishi mumkin | asadbekashurov.uz ishlamay qoladi | FR-TLS/HTTP tekshiruvlari tezda ko'rsatadi |

## 2.9. Ma'lumot yig'ish buyruqlari (inventarni to'ldirish uchun)

Quyidagilarni har serverda bir marta bajarib, natijani reyestrga kiritish kerak:

```bash
hostnamectl --static
lscpu | grep -E 'Model name|^CPU\(s\)'
free -h | sed -n 2p
df -h / | tail -n 1
lsblk -o NAME,SIZE,TYPE,MOUNTPOINT
uname -r; cat /etc/os-release | grep PRETTY_NAME
docker --version; docker compose version
systemctl list-units --type=service --state=running --no-pager | head -n 40
crontab -l; ls /etc/cron.d
nginx -T 2>/dev/null | grep -E 'server_name|proxy_pass|root ' | sort -u
ls /etc/letsencrypt/live/
```
