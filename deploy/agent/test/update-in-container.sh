#!/usr/bin/env bash
# `shart && ok ... || bad ...`: ok va bad hech qachon xato qaytarmaydi, shuning uchun SC2015 xavfi yo'q.
# shellcheck disable=SC2015
# O'z-o'zini yangilash e2e (FR-AGT-008, NFR-SEC-012): haqiqiy `minisign`, haqiqiy agent binari, soxta core.
# Debian konteyner ichida root sifatida; ishga tushirish: ../test.sh
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq >/dev/null
apt-get install -y -qq minisign python3 >/dev/null

W=/tmp/u
BIN=/usr/local/bin/nazoratchi-agent
STAGE=/var/lib/nazoratchi/update
STATE=/var/lib/nazoratchi-update
rm -rf "$W" "$STAGE" "$STATE" && mkdir -p "$W/dist" "$W/evil" "$W/queue" /usr/local/bin "$(dirname "$STAGE")" "$STATE"
chmod 0755 "$STATE"
ARCH="$(cd /src/agent && go env GOARCH)"

# 1. Kalitlar, ikkita binar (1.0.0 eski, 1.1.0 yangi), imzolangan reliz
minisign -G -W -p "$W/pub" -s "$W/sec" >/dev/null
minisign -G -W -p "$W/evil.pub" -s "$W/evil.sec" >/dev/null
PUB="$(tail -n1 "$W/pub")"
build() { (cd /src/agent && CGO_ENABLED=0 go build -buildvcs=false -ldflags "-X main.version=$1 -X main.releasePubKey=$PUB" -o "$2" ./cmd/nazoratchi-agent); }
build 1.0.0 "$W/agent-1.0.0"
build 1.1.0 "$W/dist/nazoratchi-agent-$ARCH"
echo "1.1.0" > "$W/dist/VERSION"
(cd "$W/dist" && sha256sum VERSION "nazoratchi-agent-$ARCH" > SHA256SUMS && minisign -S -s "$W/sec" -m SHA256SUMS -x SHA256SUMS.minisig >/dev/null)
# Begona kalit bilan imzolangan to'plam (xuddi shu fayllar)
cp "$W/dist/VERSION" "$W/dist/SHA256SUMS" "$W/dist/nazoratchi-agent-$ARCH" "$W/evil/"
(cd "$W/evil" && minisign -S -s "$W/evil.sec" -m SHA256SUMS -x SHA256SUMS.minisig >/dev/null)
echo "$W/dist" > "$W/serve_dir"
NEWSHA="$(sha256sum "$W/dist/nazoratchi-agent-$ARCH" | awk '{print $1}')"
printf '[{"type":"update","version":"1.1.0","sha256":"%s","url":"/agent/v1/nazoratchi-agent-%s"}]' "$NEWSHA" "$ARCH" > "$W/commands.json"

# 2. Soxta core: /agent/v1/* fayllar va /ingest/v1/metrics (har javobda update buyrug'i)
cat > "$W/core.py" <<'PY'
import http.server, json, os
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        d = open("/tmp/u/serve_dir").read().strip()
        p = os.path.join(d, self.path.rsplit("/", 1)[-1])
        if not self.path.startswith("/agent/v1/") or not os.path.isfile(p):
            self.send_response(404); self.end_headers(); return
        b = open(p, "rb").read()
        self.send_response(200); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        body = json.dumps({"ok": True, "accepted": 1, "rejected": 0, "duplicate": False, "clock_skew": False,
                           "server_time": "2026-11-01T12:00:00.000Z", "interval_seconds": 15,
                           "commands": json.load(open("/tmp/u/commands.json"))}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self, *a): pass
http.server.HTTPServer(("127.0.0.1", 8081), H).serve_forever()
PY
AGENT=""
python3 "$W/core.py" & CORE=$!
trap 'kill "$CORE" 2>/dev/null || true; [ -z "$AGENT" ] || kill "$AGENT" 2>/dev/null || true' EXIT
sleep 1

