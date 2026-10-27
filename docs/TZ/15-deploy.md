# 15. O'rnatish, deploy va ekspluatatsiya

## 15.1. Muhitlar

| Muhit | Maqsad | Qayerda | Ma'lumot |
|---|---|---|---|
| **dev** | Ishlab chiqish | Dasturchi kompyuteri (Docker Compose, `docker-compose.dev.yml`) | Sun'iy (generator) |
| **ci** | Avtomatik testlar | GitHub Actions ishchisi | Vaqtinchalik |
| **staging** (ixtiyoriy, F2) | Reliz oldi sinov, yuklama testi | Core bilan bir xil konfiguratsiyada kichik VPS yoki vaqtincha | Sinov agentlari + generator |
| **prod** | Haqiqiy monitoring | S-00 (15.2) | Haqiqiy |

Tavsiya: staging alohida VPS sifatida doimiy bo'lmasligi mumkin; yuklama testi vaqtida
vaqtincha ko'tarib, tugagach o'chirish yetarli (xarajatni tejash).

## 15.2. Core serverini tayyorlash (S-00)

> **Owner qarori (2026-10-26).** Core S-00 da (`185.214.135.9`, Contabo, 200 GB SSD). Server tozalanib
> Ubuntu 24.04 bilan yangidan o'rnatiladi; u oldin yuklanmagan (1.3.1), shu sabab o'rnatishdan keyin
> darhol provayder snapshoti olinadi. S-01 uchun offsite zaxira ham shu serverda; watchdog esa S-01 da.
> `retired_ips` dan bu IP olib tashlanadi; unga qaragan eski DNS yozuvlari (masalan, `avloai.uz`)
> ko'chiriladi, nginx'da `default_server` `return 444` bo'ladi.

### 15.2.1. Talablar

| Parametr | Minimal | Tavsiya |
|---|---|---|
| OS | Ubuntu 24.04 LTS | Ubuntu 24.04 LTS |
| CPU / RAM | 2 vCPU / 4 GB | 2–4 vCPU / 4–8 GB |
| Disk | 40 GB SSD | 80 GB SSD |
| Tarmoq | Statik ommaviy IPv4 | + IPv6 |
| Joylashuv | Kuzatiladigan serverlardan **boshqa server**, imkon bo'lsa boshqa provayder | — |
| Domen | `nazoratchi.<domen>` (A yozuvi shu serverga) | — |

### 15.2.2. Boshlang'ich sozlash (bir marta)

```bash
# 1. Tizim
apt-get update && apt-get -y upgrade
timedatectl set-timezone UTC          # server vaqti UTC da
apt-get install -y ufw fail2ban unattended-upgrades curl ca-certificates gnupg nginx certbot python3-certbot-nginx

# 2. Foydalanuvchi va SSH (parolsiz, kalit bilan)
adduser --disabled-password --gecos "" ops
usermod -aG sudo ops
mkdir -p /home/ops/.ssh && cp ~/.ssh/authorized_keys /home/ops/.ssh/ && chown -R ops:ops /home/ops/.ssh
printf 'PasswordAuthentication no\nPermitRootLogin no\n' > /etc/ssh/sshd_config.d/00-hardening.conf
sshd -t && systemctl reload ssh      # YANGI terminalda ops bilan kirib tekshiring, keyin sessiyani yoping

# 3. Firewall
ufw allow 22/tcp && ufw allow 80/tcp && ufw allow 443/tcp && ufw --force enable

# 4. Docker
curl -fsSL https://get.docker.com | sh
cat > /etc/docker/daemon.json <<'EOF'
{ "log-driver": "json-file", "log-opts": { "max-size": "10m", "max-file": "3" }, "live-restore": true }
EOF
systemctl restart docker

# 5. appctl va papkalar (mavjud deploy/server/setup.sh bilan)
bash setup.sh --fail2ban
```

> **Muhim (L-4 saboqi):** `unattended-upgrades` yangi kernel o'rnatishi mumkin. Avtomatik reboot
> **o'chiq** bo'lishi kerak (`Unattended-Upgrade::Automatic-Reboot "false"`); reboot rejalashtirilgan
> oynada, snapshotdan keyin qo'lda bajariladi. Nazoratchi `reboot_required` ni alert qiladi
> (AL-032, AL-033).

