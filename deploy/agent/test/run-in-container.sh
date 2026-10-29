#!/usr/bin/env bash
# `shart && ok ... || bad ...`: ok va bad hech qachon xato qaytarmaydi, shuning uchun SC2015 xavfi yo'q.
# shellcheck disable=SC2015
# install.sh funksional testi (Debian konteyner ichida, NAZORATCHI_ROOT rejimi). Ishga tushirish: ../test.sh
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq >/dev/null
apt-get install -y -qq minisign curl python3 openssl >/dev/null

W=/tmp/w
rm -rf "$W" && mkdir -p "$W/dist" "$W/root"
cd /src/agent && CGO_ENABLED=0 go build -buildvcs=false -o "$W/dist/nazoratchi-agent-amd64" ./cmd/nazoratchi-agent
cd "$W/dist"
sha256sum nazoratchi-agent-amd64 > SHA256SUMS
minisign -G -W -p "$W/pub" -s "$W/sec" >/dev/null
minisign -S -s "$W/sec" -m SHA256SUMS -x SHA256SUMS.minisig >/dev/null
PUB="$(tail -n1 "$W/pub")"

cat > "$W/core.py" <<'PY'
import http.server, json, os
class H(http.server.SimpleHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length", "0")); self.rfile.read(n)
        body = json.dumps({"host_id": "h-test", "agent_token": "perm-token-123", "interval_seconds": 15}).encode()
        if os.environ.get("ENROLL_FAIL"):
            self.send_response(401); body = b'{"error":{"code":"invalid_enroll_token"}}'
        else:
            self.send_response(200)
        self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body)))
        self.end_headers(); self.wfile.write(body)
    def translate_path(self, p):
        return os.path.join("/tmp/w/dist", p.rsplit("/", 1)[-1])
    def log_message(self, *a): pass
http.server.HTTPServer(("127.0.0.1", 8080), H).serve_forever()
PY
python3 "$W/core.py" & CORE=$!
trap 'kill $CORE 2>/dev/null || true' EXIT
sleep 1

sed -e 's#__CORE_URL__#http://localhost:8080#' -e "s#__MINISIGN_PUBKEY__#$PUB#" /src/deploy/agent/install.sh > "$W/install.sh"
export NAZORATCHI_ROOT="$W/root"
fails=0
ok() { echo "OK   $*"; }
bad() { echo "FAIL $*"; fails=$((fails + 1)); }

# certbot tuzilmasi: ommaviy cert.pem + maxfiy privkey.pem (hook faqat birinchisini o'qishi kerak)
LIVE="$W/root/etc/letsencrypt/live"
mkdir -p "$LIVE/avlo.ai" "$LIVE/yomon nom"
for d in "avlo.ai" "yomon nom"; do
  openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes -days 30 -subj "/CN=t"     -keyout "$LIVE/$d/privkey.pem" -out "$LIVE/$d/cert.pem" 2>/dev/null
done

# 1. Birinchi o'rnatish
NAZORATCHI_ENROLL_TOKEN=one-time bash "$W/install.sh" >"$W/out1" 2>&1 || { cat "$W/out1"; bad "birinchi o'rnatish"; }
[ -x "$W/root/usr/local/bin/nazoratchi-agent" ] && ok "binar o'rnatildi" || bad "binar yo'q"
[ "$(tr -d '\n' < "$W/root/etc/nazoratchi/token")" = "perm-token-123" ] && ok "doimiy token yozildi" || bad "token"
[ "$(stat -c %a "$W/root/etc/nazoratchi/token")" = "640" ] && ok "token rejimi 0640" || bad "token rejimi"
grep -q 'url: "http://localhost:8080"' "$W/root/etc/nazoratchi/agent.yaml" && ok "agent.yaml yaratildi" || bad "agent.yaml"
grep -q "NoNewPrivileges=true" "$W/root/etc/systemd/system/nazoratchi-agent.service" && ok "unit yozildi" || bad "unit"
"$W/root/usr/local/bin/nazoratchi-agent" check-config --config "$W/root/etc/nazoratchi/agent.yaml" >/dev/null 2>&1 \
  && ok "check-config o'tdi" || bad "check-config"

