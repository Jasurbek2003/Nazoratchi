#!/usr/bin/env bash
# install.sh ni Debian konteynerida sinaydi (Docker kerak). Repo ildizidan: bash deploy/agent/test.sh
# Ikki qadam: install.sh funksional testi, so'ng o'z-o'zini yangilash e2e (FR-AGT-008).
set -euo pipefail
cd "$(dirname "$0")/../.."
SRC="$(pwd -W 2>/dev/null || pwd)"
for script in run-in-container.sh update-in-container.sh; do
  MSYS_NO_PATHCONV=1 docker run --rm -v "$SRC:/src:ro" golang:1.27-bookworm bash "/src/deploy/agent/test/$script"
done
