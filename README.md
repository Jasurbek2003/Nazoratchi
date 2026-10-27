# Nazoratchi

Infratuzilma monitoringi platformasi: serverlar, loyihalar, zaxira nusxalar, sertifikat va domenlar
holatini bitta oynada ko'rsatadi va muammo haqida Telegram orqali xabar beradi.

- Texnik topshiriq: [`docs/TZ/`](docs/TZ/) (v1.7; `.docx`/`.pdf` ham shu yerda)
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

## CI

`.github/workflows/ci.yml`: backend va prototip agent (ruff, mypy, pytest, qamrov ≥ 70%),
xavfsizlik (`pip-audit`), `compose` konfiguratsiyasi. Agent va frontend ishlari F1 da qo'shiladi.
