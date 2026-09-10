#!/bin/bash
# 쓰레드/인스타그램 자동발행 - 로컬 실행 스크립트
#
# 2026-09-10 개편 이유
#   기존 스크립트는 set -e 상태에서 publish.py 앞에 git push가 있었다.
#   GitHub 토큰이 만료되자 push가 exit 128로 죽었고, 그 뒤의 실제 발행이
#   통째로 실행되지 않아 9/9 저녁 ~ 9/10 아침 발행이 누락됐다.
#
#   원칙: 발행이 본체다. git은 기록일 뿐이다.
#   git이 실패해도 스레드 발행은 반드시 시도한다.
#
#   스레드 발행은 publish.py에서 image_url=None으로 텍스트만 올리므로
#   CDN(IMAGE_BASE_URL)이 없어도 아무 문제가 없다.
#   IMAGE_BASE_URL은 저녁 슬롯 인스타그램 캐러셀에만 쓰인다.
#   따라서 push가 실패하면 인스타만 건너뛰고 스레드는 정상 발행한다.

cd "$(dirname "$0")" || exit 1

source venv/bin/activate || { echo "[치명] venv 활성화 실패"; exit 1; }

set -a
source .env || { echo "[치명] .env 로드 실패"; exit 1; }
set +a

notify() {
  # 실패를 조용히 넘기지 않는다. 화면 알림 + 로그 양쪽에 남긴다.
  echo "[알림] $1"
  osascript -e "display notification \"$1\" with title \"썰대리 자동발행\"" 2>/dev/null || true
}

# ── 1. 최신 코드 받기 ────────────────────────────────────────────
# 실패해도 계속 간다. 뱅크가 조금 옛날 것이어도 발행은 되는 게 낫다.
if ! git pull --quiet; then
  notify "git pull 실패 - 로컬 코드로 계속 진행"
fi

# ── 2. 원고 생성 ────────────────────────────────────────────────
# 이건 실패하면 발행할 게 없으므로 여기서 중단한다.
if ! python3 scripts/prepare.py; then
  notify "prepare.py 실패 - 발행 중단 (재고 소진 여부 확인 필요)"
  exit 1
fi

# ── 3. 원고 커밋 & push ─────────────────────────────────────────
# push 성공 여부만 기록하고, 실패해도 절대 멈추지 않는다.
git add data/cards data/draft.json
git commit -m "chore: draft $(date +%F)" --quiet || echo "[변경 없음] draft 커밋 스킵"

if git push --quiet; then
  SHA=$(git rev-parse HEAD)
  export IMAGE_BASE_URL="https://cdn.jsdelivr.net/gh/bluewhalesjin-prog/-@${SHA}"
else
  # push가 안 됐으면 jsDelivr가 이미지를 못 가져온다.
  # 빈 값으로 두면 publish.py가 인스타를 건너뛰고 스레드만 발행한다.
  export IMAGE_BASE_URL=""
  notify "git push 실패 - 인스타는 건너뛰고 스레드만 발행함 (토큰 만료 확인)"
fi

# ── 4. 실제 발행 ────────────────────────────────────────────────
python3 scripts/publish.py
PUB_STATUS=$?

# ── 5. 결과 기록 ────────────────────────────────────────────────
# published_ids.json이 기존 스크립트에서 빠져 있었다.
# 이 파일이 중복 발행 방지의 기준인데 커밋이 안 돼서 원격에 반영되지 않았다.
git add data/history.json data/last_result.json data/published_ids.json
git commit -m "chore: result $(date +%F)" --quiet || echo "[변경 없음] result 커밋 스킵"
git push --quiet || notify "결과 push 실패 - 다음 실행에서 재시도됨"

if [ $PUB_STATUS -ne 0 ]; then
  notify "발행 실패 (publish.py 종료코드 $PUB_STATUS)"
  exit $PUB_STATUS
fi

echo "[완료] $(date '+%Y-%m-%d %H:%M:%S')"