### 15.2.3. Papkalar

```
/opt/applications/
  projects/Nazoratchi/            # compose, .env, .appctl
    docker-compose.yml
    .env                       # maxfiy (0600)
    .appctl
    nginx/                     # (ixtiyoriy) konteyner ichidagi konfiglar
  nginx/nazoratchi.<domen>.conf   # host nginx konfigi
  backups/Nazoratchi/             # appctl zaxiralari
/etc/nazoratchi/master.key        # 0400 (yoki .env ichida)
```

## 15.3. Repozitoriy tuzilmasi

```
nazoratchi/                       # monorepo
  backend/                     # Django loyihasi (6.4-bo'lim)
    apps/ workers/ config/ tests/
    pyproject.toml uv.lock
  frontend/                    # React (13.13)
  agent/                       # Go agenti
    cmd/nazoratchi-agent/ internal/collectors/ internal/sender/ ...
    go.mod
  deploy/
    docker-compose.yml         # prod
    docker-compose.dev.yml
    nginx/nazoratchi.conf.template
    install.sh                 # agent o'rnatuvchi (shablon)
    appctl-patches/            # appctl ga o'zgarishlar (10.3)
  docs/
    TZ/                        # shu hujjat
    runbooks/                  # RB-001 ... (18.2)
    adr/                       # arxitektura qarorlari
  seed/inventory.yaml          # boshlang'ich reyestr (8.11, 18.5)
  .github/workflows/           # CI/CD
```

## 15.4. Docker Compose (prod)

`/opt/applications/projects/Nazoratchi/docker-compose.yml`:

```yaml
name: nazoratchi

x-app: &app
  image: ghcr.io/${GHCR_OWNER}/nazoratchi-backend:${NAZORATCHI_VERSION}
  env_file: .env
  restart: unless-stopped
  depends_on:
    db:    { condition: service_healthy }
    redis: { condition: service_healthy }
  logging:
    driver: json-file
    options: { max-size: "10m", max-file: "3" }

services:
  db:
    image: timescale/timescaledb:2.17.2-pg16        # versiya reliz oldidan tekshiriladi
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${DB_NAME}
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - nazoratchi_pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER} -d ${DB_NAME}"]
      interval: 10s
      timeout: 5s
      retries: 10
    shm_size: 256mb
    command: >
      postgres -c shared_buffers=512MB -c effective_cache_size=1536MB
               -c max_connections=60 -c work_mem=16MB
               -c timescaledb.max_background_workers=8
               -c shared_preload_libraries=timescaledb

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    command: ["redis-server", "--save", "", "--appendonly", "no", "--maxmemory", "256mb", "--maxmemory-policy", "allkeys-lru"]
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 10

  web:
    <<: *app
    command: ["uvicorn", "config.asgi:application", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers"]
    ports: ["127.0.0.1:8040:8000"]
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz').status==200 else 1)"]
      interval: 15s
      timeout: 5s
      retries: 5

  evaluator:
    <<: *app
    command: ["python", "-m", "workers.evaluator"]

  prober:
    <<: *app
    command: ["python", "-m", "workers.prober"]

  notifier:                              # navbatdagi bildirishnomalarni yuboradi (S3 da evaluator ichiga o'tishi mumkin)
    <<: *app
    command: ["python", "manage.py", "notify_worker"]

  worker:
    <<: *app
    command: ["celery", "-A", "config", "worker", "-l", "info", "--concurrency", "2"]

  beat:
    <<: *app
    command: ["celery", "-A", "config", "beat", "-l", "info", "--schedule", "/data/celerybeat-schedule"]
    volumes:
      - nazoratchi_beat:/data

  frontend:
    image: ghcr.io/${GHCR_OWNER}/nazoratchi-frontend:${NAZORATCHI_VERSION}
    restart: unless-stopped
    ports: ["127.0.0.1:3040:80"]

volumes:
  nazoratchi_pgdata:
  nazoratchi_beat:
```

