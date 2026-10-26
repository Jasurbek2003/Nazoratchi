"""setup.sh --heartbeat-url sinovi (E-03). Bir martalik Debian konteynerida, root bilan; `nginx` va
`systemctl` soxta. Mahalliy mashina fayllariga tegilmaydi (hammasi konteyner ichida).
"""

import shutil
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent.parent


def docker_ready() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


pytestmark = pytest.mark.skipif(not docker_ready(), reason="docker kerak")

SCRIPT = r"""
set -u
mkdir -p /w /etc/nginx/conf.d /etc/cron.d
cp /src/appctl /src/setup.sh /w/; echo "# registry" > /w/REGISTRY.md
for c in nginx systemctl; do
  printf '#!/bin/sh\necho "$0 $*" >> /tmp/calls\nexit 0\n' > /usr/local/bin/$c; chmod +x /usr/local/bin/$c
done
S=/opt/applications/appctl.secret

bash /w/setup.sh > /tmp/a.out 2>&1; echo "RC_A=$?"
echo "SECRET_A=$([ -e $S ] && echo yes || echo no)"
echo "CRON=$(cat /etc/cron.d/appctl-backup)"
CRON_A="$(cat /etc/cron.d/appctl-backup)"

bash /w/setup.sh --heartbeat-url=https://core.example.uz/hb/TOKEN123 > /tmp/b.out 2>&1; echo "RC_B=$?"
echo "MODE_B=$(stat -c %a $S)"; echo "OWNER_B=$(stat -c %U $S)"
echo "SECRET_B=$(cat $S)"
echo "TOKEN_LEAKS=$(grep -l TOKEN123 /opt/applications/appctl.conf /etc/cron.d/appctl-backup /tmp/b.out 2>/dev/null | wc -l)"
echo "CRON_SAME=$([ "$(cat /etc/cron.d/appctl-backup)" = "$CRON_A" ] && echo yes || echo no)"
echo "APPCTL_MODE=$(stat -c %a /usr/local/bin/appctl)"

bash /w/setup.sh --heartbeat-url=https://core2.example.uz/hb/NEW456 > /dev/null 2>&1
echo "LINES_C=$(grep -c '^HEARTBEAT_URL=' $S)"; echo "SECRET_C=$(cat $S)"

NAZORATCHI_HEARTBEAT_URL=https://env.example.uz/hb/ENV789 bash /w/setup.sh > /dev/null 2>&1
echo "SECRET_D=$(cat $S)"

rm -f /etc/nginx/conf.d/00-applications.conf /tmp/calls
bash /w/setup.sh --heartbeat-url=http://insecure.example.uz/x > /tmp/e.out 2>&1; echo "RC_E=$?"
echo "NGINX_CONF_E=$([ -e /etc/nginx/conf.d/00-applications.conf ] && echo yes || echo no)"
echo "CALLS_E=$(cat /tmp/calls 2>/dev/null | wc -l)"
echo "SECRET_E=$(cat $S)"
"""


def test_setup_heartbeat_flag_in_a_clean_container() -> None:
    proc = subprocess.run(
        ["docker", "run", "--rm", "-v", f"{HERE.as_posix()}:/src:ro", "python:3.13-slim", "bash", "-c", SCRIPT],
        capture_output=True,
        text=True,
        timeout=240,
        env={"MSYS_NO_PATHCONV": "1", **__import__("os").environ},
    )
    facts = dict(line.split("=", 1) for line in proc.stdout.splitlines() if "=" in line)
    assert facts["RC_A"] == "0" and facts["SECRET_A"] == "no"  # bayroqsiz: asl xatti-harakat
    assert facts["CRON"] == "15 3 * * * root /usr/local/bin/appctl backup all >> /var/log/appctl-backup.log 2>&1"
    assert facts["RC_B"] == "0"
    assert facts["MODE_B"] == "600" and facts["OWNER_B"] == "root"
    assert facts["SECRET_B"] == "HEARTBEAT_URL='https://core.example.uz/hb/TOKEN123'"
    assert facts["TOKEN_LEAKS"] == "0"  # token appctl.conf, cron.d va chiqishda yo'q
    assert facts["CRON_SAME"] == "yes" and facts["APPCTL_MODE"] == "755"
    assert facts["LINES_C"] == "1" and "NEW456" in facts["SECRET_C"] and "TOKEN123" not in facts["SECRET_C"]
    assert "ENV789" in facts["SECRET_D"]  # NAZORATCHI_HEARTBEAT_URL muhit o'zgaruvchisi
    assert facts["RC_E"] != "0"  # noto'g'ri URL
    assert facts["NGINX_CONF_E"] == "no" and facts["CALLS_E"] == "0"  # nginx hali o'zgarmagan
    assert "ENV789" in facts["SECRET_E"]  # eski maxfiy fayl buzilmagan
