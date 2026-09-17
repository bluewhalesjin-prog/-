"""
우리 글에 달린 답글을 수집하고, 작성된 회신 문안을 게시한다.

2026-09-16 신설. 왜 만들었나.
  9/16 아침 글 하나가 조회 78만, 답글 230개를 넘겼다. 사람이 손으로 회신할 양이 아니다.
  그런데 회신은 값이 크다. 그날 4.4천짜리 답글에 단 회신이 좋아요 182를 받았다.
  답글은 좋아요보다 무거운 신호이고, 회신은 그 스레드 안에서 우리를 다시 노출시킨다.

  브라우저 자동화는 못 쓴다. Chrome 확장이 하루에도 몇 번씩 끊긴다.
  대신 Threads API에 답글 읽기(GET /{id}/replies)와 답글 쓰기(reply_to_id)가 둘 다 있다.
  그래서 브라우저를 아예 빼고 API로만 돌린다.

파이프라인
  ① 이 스크립트(맥, 2시간마다)  outbox에 대기 중인 문안을 게시
  ② 이 스크립트                 최근 글의 미회신 답글을 수집 → inbox
  ③ Cowork 예약 작업(하루 3회)  inbox 읽고 문안 작성 → outbox
  다시 ①로. 브라우저가 한 번도 안 낀다.

파일 (연결 폴더)
  replies_inbox.json   수집된 답글 후보 (이 스크립트가 씀, Cowork가 읽음)
  replies_outbox.json  게시 대기 문안 (Cowork가 씀, 이 스크립트가 읽고 비움)
  replies_log.jsonl    게시 기록 (추적용, 계속 쌓임)

안전장치
  - 우리 글에 달린 답글만 본다. 남의 글에는 절대 안 간다
  - 이미 회신한 답글은 건너뛴다. 게시 직전에 API로 한 번 더 확인한다
  - 한 번에 최대 5개, 하루 최대 20개
  - 민감어가 섞인 답글은 후보에서 제외한다
  - 모든 게시를 로그로 남긴다

사용법
  python3 scripts/reply_sync.py            # 게시 + 수집
  python3 scripts/reply_sync.py --collect  # 수집만
  python3 scripts/reply_sync.py --publish  # 게시만
  python3 scripts/reply_sync.py --dry-run  # 게시 안 하고 출력만
"""
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timedelta, timezone

import requests

GRAPH = "https://graph.threads.net/v1.0"
STATE_DIR = "data/state"
HISTORY_PATH = "data/history.json"
REPLIED_PATH = "data/replied_to.json"

FOLDER_NAME = "쓰레드 100만 팔로워 달성하기"
INBOX = "replies_inbox.json"
OUTBOX = "replies_outbox.json"
LOGFILE = "replies_log.jsonl"

MAX_PER_RUN = 5          # 한 번에 게시할 최대 개수
MAX_PER_DAY = 20         # 하루 총량
LOOKBACK_DAYS = 3        # 최근 며칠 글까지 훑을지
SCAN_LIMIT = 50          # 글 하나당 훑을 답글 수
INSIGHT_CAP = 30         # 좋아요 조회는 상위 후보에만 (API 호출 절약)

# 이런 게 섞인 답글에는 회신하지 않는다. 잘못 엮이면 계정이 위험하다.
BLOCK = re.compile(
    r"정치|대통령|여당|야당|좌파|우파|페미|한남|김치녀|틀딱|급식충|"
    r"죽여|자살|극단적|성추행|성폭|고소|고발|소송|변호사|"
    r"씨발|병신|새끼|좆|지랄|꺼져|닥쳐",
    re.I,
)
QUESTION = re.compile(r"[?？]\s*$|어떻게\s*(됐|했)|그래서\s*어|뭐예요|뭔가요|인가요|나요\?")


def find_folder():
    """연결 폴더를 찾는다. 맥 파일명은 자소 분리(NFD)라 단순 비교가 실패한다."""
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


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(path, obj):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def load_token():
    cached = os.path.join(STATE_DIR, "token.txt")
    if os.path.exists(cached):
        tok = open(cached, encoding="utf-8").read().strip()
        if tok:
            return tok
    return os.environ["THREADS_ACCESS_TOKEN"]


_warned = set()


