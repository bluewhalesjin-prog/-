"""
우리 글에 달린 답글을 수집하고, 작성된 회신 문안을 게시한다.

2026-09-16 신설 / 2026-09-17 전면 수정.

[왜 고쳤나 — 측정 결과]
9/16에 자동 회신 4건이 나갔다. 결과가 이랬다.

    상대 답글 좋아요 → 우리 회신 좋아요
      35  →  2   (5.7%)
      17  →  2   (11.8%)
       6  →  1
       1  →  1
    4,400 → 182   (4.1%)   ← 계정 주인이 직접 단 것

읽히는 건 하나다. 우리 회신이 받는 반응은 문안 품질이 아니라
"그 답글이 몇 명에게 보이느냐"로 거의 전부 결정된다.
비율이 4~6%로 붙어 있다.

그러니 회신은 알고리즘 가점 장치가 아니다. 인기 답글 밑에 우리 이름을
걸어두는 자리 확보 장치다. 자리가 나쁘면 아무리 잘 써도 좋아요 2개다.

결론: 하루 20건을 아무 데나 다는 것보다 상위 1~2건에만 다는 게 낫다.
그래서 한도를 20 → 4로 줄였다.

[insights를 왜 뺐나]
GET /{id}/insights 는 내 소유 미디어만 조회된다. 후보 답글은 전부 남의
것이라 likes가 구조적으로 항상 0이다. 버그가 아니라 API 제약이다.
호출해봐야 시간만 쓰고 0을 받으므로 아예 제거했다.

  → 답글별 좋아요는 Cowork 쪽에서 브라우저로 원글 스레드를 열어 읽는다.
     그래서 이 스크립트는 inbox에 post_permalink를 반드시 같이 넣는다.
     그게 없으면 Cowork가 좋아요를 볼 방법이 없다.

[이 스크립트의 역할]
순위를 매기지 않는다. 후보를 넓게 모아서 넘기는 게 일이다.
진짜 선별은 좋아요를 볼 수 있는 Cowork가 한다.

파이프라인
  ① 이 스크립트(맥, 2시간마다)  outbox에 대기 중인 문안을 게시
  ② 이 스크립트                 최근 글의 미회신 답글 + 원글 링크를 수집 → inbox
  ③ Cowork 예약 작업            원글을 브라우저로 열어 좋아요 확인 →
                                상위 1~2건에만 문안 작성 → outbox
  다시 ①로.

파일 (연결 폴더)
  replies_inbox.json    수집된 답글 후보 (이 스크립트가 씀, Cowork가 읽음)
  replies_outbox.json   게시 대기 문안 (Cowork가 씀, 이 스크립트가 읽고 비움)
  replies_log.jsonl     게시 기록 (추적용)
  followers_log.jsonl   매 실행 시 팔로워 수 (회신한 날 / 안 한 날 비교용)

안전장치
  - 우리 글에 달린 답글만 본다. 남의 글에는 절대 안 간다
  - 이미 회신한 답글은 건너뛴다. 게시 직전에 API로 한 번 더 확인한다
  - 한 번에 최대 2개, 하루 최대 4개
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
FOLLOWERS_LOG = "followers_log.jsonl"

MAX_PER_RUN = 2          # 한 번에 게시할 최대 개수 (5 → 2)
MAX_PER_DAY = 4          # 하루 총량 (20 → 4)
LOOKBACK_DAYS = 3        # 최근 며칠 글까지 훑을지
SCAN_LIMIT = 50          # 글 하나당 훑을 답글 수
CAND_CAP = 60            # inbox에 넘길 후보 상한. Cowork가 좋아요 보고 다시 고른다
MIN_LEN = 15             # 이보다 짧으면 회신할 말이 안 나온다 (6 → 15)

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


def already_replied(reply_id, me, token):
    """그 답글 아래에 우리 회신이 이미 있는지 API로 확인한다."""
    d = api_get(f"{reply_id}/replies", token, fields="id,username", limit=25)
    if not d:
        return False
    return any(x.get("username") == me for x in d.get("data", []))


def age_hours(raw, now):
    """Threads는 '2026-09-16T07:38:54+0000' 형식을 준다. 콜론이 없어서
    fromisoformat이 못 읽는다(3.11 미만). strptime %z는 둘 다 처리한다."""
    raw = (raw or "").strip()
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


def collect(token, me, folder):
    """후보를 넓게 모아서 넘긴다. 순위는 매기지 않는다.

    좋아요를 볼 수 없으므로 여기서 순위를 매기면 반드시 틀린다.
    (9/16에 신선도 기준으로 골랐다가 '감덩이네...' 같은 걸 상위로 올렸다.)
    길이로 약하게 거르기만 하고, 진짜 선별은 Cowork에 맡긴다.
    """
    replied = set(load_json(REPLIED_PATH, []))
    now = datetime.now(timezone.utc)
    posts, cands = [], []

    for date, pid in recent_post_ids():
        d = api_get(pid, token, fields="id,text,permalink")
        root_text = (d or {}).get("text", "")[:120]
        root_link = (d or {}).get("permalink", "")
        res = api_get(f"{pid}/replies", token,
                      fields="id,text,username,timestamp,permalink",
                      reverse="true", limit=SCAN_LIMIT)
        if not res:
            continue

        n_before = len(cands)
        for r in res.get("data", []):
            rid = r.get("id")
            txt = (r.get("text") or "").strip()
            if not rid or not txt:
                continue
            if r.get("username") == me or rid in replied:
                continue
            if BLOCK.search(txt):
                continue
            if len(txt) < MIN_LEN:
                continue
            cands.append({
                "reply_id": rid,
                "username": r.get("username"),
                "text": txt,
                "age_h": round(age_hours(r.get("timestamp"), now), 1),
                "is_question": bool(QUESTION.search(txt)),
                "permalink": r.get("permalink"),
                "post_id": pid,
                "post_date": date,
                "post_permalink": root_link,
                "post_excerpt": root_text,
            })

        posts.append({
            "post_id": pid,
            "date": date,
            "permalink": root_link,
            "excerpt": root_text,
            "candidates_here": len(cands) - n_before,
        })

    # 긴 답글이 좋아요를 더 받는 경향이 있다(9/16 표본에서 확인). 약한 사전 필터일 뿐이다.
    cands.sort(key=lambda c: -len(c["text"]))
    top = cands[:CAND_CAP]

    save_json(os.path.join(folder, INBOX), {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "account": me,
        "how_to_pick": (
            "순위가 매겨져 있지 않다. 길이순일 뿐이다. "
            "posts[].permalink 를 브라우저로 열어 답글별 좋아요를 직접 읽고, "
            "좋아요가 가장 많은 1~2건에만 회신한다. "
            "좋아요 10 미만이면 회신하지 않는다."
        ),
        "posts": posts,
        "candidates": top,
    })
    print(f"[collect] 후보 {len(top)}건 / 원글 {len(posts)}건 저장 (전체 {len(cands)}건)")
    return len(top)


def today_count(folder):
    path = os.path.join(folder, LOGFILE)
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


def followers_now(me_id, token):
    """팔로워 수. threads_insights의 followers_count는 total_value로 온다."""
    d = api_get(f"{me_id}/threads_insights", token, quiet=True,
                metric="followers_count")
    if not d:
        return None
    for m in d.get("data", []):
        if m.get("name") != "followers_count":
            continue
        tv = m.get("total_value") or {}
        if tv.get("value") is not None:
            return int(tv["value"])
        vals = m.get("values") or []
        if vals:
            return int(vals[-1].get("value") or 0)
    return None


def log_followers(folder, me_id, token):
    """회신한 날과 안 한 날의 팔로워 증감을 나중에 비교하려고 남긴다.
    이게 '회신이 효과 있나'를 판정할 유일한 근거다. 조회 실패해도 줄은 남긴다."""
    n = followers_now(me_id, token)
    rec = {
        "at": datetime.now().isoformat(timespec="seconds"),
        "followers": n,
        "replies_today": today_count(folder),
    }
    try:
        with open(os.path.join(folder, FOLLOWERS_LOG), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError as e:
        print(f"[followers] 기록 실패: {e}")
        return
    print(f"[followers] {n if n is not None else '조회실패'} "
          f"(오늘 회신 {rec['replies_today']}건)")


def publish(token, me, me_id, folder, dry_run=False):
    out_path = os.path.join(folder, OUTBOX)
    data = load_json(out_path, None)
    if not data or not data.get("replies"):
        print("[publish] 게시할 문안 없음")
        return 0

    used_today = today_count(folder)
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
                "their_likes": item.get("their_likes"),
                "their_text": (item.get("their_text") or "")[:120],
                "our_text": text, "published_id": new_id,
            }, ensure_ascii=False) + "\n")
        print(f"[publish] 완료 → @{item.get('username')} "
              f"(상대 답글 좋아요 {item.get('their_likes', '?')})")
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
    log_followers(folder, me_id, token)
    return 0


if __name__ == "__main__":
    sys.exit(main())
