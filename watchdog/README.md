# Nazoratchi watchdog

Core tirikligini **tashqaridan** tekshiruvchi kichik xizmat (FR-SYS-002, ADR-014). Faqat Python standart kutubxonasi.
Core evaluator'i har ≥60 s da `https://<watchdog-domen>/ping/<WATCHDOG_ID>` ga ping yuboradi (faqat muvaffaqiyatli
tsiklidan keyin). 5 daqiqa ping kelmasa — Telegram'ga (mustaqil bot) bitta alert, har 30 daqiqada eslatma, tiklanganda
"tiklandi" xabari. Holat diskda saqlanadi (qayta ishga tushganda soxta alert chiqmaydi).

## O'rnatish (S-01, core'dan BOSHQA server)

```bash
install -d /opt/nazoratchi-watchdog && cp -r watchdog/nazoratchi_watchdog /opt/nazoratchi-watchdog/
useradd --system --no-create-home --shell /usr/sbin/nologin nazoratchi-watchdog
install -m 0600 deploy/watchdog/nazoratchi-watchdog.env.example /etc/nazoratchi-watchdog.env   # to'ldiring
install -m 0644 deploy/watchdog/nazoratchi-watchdog.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now nazoratchi-watchdog
```

nginx (TLS bilan) faqat `location /ping/ { proxy_pass http://127.0.0.1:8099; }` ni oshkor qiladi.

## Tekshirish

```bash
set -a; . /etc/nazoratchi-watchdog.env; set +a
python3 -m nazoratchi_watchdog --check-config
python3 -m nazoratchi_watchdog --test-telegram
```

Qabul sinovi: core'ni to'xtating — 5–6 daqiqada xabar kelishi kerak (RB-012).

## Testlar

```bash
cd watchdog && uv run --with pytest --with ruff --with mypy sh -c 'ruff check . && mypy nazoratchi_watchdog tests && pytest -q'
```