def api_get(path, token, quiet=False, **params):
    """실패하면 None. 같은 종류의 오류는 한 번만 출력한다(로그 도배 방지)."""
    params["access_token"] = token
    try:
        r = requests.get(f"{GRAPH}/{path}", params=params, timeout=30)
        if r.status_code != 200:
            if not quiet:
                try:
                    msg = r.json().get("error", {}).get("message", "")[:120]
                except ValueError:
                    msg = r.text[:120]
                key = (path.split("/")[-1], r.status_code)
                if key not in _warned:
                    _warned.add(key)
                    print(f"[api] {r.status_code} on .../{key[0]}: {msg}")
            return None
        return r.json()
    except requests.RequestException as e:
        if not quiet:
            print(f"[api] 요청 실패 {path}: {e}")
        return None


def recent_post_ids():
    """최근 LOOKBACK_DAYS 이내 발행한 글의 루트 post_id를 모은다."""
    hist = load_json(HISTORY_PATH, {"entries": []}).get("entries", [])
    cutoff = (datetime.now() - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    ids = []
    for e in hist:
        if not e.get("published") or (e.get("date") or "") < cutoff:
            continue
        pid = (e.get("post_ids") or [None])[0]
        if pid:
            ids.append((e.get("date"), pid))
    return ids


def likes_of(reply_id, token):
    d = api_get(f"{reply_id}/insights", token, metric="likes")
    if not d:
        return 0
    for m in d.get("data", []):
        if m.get("name") == "likes":
            v = m.get("values") or [{}]
            return int(v[0].get("value") or 0)
    return 0


def already_replied(reply_id, me, token):
    """그 답글 아래에 우리 회신이 이미 있는지 API로 확인한다."""
    d = api_get(f"{reply_id}/replies", token, fields="id,username", limit=25)
    if not d:
        return False
    return any(x.get("username") == me for x in d.get("data", []))


def collect(token, me, folder):
    replied = set(load_json(REPLIED_PATH, []))
    cands = []

    for date, pid in recent_post_ids():
        d = api_get(pid, token, fields="id,text,permalink")
        root_text = (d or {}).get("text", "")[:120]
        res = api_get(f"{pid}/replies", token,
                      fields="id,text,username,timestamp,permalink",
                      reverse="true", limit=SCAN_LIMIT)
        if not res:
            continue
        for r in res.get("data", []):
            rid = r.get("id")
            txt = (r.get("text") or "").strip()
            if not rid or not txt:
                continue
            if r.get("username") == me or rid in replied:
                continue
            if BLOCK.search(txt):
                continue
            if len(txt) < 6:          # "ㅋㅋ" 같은 건 회신할 게 없다
                continue
            cands.append({
                "reply_id": rid,
                "username": r.get("username"),
                "text": txt,
                "timestamp": r.get("timestamp"),
                "permalink": r.get("permalink"),
                "post_id": pid,
                "post_date": date,
                "post_excerpt": root_text,
            })

    # 신선도 + 질문 여부 + 길이로 1차 정렬한 뒤, 상위 것만 좋아요를 조회한다.
    now = datetime.now(timezone.utc)

    def age_hours(c):
        """Threads는 '2026-09-16T07:38:54+0000' 형식을 준다. 콜론이 없어서
        fromisoformat이 못 읽는다(3.11 미만). strptime %z는 둘 다 처리한다."""
        raw = (c.get("timestamp") or "").strip()
        if not raw:
            return 999
        raw = raw.replace("Z", "+0000")
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z"):
            try:
                return (now - datetime.strptime(raw, fmt)).total_seconds() / 3600
            except ValueError:
                continue
        try:  # 마지막 수단
            return (now - datetime.fromisoformat(raw)).total_seconds() / 3600
        except Exception:
            return 999

    for c in cands:
        c["age_h"] = round(age_hours(c), 1)
        c["is_question"] = bool(QUESTION.search(c["text"]))

    cands.sort(key=lambda c: (c["age_h"] > 24, -len(c["text"]), c["age_h"]))
    for c in cands[:INSIGHT_CAP]:
        c["likes"] = likes_of(c["reply_id"], token)
        time.sleep(0.3)
    for c in cands[INSIGHT_CAP:]:
        c["likes"] = 0

    def score(c):
        # 좋아요는 insights 권한이 없으면 전부 0으로 들어온다.
        # 그 경우에도 순위가 무너지지 않도록 나머지 신호를 충분히 크게 잡았다.
        s = c["likes"] * 3
        if c["is_question"]:
            s += 8
        if len(c["text"]) >= 60:      # 자기 경험을 길게 쓴 답글
            s += 6
        if len(c["text"]) >= 120:     # 아주 길게 푼 썰
            s += 4
        if c["age_h"] <= 1:
            s += 12                    # 막 달린 것 (초기 반응이 노출을 만든다)
        elif c["age_h"] <= 3:
            s += 8
        elif c["age_h"] <= 12:
            s += 4
        elif c["age_h"] > 48:
            s -= 6                     # 식은 글은 회신해도 안 보인다
        return s

    cands.sort(key=score, reverse=True)
    top = cands[: MAX_PER_RUN * 3]     # Cowork가 고를 여유를 준다

    save_json(os.path.join(folder, INBOX), {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "account": me,
        "note": "Cowork가 읽고 문안을 써서 replies_outbox.json에 저장한다.",
        "candidates": top,
    })
    print(f"[collect] 후보 {len(top)}건 저장 (전체 스캔 {len(cands)}건)")
    return len(top)


def today_count():
    path = os.path.join(find_folder() or ".", LOGFILE)
    today = datetime.now().strftime("%Y-%m-%d")
    n = 0
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    if json.loads(line).get("at", "").startswith(today):
                        n += 1
                except ValueError:
                    continue
    except OSError:
        pass
    return n


def publish(token, me, me_id, folder, dry_run=False):
    out_path = os.path.join(folder, OUTBOX)
    data = load_json(out_path, None)
    if not data or not data.get("replies"):
        print("[publish] 게시할 문안 없음")
        return 0

    used_today = today_count()
    room = min(MAX_PER_RUN, MAX_PER_DAY - used_today)
    if room <= 0:
        print(f"[publish] 오늘 한도 소진 ({used_today}/{MAX_PER_DAY})")
        return 0

    replied = set(load_json(REPLIED_PATH, []))
    done, kept = 0, []

    for item in data["replies"]:
        rid, text = item.get("reply_id"), (item.get("text") or "").strip()
        if not rid or not text:
            continue
        if done >= room:
            kept.append(item)
            continue
        if rid in replied:
            print(f"[publish] 건너뜀(기록에 있음) {rid}")
            continue
        if already_replied(rid, me, token):
            print(f"[publish] 건너뜀(이미 회신됨) {rid}")
            replied.add(rid)
            continue

        if dry_run:
            print(f"[DRY] → {item.get('username')}: {text[:60]}")
            done += 1
            continue

        try:
            c = requests.post(f"{GRAPH}/{me_id}/threads", timeout=30, data={
                "media_type": "TEXT", "text": text,
                "reply_to_id": rid, "access_token": token})
            c.raise_for_status()
            cid = c.json()["id"]
            time.sleep(3)
            p = requests.post(f"{GRAPH}/{me_id}/threads_publish", timeout=30,
                              data={"creation_id": cid, "access_token": token})
            p.raise_for_status()
            new_id = p.json()["id"]
        except Exception as e:
            print(f"[publish] 실패 {rid}: {e}")
            kept.append(item)
            continue

        replied.add(rid)
        done += 1
        with open(os.path.join(folder, LOGFILE), "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "at": datetime.now().isoformat(timespec="seconds"),
                "reply_id": rid, "to": item.get("username"),
                "their_text": (item.get("their_text") or "")[:120],
                "our_text": text, "published_id": new_id,
            }, ensure_ascii=False) + "\n")
        print(f"[publish] 완료 → @{item.get('username')}")
        time.sleep(2)

    save_json(REPLIED_PATH, sorted(replied))
    if kept:
        save_json(out_path, {"replies": kept})
    else:
        try:
            os.remove(out_path)
        except OSError:
            save_json(out_path, {"replies": []})
    print(f"[publish] {done}건 게시 (오늘 누적 {used_today + done}/{MAX_PER_DAY})")
    return done


def main():
    args = set(sys.argv[1:])
    folder = find_folder()
    if not folder:
        print("[reply_sync] 연결 폴더를 못 찾음. 중단")
        return 0
    if not os.path.exists(HISTORY_PATH):
        print("[reply_sync] 저장소 루트에서 실행해야 한다")
        return 0

    token = load_token()
    me_id = os.environ["THREADS_USER_ID"]
    prof = api_get(me_id, token, fields="username")
    me = (prof or {}).get("username")
    if not me:
        print("[reply_sync] 계정 확인 실패. 토큰 만료 가능성")
        return 1

    do_pub = ("--collect" not in args)
    do_col = ("--publish" not in args)

    if do_pub:
        publish(token, me, me_id, folder, dry_run="--dry-run" in args)
    if do_col:
        collect(token, me, folder)
    return 0


if __name__ == "__main__":
    sys.exit(main())