Eslatmalar:
- Portlar faqat `127.0.0.1` ga (Docker nashri `ufw` ni chetlab o'tadi).
- `evaluator` va `prober` **bitta nusxada** ishlaydi (`replicas` yo'q). Ikkinchi nusxa
  tasodifan ishga tushsa, takroriy alert bo'lmasligi uchun baza darajasidagi `advisory lock`
  bilan "leader" tanlanadi (6.2).
- `web`, `worker`, `evaluator`, `prober` bir image'dan, buyruqlari farqli.
- Migratsiyalar `deploy` paytida alohida bir martalik buyruq bilan (15.7).

## 15.5. Muhit o'zgaruvchilari (`.env`)

`.env.example` (qiymatlar o'rniga izoh; **haqiqiy qiymatlar repoda yo'q**):

| O'zgaruvchi | Misol / format | Izoh |
|---|---|---|
| `NAZORATCHI_VERSION` | `1.0.0` | Image tegi |
| `GHCR_OWNER` | `<tashkilot>` | Registry egasi |
| `DJANGO_SETTINGS_MODULE` | `config.settings.prod` | |
| `SECRET_KEY` | 50+ belgi, tasodifiy | Django |
| `ALLOWED_HOSTS` | `nazoratchi.example.uz` | Vergul bilan. Prod sozlamasi `127.0.0.1` va `localhost` ni o'zi qo'shadi: konteyner healthcheck va host watchdog `/healthz` ga shu orqali kiradi (aks holda 400) |
| `CSRF_TRUSTED_ORIGINS` | `https://nazoratchi.example.uz` | |
| `PUBLIC_URL` | `https://nazoratchi.example.uz` | Alert havolalari, install buyrug'i |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST=db`, `DB_PORT=5432` | | Bazaga ulanish |
| `REDIS_URL` | `redis://redis:6379/0` | |
| `NAZORATCHI_MASTER_KEY` | base64, 32 bayt | Maxfiy maydonlarni shifrlash (14.6). **Majburiy**: yo'q yoki 32 bayt emas bo'lsa core ishga tushmaydi |
| `TELEGRAM_API_BASE` | `https://api.telegram.org` | Ixtiyoriy; faqat sinov uchun (soxta Bot API) |
| `TZ_DEFAULT` | `Asia/Tashkent` | UI uchun standart zona |
| `TELEGRAM_BOT_TOKEN` | `<TOKEN>` | **Faqat boshlang'ich**; keyin panel orqali kanalda saqlanadi (shifrlangan) |
| `TELEGRAM_WEBHOOK_SECRET` | tasodifiy | Webhook yo'li va sarlavha |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | | Email kanal (ixtiyoriy) |
| `WATCHDOG_URL` | `https://watchdog.example.uz/ping/<id>` | S-01 dagi watchdog (FR-SYS-002) |
| `RETIRED_IPS` | `34.173.220.247` | DNS "yopilgan IP" ro'yxati (11.4.2) |
| `RETENTION_RAW_DAYS` | `14` | 8.10 |
| `RETENTION_1M_DAYS` | `90` | |
| `RETENTION_5M_DAYS` | `365` | |
| `RETENTION_1H_DAYS` | `1095` | |
| `INGEST_MAX_BODY_BYTES` | `1048576` | |
| `LOG_LEVEL` | `INFO` | |
| `SENTRY_DSN` | bo'sh | Ixtiyoriy |

Qoida: `.env` fayli rejimi `0600`, egasi — deploy foydalanuvchisi; repoda yo'q; zaxirada
shifrlangan holda.

## 15.6. Host nginx (core)

`/opt/applications/nginx/nazoratchi.example.uz.conf` (HTTP qismini certbot to'ldiradi):

```nginx
limit_req_zone $binary_remote_addr zone=nzr_login:10m rate=10r/m;
limit_req_zone $http_authorization zone=nzr_ingest:10m rate=30r/m;
limit_req_zone $binary_remote_addr zone=nzr_api:10m rate=20r/s;

server {
    server_name nazoratchi.example.uz;
    server_tokens off;

    # Xavfsizlik sarlavhalari (14.8.2)
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options nosniff always;
    add_header X-Frame-Options DENY always;
    add_header Referrer-Policy same-origin always;
    add_header Content-Security-Policy "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'" always;

    client_max_body_size 2m;

    location /ingest/ {
        limit_req zone=nzr_ingest burst=10 nodelay;
        proxy_pass http://127.0.0.1:8040;
        include /etc/nginx/proxy_params;
    }
    location /hb/ {
        limit_req zone=nzr_ingest burst=10 nodelay;
        proxy_pass http://127.0.0.1:8040;
        include /etc/nginx/proxy_params;
    }
    location /api/v1/auth/login {
        limit_req zone=nzr_login burst=5 nodelay;
        proxy_pass http://127.0.0.1:8040;
        include /etc/nginx/proxy_params;
    }
    location /api/v1/stream {                      # SSE: buferlashsiz
        proxy_pass http://127.0.0.1:8040;
        include /etc/nginx/proxy_params;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_read_timeout 1h;
    }
    location /api/ {
        limit_req zone=nzr_api burst=40 nodelay;
        proxy_pass http://127.0.0.1:8040;
        include /etc/nginx/proxy_params;
    }
    location ~ ^/(healthz|install\.sh|agent/) {
        proxy_pass http://127.0.0.1:8040;
        include /etc/nginx/proxy_params;
    }
    location /metrics { allow 127.0.0.1; deny all; proxy_pass http://127.0.0.1:8040; }

    location / {                                   # SPA
        proxy_pass http://127.0.0.1:3040;
        include /etc/nginx/proxy_params;
    }

    listen 80;
}
# certbot --nginx -d nazoratchi.example.uz  → 443 va yo'naltirishni o'zi qo'shadi
```

`/etc/nginx/proxy_params` standart: `Host`, `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto`.
Eslatma: `limit_req` kaliti `$http_authorization` — agent tokeni bo'yicha chegara.

## 15.7. Birinchi ishga tushirish (bootstrap)

1. DNS: `nazoratchi.example.uz` A → S-00 IP (`185.214.135.9`); `appctl nginx`; `certbot --nginx -d ...`.
2. `docker compose pull && docker compose up -d db redis`.
3. Migratsiya (bir martalik): `docker compose run --rm web python manage.py migrate`.
4. Birinchi Owner yaratish: `docker compose run --rm web python manage.py createowner --login jasur`
   (parol terminalda so'raladi; skriptda saqlanmaydi).
5. `docker compose up -d` (hamma servis).
6. Boshlang'ich reyestr: `manage.py seed_inventory seed/inventory.yaml --dry-run`, so'ng haqiqiy.
7. Panelga kirish (HTTPS), 2FA yoqish (Owner uchun majburiy).
8. Telegram kanalini sozlash va **sinov xabari** (FR-ALR-020).
9. Watchdog S-01 da o'rnatiladi (alohida bot, systemd, nginx qoidasi va subdomen; `appctl` ga tegilmaydi);
   `WATCHDOG_URL` shunga qaratiladi; sinov: core'ni to'xtatib, 5–6 daqiqada xabar kelishini tekshirish.
   Telegram'da zaxira uchun `age` kalit jufti yaratiladi (maxfiy kalit parol menejeriga) va birinchi sinov zaxira yuboriladi.
10. Birinchi agent (S-00, core'ning o'zi va offsite papka; keyin S-02) — UC-01; panelda "Onlayn" ni tekshirish.
11. `appctl` ga Nazoratchi `.appctl` yozish va `appctl backup Nazoratchi`.

## 15.8. Agentlarni mavjud serverlarga tarqatish

Tartib — kamroq xavfdan ko'proqqa:

| Qadam | Server | Sabab | Tekshiruv |
|---|---|---|---|
| 1 | S-00 (core + offsite) | Yangi o'rnatilgan, ishlab turgan loyiha yo'q | Agent ishlaydi, zaxira skaneri bo'sh papkada xatosiz; disk/RAM ko'rinadi |
| 2 | S-02 (vmd208589) | Aaclub staging bor; Docker bor; resurs katta | Docker proksi ishlaydi; `nginx.conf` ga tegilmadi |
| 3 | S-01 (main-2) | Asosiy server | Yuk oshmadi (CPU ≤ +1%); 24 soat kuzatuv |

S-01 uchun qo'shimcha oldi shartlar:
- `appctl` ga `state.json`/`_run.json`/`--json` o'zgartirishlari o'rnatiladi (10.3) va bir marta
  `appctl backup all` bilan tekshiriladi.
- `docker-socket-proxy` konteyneri `127.0.0.1:2375` ga (faqat GET).
- ACL: `setfacl -R -m u:nazoratchi:rX /opt/applications/backups` (zaxira papkasi);
  `/etc/letsencrypt` uchun deploy-hook (7.7.2 eslatmasi).
- `nazoratchi` foydalanuvchisi `docker` guruhida **emas**.
- Cron'larga heartbeat qo'shiladi (`appctl-backup`, `certbot-renew`).

S-02 uchun ehtiyot choralari:
- `/etc/nginx/nginx.conf` front-proksiga **tegilmaydi**. Agent faqat o'qiydi.
- `asadbekashurov-certbot` cron'iga heartbeat qo'shish — `/etc/cron.d/asadbekashurov-certbot` ni tahrirlash (faqat shu fayl).

## 15.9. Nazoratchi'ni tiklash (yangi serverda) — RB-044

Maqsad: RTO ≤ 1 soat (NFR-REL-006).

1. Yangi server (15.2) — 20 daqiqa.
2. `docker` va `appctl` tayyor; `Nazoratchi` papkasini yaratish; eng yangi zaxirani Owner'ning Telegram
   chatidan yuklab olish va `age` maxfiy kaliti (parol menejeridan) bilan ochish.
3. `.env` ni tiklash (shifrlangan zaxiradan) **va `master.key`** ni parol menejeridan.
4. `docker compose up -d db`, bazani tiklash: `appctl restore Nazoratchi <fayl.sql.gz> --yes`
   (yangi bo'sh serverda — xavfsiz).
5. `docker compose up -d` (hammasi).
6. DNS: `nazoratchi.example.uz` yangi IP ga (TTL kichik bo'lishi uchun doimiy 300 s).
7. Agentlar yangi core'ga ulanadi (domen o'zgarmagani uchun avtomatik); buferdagi ma'lumot yuboriladi.
8. Sinov: panel ochiladi, reyestr to'liq, sinov alerti keladi.
9. Natija va vaqt — drill jurnaliga.

## 15.10. CI/CD (GitHub Actions)

### 15.10.1. Pipeline bosqichlari

| Bosqich | Qachon | Nima qiladi | Muvaffaqiyatsiz bo'lsa |
|---|---|---|---|
| `lint` | Har PR/push | `ruff`, `mypy`, `eslint`, `tsc --noEmit`, `go vet`, `staticcheck` | Birlashtirish bloklanadi |
| `test-backend` | Har PR/push | `pytest` (Timescale konteyneri bilan), qamrov hisoboti | Bloklanadi |
| `test-frontend` | Har PR/push | `vitest`; `playwright` (asosiy oqimlar) | Bloklanadi |
| `test-agent` | Har PR/push | `go test ./...` (fixtures bilan), amd64+arm64 cross-compile | Bloklanadi |
| `security` | Har PR/push + haftalik | `pip-audit`, `npm audit`, `govulncheck`, `trivy fs` | Jiddiy zaiflikda bloklanadi |
| `build` | `main` ga birlashganda | Docker image'lar (backend, frontend), `nazoratchi-agent` binarlari, SBOM | — |
| `sign` | Reliz tegida (`v*`) | Agent binarlarini `minisign` bilan imzolash (maxfiy kalit CI sirida) | Reliz to'xtaydi |
| `release` | Reliz tegida | GitHub Release, image'larni `ghcr.io` ga, agent artefaktlarini core'ga yuklash uchun paket | — |
| `deploy-prod` | Qo'lda (`workflow_dispatch`) yoki reliz tasdiqlangach | `ssh` orqali: `appctl deploy Nazoratchi` (15.11) | Avtomatik rollback (15.11.3) |

### 15.10.2. Namuna workflow qismi (test-backend)

```yaml
name: ci
on: [push, pull_request]
jobs:
  test-backend:
    runs-on: ubuntu-24.04
    services:
      db:
        image: timescale/timescaledb:2.17.2-pg16
        env: { POSTGRES_PASSWORD: ci, POSTGRES_DB: nazoratchi }
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U postgres" --health-interval 5s --health-retries 10
      redis:
        image: redis:7-alpine
        ports: ["6379:6379"]
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --frozen
        working-directory: backend
      - run: uv run ruff check . && uv run mypy apps
        working-directory: backend
      - run: uv run pytest --cov=apps --cov-fail-under=70
        working-directory: backend
        env:
          DB_HOST: localhost
          DB_PASSWORD: ci
          REDIS_URL: redis://localhost:6379/0
```

Sirlar (GitHub Secrets): `MINISIGN_KEY`, `GHCR_TOKEN`, `DEPLOY_SSH_KEY` (faqat deploy
foydalanuvchisi, cheklangan `command=`), `DEPLOY_HOST`. Maxfiy qiymatlar loglarga chiqmaydi.

## 15.11. Yangilash (deploy) tartibi

### 15.11.1. Oddiy yangilash (backend/frontend)

1. Oldindan: oxirgi zaxira yangi (`appctl backup Nazoratchi`), ochiq `critical` incident yo'q.
2. `NAZORATCHI_VERSION` ni yangilash (`.env`), `docker compose pull`.
3. Migratsiyalar: `docker compose run --rm web python manage.py migrate --noinput`
   (orqaga qaytariladigan; katta jadvallarda `CONCURRENTLY` va `atomic = False`).
4. `docker compose up -d --remove-orphans` (`appctl deploy Nazoratchi` shuni bajaradi).
5. Health check: `/healthz` 200, `evaluator_heartbeat` yangilanyapti, sinov ingest 200.
6. Kuzatuv: 15 daqiqa xatolar yo'qligini ko'rish (panel → "Tizim holati").

**Uzilish:** `web` qayta ishga tushganda ingest 5–10 soniya javob bermaydi; agent buferi
buni qoplaydi (NFR-REL-002). Alert hisoblash 15–30 soniya to'xtaydi (bir martalik `for` siljishi).

### 15.11.2. Agent reliz tarqatish

1. Yangi agent binari core'ga `/agent/v1/` ga yuklanadi (CI imzolagan).
2. Core `latest` ni yangilaydi; hostlar `update` buyrug'ini **bosqichma-bosqich** oladi:
   avval 1 ta (S-00), 1 soat kutish, so'ng qolganlari.
3. Agent o'zini yangilaydi, imzoni tekshiradi, rollback himoyasi bilan (7.7.3).

### 15.11.3. Rollback

- Backend: oldingi `NAZORATCHI_VERSION` ga qaytish va `docker compose up -d`. Migratsiya orqaga
  qaytariladigan bo'lsa, `migrate <app> <oldingi_raqam>`; aks holda (nisbatan kam hollarda) —
  bazani oldindan olingan zaxiradan tiklash (RTO ichida).
- Agent: `.old` binarga avtomatik qaytish (7.7.3), yoki core'da `latest` ni oldingi versiyaga
  o'rnatib `update` yuborish (versiya pasaytirish uchun maxsus bayroq kerak — 14.5.4).

## 15.12. Ekspluatatsiya: davriy vazifalar

| Davriylik | Vazifa | Kim |
|---|---|---|
| Doimiy | Alertlarga javob | Operator/Owner |
| Kunlik (avtomatik) | Zaxira (03:15), retention, kunlik hisobot (08:00) | Tizim |
| Haftalik | Haftalik hisobotni ko'rish; ochiq doimiy ogohlantirishlarni tahlil qilish; `docker image prune` kerakmi | Operator |
| Oylik | Alert sifatini ko'rib chiqish (12.11); bog'liqlik yangilanishlari; disk/baza hajmi tendensiyasi; sertifikat va domen muddatlari | Operator |
| Chorak | Restore drill (har loyiha); Nazoratchi'ni tiklash mashqi (15.9); agent token rotatsiyasini ko'rib chiqish | Operator |
| Yillik | `master.key` va tokenlar rotatsiyasi; xavfsizlik tekshiruvi (14.13); Timescale/Postgres/Docker katta yangilanishlari rejasi | Owner |

## 15.13. Monitoring monitoringi

| Nimani | Kim kuzatadi | Qanday |
|---|---|---|
| Core ishlayaptimi | Watchdog (S-01) | Core har 60 s ping; 5 daq. kelmasa Telegram |
| Core host (disk/RAM) | Core'dagi agent (o'zini kuzatadi) + watchdog (to'liq uzilish uchun) | AL-019..AL-023, AL-014/015 |
| Alert dvigateli | `evaluator_heartbeat` | AL-084 |
| Bildirishnoma | `notifications` xato soni | AL-086 |
| Zaxira | Nazoratchi'ning o'z `BACKUP` qoidalari | AL-068.. |

**Muhim cheklov:** Core to'liq o'lsa, alertlar uni kuzatuvchi watchdog'dan boshqa joydan
kelmaydi. Shu sababli watchdog (a) core'dan alohida serverda (S-01), (b) alohida Telegram botida
bo'lishi shart (ADR-014). O'zaro kuzatuv: S-01 ni core kuzatadi. Ikkalasi bir vaqtda tushsa
(bir provayder) xabar bo'lmaydi (RS-06).

## 15.14. Masshtablash bosqichlari

| Belgi | Choralar |
|---|---|
| Baza hajmi > 80% byudjetdan | Retention qisqartirish (xom 14 → 7 kun), `rollup=false` metrikalarni agregatlamaslik, diskni oshirish |
| Ingest p95 > 300 ms | `web` workerlarini 2 → 4; `db` `shared_buffers`; indeks tekshiruvi |
| 30+ host | Core: 4 vCPU / 8 GB; Timescale chunk intervalini ko'rib chiqish |
| 100+ host | Ingest'ni alohida `ingest` servisga ajratish (gorizontal), agent paketlarini Redis navbatiga; alohida DB serveri |
| Core ishonchliligi talabi oshsa | Ikkinchi core (replika, X-6 qamrovdan chiqarilgan: alohida loyiha) |

## 15.15. Tizimni to'xtatish (decommission)

1. Barcha agentlarda `nazoratchi-agent uninstall`.
2. Ma'lumotni eksport (reyestr YAML, incident tarixi, audit CSV) va arxivlash.
3. Core'ni to'xtatish; DNS yozuvini o'chirish; `master.key` va maxfiy qiymatlarni yo'q qilish.
4. Telegram botini o'chirish yoki tokenni bekor qilish.
5. Watchdog'ni to'xtatish.

## 15.16. Qabul sinovlari (o'rnatish)

| № | Sinov | Kutilgan natija |
|---|---|---|
| T-DEP-01 | Toza Ubuntu 24.04 da 15.2 + 15.7 | 60 daqiqada ishlaydigan panel |
| T-DEP-02 | Server reboot | 3 daqiqada barcha servis ko'tariladi, qo'lda aralashuvsiz (NFR-REL-009) |
| T-DEP-03 | Yangilash (15.11.1) | Ma'lumot yo'qolmaydi; agent buferi qoplaydi |
| T-DEP-04 | Migratsiya xato bilan to'xtasa | Eski versiyaga qaytish ishlaydi |
| T-DEP-05 | Tiklash (15.9) | RTO ≤ 60 daqiqa, reyestr to'liq |
| T-DEP-06 | Agent o'rnatish 3 serverda | Hammasi onlayn; S-01 da yuk ortishi ≤ 1% |
| T-DEP-07 | CI pipeline: PR → build → release → imzolangan agent | Imzo tekshiruvidan o'tadi |
| T-DEP-08 | Core uzoq o'chiq (30 daq) → qayta yoqish | Agent buferi bo'shliqsiz yuboriladi |
