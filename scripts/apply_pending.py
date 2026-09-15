"""
연결 폴더에 쌓인 주간 신규 썰(pending_v2_*.py)을 question_bank_v2.py에 합친다.

2026-09-15 신설. 왜 만들었나.
  주간 보충 작업(threads-question-bank-refresh)이 GitHub 커밋을 Claude in Chrome
  웹 편집기에 의존해 왔는데, 9/1과 9/15 두 번 확인된 실패가 있었다.
  확장이 끊기거나 로그인이 풀리면 18편이 통째로 날아간다.

  맥은 git 인증이 살아 있고 run_daily.sh가 하루 두 번 돈다.
  그러니 예약작업은 '원고를 연결 폴더에 떨구는 것'까지만 하고,
  실제 뱅크 반영은 이 스크립트가 맥에서 처리한다. 브라우저가 아예 필요 없어진다.

동작
  1. 연결 폴더에서 pending_v2_*.py 를 찾는다 (오래된 것부터)
  2. 각 파일에서 V2_PENDING 리스트를 읽는다
  3. 편마다 스키마와 길이를 검사한다. 통과한 것만 쓴다
  4. 이미 뱅크에 있는 id는 건너뛴다 (중복 발행 방지)
  5. question_bank_v2.py 의 마지막 "]" 앞에 끼워 넣는다
  6. ast.parse 와 재로딩으로 검증한다. 깨지면 원본을 되돌리고 중단한다
  7. 처리한 pending 파일은 연결 폴더의 applied/ 로 옮긴다

안전 원칙
  - 추가만 한다. 기존 항목을 고치거나 지우지 않는다
  - 검증 실패 시 뱅크를 원상 복구한다
  - data/ 는 절대 건드리지 않는다
  - 종료코드 0 = 정상(반영했든 반영할 게 없든), 1 = 뱅크가 깨져서 되돌림
"""
import ast
import glob
import json
import os
import shutil
import sys
import unicodedata
from datetime import datetime

BANK_PATH = "scripts/question_bank_v2.py"
FOLDER_NAME = "쓰레드 100만 팔로워 달성하기"

KEY_ORDER = ["id", "category", "series", "ep", "ep_total",
             "hook", "body", "closing",
             "option_a", "option_a_sub", "option_b", "option_b_sub"]


def find_pending_dir():
    """연결 폴더를 찾는다. 맥 파일명은 자소 분리(NFD)로 저장돼서 단순 비교가 실패한다."""
    env = os.environ.get("PENDING_DIR")
    if env and os.path.isdir(env):
        return env
    home = os.path.expanduser("~")
    target = unicodedata.normalize("NFC", FOLDER_NAME)
    try:
        for name in os.listdir(home):
            if unicodedata.normalize("NFC", name) == target:
                return os.path.join(home, name)
    except OSError:
        pass
    return None


def load_items(path):
    """pending 파일에서 항목 리스트를 꺼낸다."""
    src = open(path, encoding="utf-8").read()
    ast.parse(src)  # 문법 오류면 여기서 터진다
    ns = {}
    exec(compile(src, path, "exec"), ns)
    for key in ("V2_PENDING", "V2_BATCH", "V2_QUESTIONS", "V2_NEW"):
        if isinstance(ns.get(key), list):
            return ns[key]
    raise ValueError("V2_PENDING 리스트를 못 찾음")


def validate(q, existing_ids, seen_ids):
    """한 편을 검사한다. 통과하면 빈 리스트, 아니면 사유 리스트를 돌려준다."""
    bad = []
    for k in ("id", "category", "hook", "body", "closing",
              "option_a", "option_b", "option_a_sub", "option_b_sub"):
        if not isinstance(q.get(k), str) or not q[k].strip():
            bad.append(f"{k} 누락")
    if bad:
        return bad

    h, b, c = q["hook"], q["body"], q["closing"]
    if not 20 <= len(h) <= 52:
        bad.append(f"hook {len(h)}자")
    if not 280 <= len(b) <= 400:
        bad.append(f"body {len(b)}자")
    if not 15 <= len(c) <= 70:
        bad.append(f"closing {len(c)}자")
    if 14 + len(h) + len(b) + len(c) + 18 > 500:
        bad.append("전체 500자 초과")
    if b.count('"') < 2:
        bad.append("대사 없음")
    if len([p for p in b.split("\n\n") if p.strip()]) < 4:
        bad.append("body 문단 4개 미만")
    if "vs" in h.lower():
        bad.append("hook에 vs")
    if "마지막 화" in h:
        bad.append("hook에 '마지막 화'")
    if len(q["option_a"]) > 12 or len(q["option_b"]) > 12:
        bad.append("선택지 12자 초과")
    for k in ("option_a_sub", "option_b_sub"):
        if "\n" not in q[k] or not q[k].rstrip().endswith("!"):
            bad.append(k)
    if q["id"] in existing_ids:
        bad.append("뱅크에 이미 있는 id")
    if q["id"] in seen_ids:
        bad.append("이번 배치 안에서 id 중복")
    return bad


