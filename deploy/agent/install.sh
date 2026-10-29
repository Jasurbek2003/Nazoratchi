#!/usr/bin/env bash
# Nazoratchi agent o'rnatuvchisi (TZ 7.7.1). Core uni berishda __CORE_URL__ va __MINISIGN_PUBKEY__ ni almashtiradi.
#   curl -fsSL https://<core>/install.sh | sudo NAZORATCHI_ENROLL_TOKEN=<token> bash
# Idempotent: qayta ishga tushirilsa mavjud sozlama va tokenni saqlaydi, binarni yangilaydi.
# Sinov uchun o'zgaruvchilar: NAZORATCHI_ROOT (fayl ildizi), NAZORATCHI_SKIP_START=1.
set -euo pipefail

CORE_URL="__CORE_URL__"
MINISIGN_PUBKEY="__MINISIGN_PUBKEY__"

ROOT="${NAZORATCHI_ROOT:-}"
BIN="$ROOT/usr/local/bin/nazoratchi-agent"
CONF_DIR="$ROOT/etc/nazoratchi"
CONF="$CONF_DIR/agent.yaml"
TOKEN_FILE="$CONF_DIR/token"
STATE_DIR="$ROOT/var/lib/nazoratchi"
UNIT="$ROOT/etc/systemd/system/nazoratchi-agent.service"
PROXY_NAME="nazoratchi-docker-proxy"
PROXY_IMAGE="${NAZORATCHI_PROXY_IMAGE:-tecnativa/docker-socket-proxy:0.3.0}"

say() { printf '%s\n' "$*"; }
fail() { printf 'xato: %s\n' "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

# 1. Old shartlar
[ "$(id -u)" -eq 0 ] || fail "root huquqi kerak (sudo bilan ishga tushiring)"
case "$CORE_URL$MINISIGN_PUBKEY" in *__*) fail "skriptni core'dan oling: https://<core>/install.sh" ;; esac
[ -n "${NAZORATCHI_ENROLL_TOKEN:-}" ] || [ -s "$TOKEN_FILE" ] || fail "NAZORATCHI_ENROLL_TOKEN berilmagan"
have curl || fail "curl topilmadi"
have sha256sum || fail "sha256sum topilmadi"
have minisign || fail "minisign topilmadi (apt install minisign)"
if [ -z "$ROOT" ]; then have systemctl || fail "systemd (systemctl) topilmadi"; fi

# 2. Arxitektura
case "$(uname -m)" in
  x86_64|amd64) ARCH=amd64 ;;
  aarch64|arm64) ARCH=arm64 ;;
  *) fail "qo'llab-quvvatlanmaydigan arxitektura: $(uname -m)" ;;
esac

# 3-4. Yuklash va imzoni tekshirish
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
NAME="nazoratchi-agent-$ARCH"
for f in "$NAME" SHA256SUMS SHA256SUMS.minisig; do
  curl -fsSL --proto '=https,http' --max-time 120 -o "$TMP/$f" "$CORE_URL/agent/v1/$f" \
    || fail "yuklab bo'lmadi: $CORE_URL/agent/v1/$f"
done
printf 'untrusted comment: nazoratchi release key\n%s\n' "$MINISIGN_PUBKEY" > "$TMP/key.pub"
minisign -Vm "$TMP/SHA256SUMS" -p "$TMP/key.pub" -x "$TMP/SHA256SUMS.minisig" >/dev/null \
  || fail "SHA256SUMS imzosi noto'g'ri — o'rnatish to'xtatildi"
EXPECTED="$(awk -v n="$NAME" '$2==n || $2=="*"n {print $1}' "$TMP/SHA256SUMS")"
[ -n "$EXPECTED" ] || fail "SHA256SUMS ichida $NAME yo'q"
ACTUAL="$(sha256sum "$TMP/$NAME" | awk '{print $1}')"
[ "$EXPECTED" = "$ACTUAL" ] || fail "binar SHA-256 mos kelmadi"
say "Imzo va SHA-256 tekshiruvi: OK"

# 5. Binar (atomik almashtirish)
install -d -m 0755 "$(dirname "$BIN")"
install -m 0755 "$TMP/$NAME" "$BIN.new"
mv -f "$BIN.new" "$BIN"

