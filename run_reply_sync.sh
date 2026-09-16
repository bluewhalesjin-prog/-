#!/bin/bash
# reply_sync.py 실행 래퍼. launchd가 이걸 부른다.
cd "$(dirname "$0")" || exit 1
source venv/bin/activate || exit 1
set -a; source .env || exit 1; set +a
python3 scripts/reply_sync.py