# 3. Agent sozlamasi (faqat system kollektori) va `install.sh` dagi aynan shu ExecStartPre o'rovi
printf 'tok\n' > "$W/token" && chmod 0600 "$W/token"
cat > "$W/agent.yaml" <<YAML
core:
  url: "http://localhost:8081"
  token_file: "$W/token"
queue:
  dir: "$W/queue"
collectors:
  system: { enabled: true, interval: 5s }
  disk: { enabled: false }
  diskio: { enabled: false }
  net: { enabled: false }
  docker: { enabled: false }
  systemd: { enabled: false }
  backup: { enabled: false }
  certs: { enabled: false }
  ssh: { enabled: false }
  apt: { enabled: false }
  reboot: { enabled: false }
YAML
sed -n "/<<'PRESTARTEOF'/,/^PRESTARTEOF/p" /src/deploy/agent/install.sh | sed '1d;$d' > "$W/prestart.sh"
[ -s "$W/prestart.sh" ] || { echo "FAIL install.sh da o'rov skripti topilmadi"; exit 1; }

fails=0
ok() { echo "OK   $*"; }
bad() { echo "FAIL $*"; fails=$((fails + 1)); }
ver() { "$BIN" version | awk '{print $2}'; }
start_agent() { "$BIN" run --config "$W/agent.yaml" >"$W/$1.log" 2>&1 & AGENT=$!; }
# wait_until <funksiya> <soniya>: funksiya 0 qaytarguncha kutadi
wait_until() { for _ in $(seq 1 "$2"); do "$1" && return 0; sleep 1; done; return 1; }
agent_gone() { ! kill -0 "$AGENT" 2>/dev/null; }
new_confirmed() { grep -qx 1.1.0 "$STAGE/confirmed" 2>/dev/null; }
reset_state() { rm -rf "$STAGE" "${STATE:?}"/* "${W:?}/queue"/*; }

# ---- A. Muvaffaqiyatli yangilanish ----
install -m 0755 "$W/agent-1.0.0" "$BIN"
[ "$(ver)" = "1.0.0" ] && ok "boshlang'ich versiya 1.0.0" || bad "boshlang'ich versiya"
start_agent a1
if wait_until agent_gone 90; then
  wait "$AGENT" && ok "agent yangilanishni yuklab, toza (kod 0) chiqdi" || bad "agent nol bo'lmagan kod bilan chiqdi"
else
  bad "agent 90 s da chiqmadi"; kill "$AGENT" 2>/dev/null || true
fi
[ -f "$STAGE/staged" ] && ok "staged belgisi yozildi" || bad "staged belgisi yo'q"
sh "$W/prestart.sh" >"$W/pre1.log" 2>&1 || bad "o'rov skripti xato berdi"
[ "$(ver)" = "1.1.0" ] && ok "ExecStartPre binarni 1.1.0 ga almashtirdi" || bad "binar almashtirilmadi: $(ver)"
[ -f "$BIN.old" ] && [ -f "$STATE/pending.json" ] && ok ".old zaxira va pending.json bor" || bad ".old/pending.json yo'q"
[ ! -e "$STAGE/staged" ] && ok "staged to'plam tozalandi" || bad "staged qoldi"

# Yangi agent: core hali ham update 1.1.0 yuboradi -> "allaqachon shu versiya" deb rad etiladi, qayta ishga tushish halqasi yo'q
start_agent a2
if wait_until new_confirmed 60; then ok "yangi agent birinchi paketni yubordi va tasdiq yozdi"; else bad "tasdiq yozilmadi"; fi
kill -0 "$AGENT" 2>/dev/null && ok "yangilanishdan keyin agent ishlashda davom etmoqda (halqa yo'q)" || bad "agent to'xtab qoldi"
grep -q "yangilanish rad etildi" "$W/a2.log" && ok "bir xil versiya buyrug'i rad etildi" || bad "bir xil versiya rad etilmadi"
kill "$AGENT" 2>/dev/null || true; wait "$AGENT" 2>/dev/null || true
sh "$W/prestart.sh" >"$W/pre2.log" 2>&1
[ "$(ver)" = "1.1.0" ] && [ ! -e "$STATE/pending.json" ] && ok "tasdiqlangan yangilanish saqlandi, pending tozalandi" || bad "tasdiqdan keyin holat noto'g'ri"

# ---- B. Tasdiqlanmagan yangilanish qaytariladi va qayta urinilmaydi ----
reset_state
install -m 0755 "$W/agent-1.0.0" "$BIN"
start_agent b1
wait_until agent_gone 90 || kill "$AGENT" 2>/dev/null || true
wait "$AGENT" 2>/dev/null || true
sh "$W/prestart.sh" >"$W/pre3.log" 2>&1
[ "$(ver)" = "1.1.0" ] || bad "B: yangilanish qo'llanmadi"
# yangi agent tasdiq bermasdan qayta ishga tushdi (masalan, ishga tushishda qulaydi)
sh "$W/prestart.sh" >"$W/pre4.log" 2>&1
[ "$(ver)" = "1.0.0" ] && ok "tasdiqsiz yangi binar qaytarildi (rollback)" || bad "rollback bo'lmadi: $(ver)"
grep -q '"version":"1.1.0"' "$STATE/rolled_back.json" && ok "qaytarilgan versiya qayd etildi" || bad "rolled_back.json yo'q"
start_agent b2
sleep 25
kill -0 "$AGENT" 2>/dev/null && [ ! -e "$STAGE/staged" ] && ok "qaytarilgan versiya qayta yuklanmadi, agent ishlaydi" || bad "qaytarilgan versiya qayta urinildi"
grep -q "avval qaytarilgan" "$W/b2.log" && ok "sabab logda" || bad "log sababi yo'q"
kill "$AGENT" 2>/dev/null || true; wait "$AGENT" 2>/dev/null || true

# ---- C. Begona kalit bilan imzolangan reliz rad etiladi (T-U-SEC-11) ----
reset_state
install -m 0755 "$W/agent-1.0.0" "$BIN"
echo "$W/evil" > "$W/serve_dir"
start_agent c1
sleep 30
kill -0 "$AGENT" 2>/dev/null && ok "begona imzoda agent ishlashda davom etdi" || bad "agent to'xtab qoldi"
[ ! -e "$STAGE/staged" ] && ok "begona imzoli to'plam staged bo'lmadi" || bad "begona imzoli to'plam staged bo'ldi"
grep -q "agent_update_rejected" "$W/c1.log" && grep -q "kalit" "$W/c1.log" && ok "agent_update_rejected qayd etildi (boshqa kalit)" || bad "rad etish logda yo'q"
[ "$(ver)" = "1.0.0" ] && ok "binar o'zgarmadi" || bad "binar o'zgardi"
kill "$AGENT" 2>/dev/null || true; wait "$AGENT" 2>/dev/null || true
echo "$W/dist" > "$W/serve_dir"

# ---- D. Yangi binar umuman ishlamasa o'rov skripti eskisini qaytaradi ----
reset_state
install -m 0755 "$W/agent-1.0.0" "$BIN.old"
head -c 64 /bin/ls > "$BIN" && chmod 0755 "$BIN"
printf '{"from":"1.0.0","to":"1.1.0","applied_at":"%s"}' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$STATE/pending.json"
sh "$W/prestart.sh" >"$W/pre5.log" 2>&1 || bad "o'rov skripti nol bo'lmagan kod bilan chiqdi"
[ "$(ver)" = "1.0.0" ] && [ ! -e "$STATE/pending.json" ] && ok "ishlamaydigan yangi binar o'rov skripti bilan qaytarildi" || bad "fallback ishlamadi"

echo "---"
[ "$fails" -eq 0 ] && echo "HAMMASI O'TDI" || { echo "XATOLAR: $fails"; exit 1; }
