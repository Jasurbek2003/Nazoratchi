#!/usr/bin/env bash
# install.sh ni Debian konteynerida sinaydi (Docker kerak). Repo ildizidan: bash deploy/agent/test.sh
set -euo pipefail
cd "$(dirname "$0")/../.."
MSYS_NO_PATHCONV=1 docker run --rm -v "$(pwd -W 2>/dev/null || pwd):/src:ro" golang:1.27-bookworm \
  bash /src/deploy/agent/test/run-in-container.sh
