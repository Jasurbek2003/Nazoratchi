# Yuklama simulyatori (TZ 16.9)

Virtual agentlar core'ga `POST /ingest/v1/metrics` orqali haqiqiy hajmdagi (~190 namuna) gzip paketlar yuboradi.
Faqat Python stdlib. Mezon buzilsa chiqish kodi `1`.

```bash
# 1. Har virtual agent uchun server va token (dev bazada):
cd backend
for i in $(seq 1 10); do uv run python manage.py create_server "sim-$i"; done   # tokenlarni tokens.txt ga yig'ing

# 2. Yuklash (T-P-01: interval 15 s, 1 soat; qisqa sinov uchun interval kichik):
python tools/simulator/simulate.py --url http://127.0.0.1:8000 --tokens-file tokens.txt \
    --duration 3600 --interval 15 --pattern daily
```

Naqshlar: `steady`, `daily`, `spike`, `sustained_high`, `mem_leak`, `disk_growth`. Mezonlar: p95 ≤ 300 ms, p99 ≤ 1 s,
xato 0% (`--p95-ms`, `--p99-ms` bilan o'zgartiriladi). Tezlik chegarasi token bo'yicha 30/daq, shuning uchun interval
2 s dan kichik bo'lmasin. Sinovdan keyin `sim-*` serverlarini panel orqali arxivlang.
