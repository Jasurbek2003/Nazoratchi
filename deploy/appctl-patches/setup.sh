#!/usr/bin/env bash
# Serverni bir marta tayyorlash (idempotent — qayta ishga tushirsa bo'ladi).
#
#   sudo bash setup.sh                 # papkalar, appctl, nginx include, kunlik zaxira cron
#   sudo bash setup.sh --ufw           # + firewall (22, 80, 443)
#   sudo bash setup.sh --fail2ban      # + fail2ban (sshd)
#   sudo bash setup.sh --harden-ssh    # + SSH parolsiz (faqat kalit) — authorized_keys bo'lsa
#   sudo bash setup.sh --heartbeat-url=https://<core>/hb/<TOKEN>   # + Nazoratchi heartbeat (zaxira cron'i)
#
# Bayroqlarni birgalikda berish mumkin. SSH'ni qattiqlashtirishdan oldin boshqa
# terminalda KALIT BILAN kira olishingizni tekshiring.
set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "root bo'lib ishga tushiring" >&2; exit 1; }

BASE=/opt/applications
HERE="$(cd "$(dirname "$0")" && pwd)"
DO_UFW=0; DO_F2B=0; DO_SSH=0; HEARTBEAT_URL="${NAZORATCHI_HEARTBEAT_URL:-}"   # shell tarixida qolmasligi uchun muhitdan ham
for a in "$@"; do
  case "$a" in
    --ufw) DO_UFW=1 ;;
    --fail2ban) DO_F2B=1 ;;
    --harden-ssh) DO_SSH=1 ;;
    --heartbeat-url=*) HEARTBEAT_URL="${a#--heartbeat-url=}" ;;
    *) echo "noma'lum bayroq: $a" >&2; exit 1 ;;
  esac
done

echo "→ papkalar"
mkdir -p "$BASE"/{projects,nginx,scripts,backups}
[ -f "$BASE/REGISTRY.md" ] || cp "$HERE/REGISTRY.md" "$BASE/REGISTRY.md"
[ -f "$BASE/appctl.conf" ] || cat > "$BASE/appctl.conf" <<'EOF'
# appctl global sozlamalari
KEEP_DAILY=7
KEEP_WEEKLY=5
# Ikkinchi serverga zaxira nusxa (kalit bilan kirish kerak), masalan:
# OFFSITE=root@38.242.143.248:/root/backups/main-server
OFFSITE=""
# Nazoratchi heartbeat tokeni bu faylda EMAS: setup.sh --heartbeat-url=... uni appctl.secret ga yozadi.
EOF

echo "→ appctl"
install -m 0755 "$HERE/appctl" /usr/local/bin/appctl

if [ -n "$HEARTBEAT_URL" ]; then
  # Token $BASE/appctl.secret ga (0600) yoziladi, /etc/cron.d ga EMAS (u hamma o'qiy oladi).
  # Noto'g'ri URL bo'lsa shu yerda to'xtaydi, nginx hali o'zgarmagan.
  echo "→ Nazoratchi heartbeat"
  APPCTL_BASE="$BASE" /usr/local/bin/appctl heartbeat-set "$HEARTBEAT_URL"
fi

echo "→ nginx: konfiglar $BASE/nginx ichida"
INCLUDE=/etc/nginx/conf.d/00-applications.conf
moved=()
for f in /etc/nginx/conf.d/*.conf; do
  [ -f "$f" ] && [ ! -L "$f" ] && [ "$f" != "$INCLUDE" ] || continue
  mv "$f" "$BASE/nginx/"
  moved+=("$(basename "$f")")
done
echo "include $BASE/nginx/*.conf;" > "$INCLUDE"
if ! nginx -t; then
  echo "nginx -t xato — o'zgarishlar qaytarilmoqda" >&2
  rm -f "$INCLUDE"
  for f in "${moved[@]}"; do mv "$BASE/nginx/$f" /etc/nginx/conf.d/; done
  exit 1
fi
systemctl reload nginx

echo "→ kunlik zaxira (03:15)"
cat > /etc/cron.d/appctl-backup <<'EOF'
15 3 * * * root /usr/local/bin/appctl backup all >> /var/log/appctl-backup.log 2>&1
EOF
chmod 0644 /etc/cron.d/appctl-backup

if [ "$DO_UFW" -eq 1 ]; then
  echo "→ ufw"
  apt-get install -y ufw
  ufw allow 22/tcp
  ufw allow 80/tcp
  ufw allow 443/tcp
  ufw --force enable
fi

if [ "$DO_F2B" -eq 1 ]; then
  echo "→ fail2ban"
  apt-get install -y fail2ban
  cat > /etc/fail2ban/jail.d/sshd.local <<'EOF'
[sshd]
enabled = true
maxretry = 5
findtime = 10m
bantime = 1h
EOF
  systemctl enable --now fail2ban
  systemctl restart fail2ban
fi

if [ "$DO_SSH" -eq 1 ]; then
  if [ ! -s /root/.ssh/authorized_keys ]; then
    echo "/root/.ssh/authorized_keys bo'sh — SSH qattiqlashtirilmadi" >&2
    exit 1
  fi
  echo "→ SSH: parol bilan kirish o'chirilmoqda"
  cat > /etc/ssh/sshd_config.d/00-hardening.conf <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
EOF
  sshd -t
  systemctl reload ssh
  echo "  Mavjud sessiya ochiq qoladi. Yangi terminalda kalit bilan kirib tekshiring!"
fi

echo
echo "Tayyor. Keyingi qadam: appctl list"