HOOK="$W/root/etc/letsencrypt/renewal-hooks/deploy/nazoratchi-certs.sh"
[ -x "$HOOK" ] && ok "certbot deploy-hook o'rnatildi" || bad "deploy-hook yo'q"
CJ="$W/root/var/lib/nazoratchi/certs.json"
python3 - "$CJ" <<'PYEOF' && ok "certs.json: muddat to'g'ri, yaroqsiz nom tashlandi" || bad "certs.json noto'g'ri"
import json, sys, time
d = json.load(open(sys.argv[1]))["certs"]
assert [c["name"] for c in d] == ["avlo.ai"], d
left = (d[0]["not_after"] - time.time()) / 86400
assert 29 < left < 31, left
PYEOF
grep -q "PRIVATE" "$CJ" && bad "certs.json da maxfiy kalit izi bor" || ok "certs.json da maxfiy ma'lumot yo'q"

# 2. Idempotentlik: sozlama va token saqlanadi
echo "# qo'lda o'zgartirilgan" >> "$W/root/etc/nazoratchi/agent.yaml"
bash "$W/install.sh" >"$W/out2" 2>&1 || { cat "$W/out2"; bad "qayta o'rnatish (tokensiz)"; }
grep -q "qo'lda o'zgartirilgan" "$W/root/etc/nazoratchi/agent.yaml" && ok "qayta ishga tushirishda sozlama saqlandi" || bad "sozlama ustiga yozildi"
[ "$(tr -d '\n' < "$W/root/etc/nazoratchi/token")" = "perm-token-123" ] && ok "token saqlandi" || bad "token o'zgardi"

# 3. Buzilgan binar (SHA mos emas) rad etiladi
echo "x" >> "$W/dist/nazoratchi-agent-amd64"
if NAZORATCHI_ENROLL_TOKEN=t bash "$W/install.sh" >"$W/out3" 2>&1; then bad "buzilgan binar qabul qilindi"; else
  grep -q "SHA-256" "$W/out3" && ok "buzilgan binar rad etildi" || bad "noto'g'ri xato matni"; fi
head -c -2 "$W/dist/nazoratchi-agent-amd64" > "$W/dist/t" && mv "$W/dist/t" "$W/dist/nazoratchi-agent-amd64"

# 4. Boshqa kalit bilan imzolangan SHA256SUMS rad etiladi
cd "$W/dist"
minisign -G -W -p "$W/pub2" -s "$W/sec2" >/dev/null
minisign -S -s "$W/sec2" -m SHA256SUMS -x SHA256SUMS.minisig >/dev/null
if NAZORATCHI_ENROLL_TOKEN=t bash "$W/install.sh" >"$W/out4" 2>&1; then bad "begona imzo qabul qilindi"; else
  grep -q "imzosi noto'g'ri" "$W/out4" && ok "begona imzo rad etildi" || bad "imzo xato matni"; fi

# 5. Root bo'lmagan / token yo'q holatlar
rm -rf "$W/root2"
if NAZORATCHI_ROOT="$W/root2" bash "$W/install.sh" >"$W/out5" 2>&1; then bad "tokensiz o'rnatildi"; else
  grep -q "NAZORATCHI_ENROLL_TOKEN" "$W/out5" && ok "token yo'qligi aniq xabar bilan rad etildi" || bad "token xabari"; fi
if bash /src/deploy/agent/install.sh >"$W/out6" 2>&1; then bad "shablon (almashtirilmagan) ishga tushdi"; else
  grep -q "core'dan oling" "$W/out6" && ok "almashtirilmagan shablon rad etildi" || bad "shablon xabari"; fi

echo "---"
if [ "$fails" -eq 0 ]; then
  echo "HAMMASI O'TDI"
else
  echo "XATOLAR: $fails"
  exit 1
fi
