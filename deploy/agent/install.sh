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
# O'z-o'zini yangilash (FR-AGT-008): agent yuklagan fayllar `update/` da (agent yozadi, root hech narsaga
# ishonmay qayta tekshiradi); rollback holati esa faqat root yoza oladigan papkada (agent o'qiy oladi).
UPDATE_STATE="$ROOT/var/lib/nazoratchi-update"
install -d -m 0755 "$UPDATE_STATE"
install -d -m 0700 "$STATE_DIR/update"
if [ -z "$ROOT" ]; then chown nazoratchi:nazoratchi "$STATE_DIR/update"; fi

# 7. docker-socket-proxy (faqat GET, faqat loopback)
DOCKER_ENDPOINT=""
if [ -z "$ROOT" ] && have docker && docker info >/dev/null 2>&1; then
  if ! docker inspect "$PROXY_NAME" >/dev/null 2>&1; then
    docker run -d --name "$PROXY_NAME" --restart unless-stopped \
      -e CONTAINERS=1 -e INFO=1 -e SYSTEM=1 -e POST=0 \
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

# 9b. certbot deploy-hook (FR-TLS-005): sertifikat muddatlarini agent o'qiy oladigan faylga yozadi.
# /etc/letsencrypt/live root uchun yopiq, agent esa root emas; hook faqat ommaviy cert.pem muddatini o'qiydi.
HOOK="$ROOT/etc/letsencrypt/renewal-hooks/deploy/nazoratchi-certs.sh"
if [ -d "$ROOT/etc/letsencrypt" ]; then
  install -d -m 0755 "$(dirname "$HOOK")"
  cat > "$HOOK" <<'HOOKEOF'
#!/usr/bin/env bash
# Nazoratchi: certbot deploy-hook (TZ 7.7.2). Har yangilanishdan keyin, root sifatida, sertifikat
# muddatlarini /var/lib/nazoratchi/certs.json ga yozadi; agent shu faylni o'qiydi.
# Nega: /etc/letsencrypt/live odatda root uchun yopiq (0700), agent esa root emas. Bu skript faqat
# ommaviy `cert.pem` ning tugash sanasini o'qiydi; `privkey*.pem` ga tegmaydi.
# Sinov uchun: NAZORATCHI_LIVE_DIR, NAZORATCHI_CERTS_JSON, NAZORATCHI_STATE_GROUP.
set -euo pipefail

LIVE_DIR="${NAZORATCHI_LIVE_DIR:-/etc/letsencrypt/live}"
OUT="${NAZORATCHI_CERTS_JSON:-/var/lib/nazoratchi/certs.json}"
GROUP="${NAZORATCHI_STATE_GROUP:-nazoratchi}"

command -v openssl >/dev/null 2>&1 || { echo "openssl topilmadi" >&2; exit 1; }
[ -d "$LIVE_DIR" ] || exit 0

tmp="$(mktemp "$OUT.XXXXXX")"
trap 'rm -f "$tmp"' EXIT

first=1
printf '{"certs":[' > "$tmp"
for cert in "$LIVE_DIR"/*/cert.pem; do
  [ -f "$cert" ] || continue
  name="$(basename "$(dirname "$cert")")"
  # Agent tomonidagi nom qoidasi bilan bir xil: boshqacha nomni agent baribir tashlaydi.
  case "$name" in *[!A-Za-z0-9._-]*) continue ;; esac
  end="$(openssl x509 -enddate -noout -in "$cert" 2>/dev/null)" || continue
  ts="$(date -u -d "${end#notAfter=}" +%s 2>/dev/null)" || continue
  [ "$first" -eq 1 ] || printf ',' >> "$tmp"
  printf '{"name":"%s","not_after":%s}' "$name" "$ts" >> "$tmp"
  first=0
done
printf ']}\n' >> "$tmp"

chmod 0640 "$tmp"
chgrp "$GROUP" "$tmp" 2>/dev/null || chmod 0644 "$tmp" # guruh yo'q bo'lsa o'qish hammaga (fayl maxfiy emas)
mv -f "$tmp" "$OUT"
trap - EXIT
HOOKEOF
  chmod 0755 "$HOOK"
  # Birinchi marta darhol ishga tushiriladi: yangilanishni kutmasdan muddatlar ko'rinadi.
  NAZORATCHI_LIVE_DIR="$ROOT/etc/letsencrypt/live" NAZORATCHI_CERTS_JSON="$STATE_DIR/certs.json" "$HOOK" \
    || say "ogohlantirish: sertifikat muddatlari yozilmadi (openssl bormi?)"
fi

# 9c. Ishga tushishdan oldingi qadam (root): staged yangilanishni almashtiradi yoki tasdiqlanmagan yangisini
# qaytaradi. O'rov skript shuning uchun kerakki, yangi binar umuman ishlamasa ham eskisi qaytishi shart.
PRESTART="$ROOT/usr/local/lib/nazoratchi/agent-prestart.sh"
install -d -m 0755 "$(dirname "$PRESTART")"
cat > "$PRESTART" <<'PRESTARTEOF'
#!/bin/sh
# systemd ExecStartPre=+ (root). Har doim 0 bilan chiqadi: agent ishga tushishi kerak.
BIN="${NAZORATCHI_BIN:-/usr/local/bin/nazoratchi-agent}"
STATE="${NAZORATCHI_UPDATE_STATE:-/var/lib/nazoratchi-update}"
STAGE="${NAZORATCHI_UPDATE_STAGE:-/var/lib/nazoratchi/update}"
if "$BIN" apply-update --bin "$BIN" --stage "$STAGE" --state "$STATE"; then
  exit 0
fi
# apply-update ishlamadi (yangi binar buzuq bo'lishi mumkin): kutilayotgan yangilanish bo'lsa eskisini qaytaramiz.
if [ -f "$STATE/pending.json" ] && [ -f "$BIN.old" ]; then
  echo "agent-prestart: apply-update ishlamadi, $BIN.old qaytarilmoqda" >&2
  mv -f "$BIN.old" "$BIN" && rm -f "$STATE/pending.json"
fi
exit 0
PRESTARTEOF
chmod 0755 "$PRESTART"

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
ExecStartPre=+/usr/local/lib/nazoratchi/agent-prestart.sh
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
