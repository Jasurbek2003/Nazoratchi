#!/usr/bin/env bash
# Birinchi ishga tushirish (TZ 15.7, 2-5-qadamlar). Compose papkasida, .env tayyor bo'lgach:
#   bash bootstrap.sh <owner-login>
# Qayta ishga tushirish xavfsiz: migratsiya idempotent, Owner bor bo'lsa o'tkazib yuboriladi.
set -euo pipefail
cd "$(dirname "$0")"

fail() { printf 'xato: %s\n' "$*" >&2; exit 1; }
[ -f .env ] || fail ".env topilmadi (.env.example dan nusxa oling va to'ldiring)"
[ "$(stat -c %a .env)" = "600" ] || { chmod 600 .env; echo ".env rejimi 0600 qilindi"; }
for v in SECRET_KEY DB_PASSWORD NAZORATCHI_MASTER_KEY GHCR_OWNER NAZORATCHI_VERSION; do
  grep -Eq "^${v}=[^[:space:]#]+" .env || fail "$v .env da to'ldirilmagan"
done
LOGIN="${1:-}"
[ -n "$LOGIN" ] || fail "Owner login kerak: bash bootstrap.sh <login>"
case "$LOGIN" in *[!A-Za-z0-9_.-]*) fail "login faqat harf, raqam va _ . - dan iborat bo'lsin" ;; esac

DC="docker compose --env-file .env"
$DC pull
$DC up -d db redis
$DC run --rm web python manage.py migrate --noinput
if $DC run --rm -T web python manage.py shell -c \
  "import sys; from apps.accounts.models import User; sys.exit(0 if User.objects.filter(login='$LOGIN').exists() else 1)" \
  >/dev/null 2>&1; then
  echo "Owner '$LOGIN' mavjud, o'tkazib yuborildi"
else
  $DC run --rm web python manage.py createowner --login "$LOGIN"   # parol terminalda so'raladi
fi
$DC up -d
echo
echo "Tayyor. Keyingi qadamlar (TZ 15.7): reyestr seed (seed_registry --dry-run), HTTPS orqali kirish, 2FA,"
echo "Telegram kanali + sinov xabari, watchdog (S-01), age kalit jufti va birinchi sinov zaxirasi."