# 6. Foydalanuvchi va guruhlar
if [ -z "$ROOT" ]; then
  id nazoratchi >/dev/null 2>&1 \
    || useradd --system --no-create-home --shell /usr/sbin/nologin nazoratchi
  for g in adm systemd-journal; do
    if getent group "$g" >/dev/null 2>&1; then
      usermod -aG "$g" nazoratchi || true
    fi
  done
fi
install -d -m 0750 "$CONF_DIR" "$STATE_DIR"
if [ -z "$ROOT" ]; then
  chown nazoratchi:nazoratchi "$STATE_DIR"
  chown root:nazoratchi "$CONF_DIR"
fi

# 7. docker-socket-proxy (faqat GET, faqat loopback)
DOCKER_ENDPOINT=""
if [ -z "$ROOT" ] && have docker && docker info >/dev/null 2>&1; then
  if ! docker inspect "$PROXY_NAME" >/dev/null 2>&1; then
    docker run -d --name "$PROXY_NAME" --restart unless-stopped \
      -e CONTAINERS=1 -e INFO=1 -e POST=0 \
      -v /var/run/docker.sock:/var/run/docker.sock:ro \
      -p 127.0.0.1:2375:2375 "$PROXY_IMAGE" >/dev/null \
      || say "ogohlantirish: docker-socket-proxy ko'tarilmadi (Docker kollektori ishlamaydi)"
  fi
  docker inspect "$PROXY_NAME" >/dev/null 2>&1 && DOCKER_ENDPOINT="http://127.0.0.1:2375"
fi

# 8. agent.yaml — mavjud bo'lsa O'ZGARTIRILMAYDI
if [ -f "$CONF" ]; then
  say "Sozlama saqlandi: $CONF"
else
  {
    printf 'core:\n  url: "%s"\n  token_file: "/etc/nazoratchi/token"\n' "$CORE_URL"
    if [ -n "$DOCKER_ENDPOINT" ]; then
      printf 'collectors:\n  docker:\n    enabled: true\n    endpoint: "%s"\n' "$DOCKER_ENDPOINT"
    fi
  } > "$CONF"
  chmod 0640 "$CONF"
fi

# 9. Enroll (token allaqachon bo'lsa — o'tkazib yuboriladi)
if [ -s "$TOKEN_FILE" ]; then
  say "Token saqlandi: $TOKEN_FILE"
elif [ -n "$ROOT" ]; then
  "$BIN" enroll --config "$CONF" --token-file "$TOKEN_FILE" --token "$NAZORATCHI_ENROLL_TOKEN"
else
  "$BIN" enroll --config "$CONF" --token "$NAZORATCHI_ENROLL_TOKEN"
fi
if [ -z "$ROOT" ]; then chown root:nazoratchi "$TOKEN_FILE"; fi
chmod 0640 "$TOKEN_FILE"

# 10. systemd unit
install -d -m 0755 "$(dirname "$UNIT")"
cat > "$UNIT" <<'UNITEOF'
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
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
ReadWritePaths=/var/lib/nazoratchi
ReadOnlyPaths=-/opt/applications/backups -/etc/letsencrypt
CapabilityBoundingSet=
LockPersonality=true

[Install]
WantedBy=multi-user.target
UNITEOF
chmod 0644 "$UNIT"

if [ "${NAZORATCHI_SKIP_START:-}" = "1" ] || [ -n "$ROOT" ]; then
  say "Unit yozildi (ishga tushirish o'tkazib yuborildi)."
  exit 0
fi
systemctl daemon-reload
systemctl enable nazoratchi-agent >/dev/null 2>&1
systemctl restart nazoratchi-agent

# 11. Birinchi paketni kutish
for _ in $(seq 1 30); do
  if journalctl -u nazoratchi-agent --since "-1min" -o cat 2>/dev/null | grep -q "paket yuborildi (birinchi)"; then
    say "Nazoratchi'ga ulandi: $(hostname)"
    exit 0
  fi
  sleep 1
done
say "Agent ishga tushdi, lekin 30 soniyada birinchi paket tasdiqlanmadi: journalctl -u nazoratchi-agent"
