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

# ── 1-2. 주간 신규 썰 자동 반영 ─────────────────────────────────
# 2026-09-15 추가.
#   주간 보충 작업이 GitHub 커밋을 Claude in Chrome에 의존해 왔는데
#   9/1, 9/15 두 번 확인된 실패가 있었다. 확장이 끊기면 18편이 통째로 날아간다.
#   이제 예약작업은 연결 폴더에 pending_v2_*.py 를 떨구기만 하고,
#   실제 뱅크 반영은 여기서 한다. 맥은 git 인증이 살아 있고 하루 두 번 도니까
#   브라우저가 아예 필요 없어진다.
#
#   스크립트는 검증 실패 시 뱅크를 원상 복구하고 종료코드 1을 준다.
#   그 경우에도 발행은 계속한다. 재고가 안 늘었을 뿐 오늘 나갈 글은 있다.
if python3 scripts/apply_pending.py; then
  if ! git diff --quiet -- scripts/question_bank_v2.py; then
    git add scripts/question_bank_v2.py
    git commit -m "feat: 주간 신규 썰 자동 반영 $(date +%F)" --quiet
    git push --quiet || notify "뱅크 반영 push 실패 - 다음 실행에서 재시도됨"
    notify "주간 신규 썰을 뱅크에 반영했습니다"
  fi
else
  notify "pending 반영 실패 - 뱅크는 원상 복구됨. Cowork에서 확인 필요"
  git checkout -- scripts/question_bank_v2.py 2>/dev/null || true
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

# ── 4-2. 성과 수집 ──────────────────────────────────────────────
# 2026-09-22 추가.
#   67건을 발행했는데 조회수가 기록된 건 6건뿐이었다. 9%를 보고 규칙을 만들고 있었다.
#   이제 매 실행마다 최근 10일치 글의 조회/답글/좋아요와 팔로워 수를
#   data/metrics.json 에 쌓는다.
#   이 단계는 무슨 일이 있어도 발행을 막지 않는다(스크립트가 항상 exit 0).
python3 scripts/collect_insights.py --quiet || true

# ── 5. 결과 기록 ────────────────────────────────────────────────
# published_ids.json이 기존 스크립트에서 빠져 있었다.
# 이 파일이 중복 발행 방지의 기준인데 커밋이 안 돼서 원격에 반영되지 않았다.
git add data/history.json data/last_result.json data/published_ids.json data/metrics.json
git commit -m "chore: result $(date +%F)" --quiet || echo "[변경 없음] result 커밋 스킵"
git push --quiet || notify "결과 push 실패 - 다음 실행에서 재시도됨"

if [ $PUB_STATUS -ne 0 ]; then
  notify "발행 실패 (publish.py 종료코드 $PUB_STATUS)"
  exit $PUB_STATUS
fi

echo "[완료] $(date '+%Y-%m-%d %H:%M:%S')"