def fmt(q):
    """기존 뱅크와 같은 스타일의 파이썬 리터럴로 찍는다."""
    def v(x):
        if x is None:
            return "None"
        if isinstance(x, bool):
            return "True" if x else "False"
        if isinstance(x, int):
            return str(x)
        return json.dumps(x, ensure_ascii=False)

    g = lambda k: v(q.get(k))
    return (
        f'{{"id": {g("id")}, "category": {g("category")},\n'
        f' "series": {g("series")}, "ep": {g("ep")}, "ep_total": {g("ep_total")},\n'
        f' "hook": {g("hook")},\n'
        f' "body": {g("body")},\n'
        f' "closing": {g("closing")},\n'
        f' "option_a": {g("option_a")}, "option_a_sub": {g("option_a_sub")},\n'
        f' "option_b": {g("option_b")}, "option_b_sub": {g("option_b_sub")}}},\n'
    )


def main():
    pending_dir = find_pending_dir()
    if not pending_dir:
        print("[pending] 연결 폴더를 못 찾음. 건너뜀")
        return 0

    files = sorted(glob.glob(os.path.join(pending_dir, "pending_v2_*.py")))
    if not files:
        print("[pending] 반영할 파일 없음")
        return 0

    if not os.path.exists(BANK_PATH):
        print(f"[pending] {BANK_PATH} 없음. 저장소 루트에서 실행해야 한다")
        return 0

    original = open(BANK_PATH, encoding="utf-8").read()
    ns = {}
    exec(compile(original, "bank", "exec"), ns)
    existing_ids = {x["id"] for x in ns["V2_QUESTIONS"]}
    before = len(ns["V2_QUESTIONS"])

    seen, accepted, rejected = set(), [], []
    for path in files:
        try:
            items = load_items(path)
        except Exception as e:
            print(f"[pending] {os.path.basename(path)} 읽기 실패: {e}")
            rejected.append((os.path.basename(path), str(e)))
            continue
        for q in items:
            reasons = validate(q, existing_ids, seen)
            if reasons:
                rejected.append((q.get("id", "?"), ", ".join(reasons)))
            else:
                seen.add(q["id"])
                accepted.append(q)

    if not accepted:
        print(f"[pending] 통과한 편이 없음. 탈락 {len(rejected)}건")
        for rid, why in rejected[:10]:
            print(f"    - {rid}: {why}")
        return 0

    cut = original.rindex("]")
    merged = original[:cut] + "\n" + "".join(fmt(q) for q in accepted) + original[cut:]

    open(BANK_PATH, "w", encoding="utf-8").write(merged)

    # 검증. 깨졌으면 즉시 되돌린다.
    try:
        ast.parse(merged)
        ns2 = {}
        exec(compile(merged, "bank", "exec"), ns2)
        after = len(ns2["V2_QUESTIONS"])
        ids = [x["id"] for x in ns2["V2_QUESTIONS"]]
        assert after == before + len(accepted), f"개수 불일치 {before}→{after}"
        assert len(ids) == len(set(ids)), "id 중복 발생"
    except Exception as e:
        open(BANK_PATH, "w", encoding="utf-8").write(original)
        print(f"[pending] 검증 실패로 원상 복구함: {e}")
        return 1

    applied_dir = os.path.join(pending_dir, "applied")
    os.makedirs(applied_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for path in files:
        try:
            shutil.move(path, os.path.join(
                applied_dir, f"{stamp}_{os.path.basename(path)}"))
        except OSError as e:
            print(f"[pending] {os.path.basename(path)} 이동 실패(무시): {e}")

    print(f"[pending] {len(accepted)}편 반영 완료. 뱅크 {before} → {after}편")
    if rejected:
        print(f"[pending] 탈락 {len(rejected)}건")
        for rid, why in rejected[:10]:
            print(f"    - {rid}: {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
