# Nazoratchi

Infratuzilma monitoringi platformasi: serverlar, loyihalar, zaxira nusxalar, sertifikat va domenlar
holatini bitta oynada ko'rsatadi va muammo haqida Telegram orqali xabar beradi.

- Texnik topshiriq: [`docs/TZ/`](docs/TZ/) (v1.17; `.docx`/`.pdf` ham shu yerda)
- Reja: [`docs/TZ/ROADMAP.md`](docs/TZ/ROADMAP.md) · Owner qarorlari: [`docs/TZ/QARORLAR.md`](docs/TZ/QARORLAR.md)
- F0 natijasi: [`docs/P-02-timescale-sinov.md`](docs/P-02-timescale-sinov.md) (protokol prototipi, R-102)

## Tuzilma

```
backend/      Django core (apps/, config/, tests/)
agent/        Go agenti (F1 dan)
prototype/    F0 prototip agenti (Python, psutil)
deploy/appctl-patches/   appctl ga o'zgartirishlar (E-01…E-03), asl skript va sinovlar bilan
frontend/     React panel (F1 dan)
deploy/       docker-compose, nginx, install.sh
docs/         TZ, ADR, runbook'lar
seed/         boshlang'ich reyestr (inventory.yaml)
.github/      CI
```

## Mahalliy ishga tushirish (backend)

Talab: Docker, [uv](https://docs.astral.sh/uv/).

```bash
docker compose -f deploy/docker-compose.dev.yml up -d   # TimescaleDB (127.0.0.1:5433) va Redis (6380)
cd backend
uv sync                                                  # bog'liqliklar (Python 3.13)
uv run pytest                                            # testlar
uv run ruff check . && uv run ruff format --check . && uv run mypy .
uv run python manage.py migrate
uv run python manage.py runserver                        # http://127.0.0.1:8000/healthz
```

Dev sozlamalari (`config.settings.dev`) standart qiymatlarga ega; prod uchun `.env.example` ga qarang.

## Frontend

```bash
cd frontend && npm ci && npm run dev    # http://localhost:5173 (/api va /healthz ni backend 127.0.0.1:8000 ga proksilaydi)
npm run lint && npm run typecheck && npm test && npm run build
```

## Prod'ga o'rnatish

1. Core serverini tayyorlang: [TZ 15.2](docs/TZ/15-deploy.md). `deploy/docker-compose.yml`, `deploy/bootstrap.sh` va
   `.env.example` (nusxa `.env`, rejim 0600) ni server papkasiga qo'ying.
2. `bash bootstrap.sh <owner-login>` — image'larni tortadi, migratsiya qiladi, Owner yaratadi, servislarni ko'taradi.
3. Host nginx: `deploy/nginx/nazoratchi.conf.template` (`envsubst`), so'ng `certbot --nginx`.
4. Watchdog (boshqa serverda): [`watchdog/README.md`](watchdog/README.md). Agent: panel bergan
   `curl -fsSL https://<core>/install.sh | sudo NAZORATCHI_ENROLL_TOKEN=... bash`.
5. Muammo bo'lsa: [`docs/runbooks/`](docs/runbooks/README.md).

Image'lar: `docker build -f backend/Dockerfile .` va `docker build -f frontend/Dockerfile .` (context — repo ildizi).
Release: `v*` tegi `.github/workflows/release.yml` ni ishga tushiradi (ghcr.io image'lari, minisign bilan imzolangan agent).

## CI

`.github/workflows/ci.yml`: backend, Go agent, frontend (lint, typecheck, test, build), prototip agent, xavfsizlik
(`pip-audit`, `govulncheck`), image build'lar, prod `compose`, shellcheck, nginx `-t` va `install.sh` funksional testi
(Debian konteyneri).
