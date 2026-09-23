"""
발행한 글의 실제 성과를 긁어서 data/metrics.json 에 쌓는다. (2026-09-22 신설)

왜 만들었나
  67건을 발행했는데 조회수가 기록된 건 6건뿐이었다.
  9%를 보고 만든 규칙으로 나머지 91%를 판단하고 있었다.
  history.json 에는 published / permalink 만 있고 성과 필드가 없었고,
  threads_client.py 에도 insights 호출이 아예 없었다.

설계 원칙
  1) 이 스크립트는 절대 발행을 막지 않는다. 무슨 일이 있어도 exit 0 이다.
     run_daily.sh 안에서 돌지만 실패는 로그만 남기고 넘어간다.
  2) history.json 은 최근 90건만 유지된다(publish.py 가 자른다).
     그래서 성과는 별도 파일 metrics.json 에 append-only 로 쌓는다. 여기선 안 자른다.
  3) 조회수는 누적값이고 며칠이면 평탄해진다.
     그래서 발행 후 8일 안쪽 글은 돌 때마다 최신값으로 덮어쓰고,
     한 번이라도 168시간(7일) 넘긴 시점에 찍힌 기록이 있으면 확정으로 보고 건너뛴다.
  4) 체인(타래) 한 편은 게시물이 3~4개다.
     1/3의 조회수가 '도달'이고, 답글·좋아요는 3/3에 몰린다.
     그래서 part1 조회수를 대표값으로 쓰고 나머지는 합계로 따로 남긴다.

사용법
  python3 scripts/collect_insights.py            # 수집
  python3 scripts/collect_insights.py --report   # 수집 없이 표만 출력
  python3 scripts/collect_insights.py --dry-run  # API 호출 없이 대상만 확인
"""
import json
import os
import sys
import time
import datetime as dt

import requests

GRAPH = "https://graph.threads.com/v1.0"

HISTORY_PATH = "data/history.json"
METRICS_PATH = "data/metrics.json"

# 발행 후 이 시간이 지난 기록이 이미 있으면 확정으로 보고 다시 안 긁는다.
FINAL_AGE_H = 168.0
# 이 기간보다 오래된 글은 아예 대상에서 뺀다(확정 기록이 없더라도).
WINDOW_DAYS = 10
# API 호출 상한. 토큰 쿼터를 지키기 위한 안전장치다.
MAX_CALLS = 250

MEDIA_METRICS = ["views", "likes", "replies", "reposts", "quotes", "shares"]
MEDIA_METRICS_MIN = ["views", "likes", "replies"]

SLOT_HOUR = {"morning": (8, 0), "evening": (19, 30)}

_calls = 0
_metric_set = MEDIA_METRICS


def log(msg):
    print(f"[insights] {msg}")


# ── 저장소 ────────────────────────────────────────────────────────────
def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_metrics(m):
    os.makedirs(os.path.dirname(METRICS_PATH), exist_ok=True)
    tmp = METRICS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=2)
    os.replace(tmp, METRICS_PATH)


def empty_metrics():
    return {"schema": 1, "posts": {}, "followers": []}


# ── 뱅크에서 훅/시리즈 정보 끌어오기 ──────────────────────────────────
def load_bank_index():
    """question_id -> {hook, category, series, ep}. 실패해도 빈 dict를 준다."""
    try:
        sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
        import question_bank_v2  # noqa

        idx = {}
        for q in question_bank_v2.V2_QUESTIONS:
            idx[q["id"]] = {
                "hook": q.get("hook", ""),
                "category": q.get("category", ""),
                "series": q.get("series"),
                "ep": q.get("ep"),
                "ep_total": q.get("ep_total"),
                "body_len": len(q.get("body", "")),
            }
        return idx
    except Exception as e:
        log(f"뱅크 로드 실패 (훅 정보 없이 진행): {e}")
        return {}


# ── API ───────────────────────────────────────────────────────────────
def _get(url, params, label):
    global _calls
    if _calls >= MAX_CALLS:
        raise RuntimeError(f"호출 상한 {MAX_CALLS} 도달")
    _calls += 1
    resp = requests.get(url, params=params, timeout=20)
    if not resp.ok:
        raise RuntimeError(f"{label} status={resp.status_code} body={resp.text[:300]}")
    return resp.json()


def parse_metric_rows(payload):
    """
    Threads insights 응답이 두 가지 모양으로 온다.
      {"name":"views","values":[{"value":123}]}
      {"name":"followers_count","total_value":{"value":123}}
    둘 다 받는다.
    """
    out = {}
    for row in payload.get("data", []):
        name = row.get("name")
        if not name:
            continue
        if "total_value" in row and isinstance(row["total_value"], dict):
            out[name] = row["total_value"].get("value")
        else:
            vals = row.get("values") or []
            if vals and isinstance(vals[0], dict):
                out[name] = vals[0].get("value")
    return out


def media_insights(post_id, token):
    """
    지원하지 않는 metric이 섞이면 400이 난다.
    한 번 실패하면 핵심 metric만으로 재시도하고, 그 뒤로는 계속 축소본만 쓴다.
    (매번 재시도하면 호출 수가 두 배가 된다.)
    """
    global _metric_set
    try:
        payload = _get(
            f"{GRAPH}/{post_id}/insights",
            {"metric": ",".join(_metric_set), "access_token": token},
            f"media {post_id}",
        )
        return parse_metric_rows(payload)
    except RuntimeError as e:
        if "status=400" not in str(e) or _metric_set == MEDIA_METRICS_MIN:
            raise
        log(f"metric 축소: {_metric_set} -> {MEDIA_METRICS_MIN}")
        _metric_set = MEDIA_METRICS_MIN
        payload = _get(
            f"{GRAPH}/{post_id}/insights",
            {"metric": ",".join(_metric_set), "access_token": token},
            f"media {post_id} (축소)",
        )
        return parse_metric_rows(payload)


def user_followers(user_id, token):
    payload = _get(
        f"{GRAPH}/{user_id}/threads_insights",
        {"metric": "followers_count", "access_token": token},
        "followers_count",
    )
    return parse_metric_rows(payload).get("followers_count")


# ── 시각 계산 ─────────────────────────────────────────────────────────
def published_at(entry):
    """history 엔트리에 정확한 타임스탬프가 없다. date + slot 으로 추정한다."""
    d = dt.datetime.strptime(entry["date"], "%Y-%m-%d")
    h, m = SLOT_HOUR.get(entry.get("slot", "morning"), (8, 0))
    return d.replace(hour=h, minute=m)


def age_hours(entry, now):
    return (now - published_at(entry)).total_seconds() / 3600.0


def key_of(entry):
    return f"{entry['date']}__{entry.get('slot','?')}__{entry.get('question_id','?')}"


# ── 수집 ──────────────────────────────────────────────────────────────
def collect(dry_run=False):
    token = os.environ.get("THREADS_ACCESS_TOKEN")
    user_id = os.environ.get("THREADS_USER_ID")
    if not token or not user_id:
        log("THREADS_ACCESS_TOKEN / THREADS_USER_ID 없음 - 수집 건너뜀")
        return

    history = load_json(HISTORY_PATH, {"entries": []})
    entries = history.get("entries", [])
    metrics = load_json(METRICS_PATH, empty_metrics())
    metrics.setdefault("posts", {})
    metrics.setdefault("followers", [])
    bank = load_bank_index()

    now = dt.datetime.now()
    targets = []
    for e in entries:
        if not e.get("published"):
            continue
        ids = e.get("post_ids") or []
        if not ids:
            continue
        age = age_hours(e, now)
        if age < 1 or age > WINDOW_DAYS * 24:
            continue
        prev = metrics["posts"].get(key_of(e))
        if prev and prev.get("age_h", 0) >= FINAL_AGE_H:
            continue  # 이미 확정 스냅샷이 있다
        targets.append((e, age))

    log(f"대상 {len(targets)}편 (전체 기록 {len(entries)}건, 누적 metrics {len(metrics['posts'])}편)")
    if dry_run:
        for e, age in targets:
            log(f"  - {key_of(e)} age={age:.0f}h parts={len(e.get('post_ids') or [])}")
        return

    ok, fail = 0, 0
    for e, age in targets:
        ids = e["post_ids"]
        parts = []
        try:
            for pid in ids:
                parts.append({"post_id": pid, **media_insights(pid, token)})
                time.sleep(0.3)
        except Exception as ex:
            fail += 1
            log(f"실패 {key_of(e)}: {ex}")
            if "호출 상한" in str(ex):
                break
            continue

        def total(name):
            return sum((p.get(name) or 0) for p in parts)

        qid = e.get("question_id", "")
        meta = bank.get(qid, {})
        metrics["posts"][key_of(e)] = {
            "question_id": qid,
            "date": e.get("date"),
            "slot": e.get("slot"),
            "category": e.get("category") or meta.get("category", ""),
            "series": meta.get("series"),
            "ep": meta.get("ep"),
            "hook": meta.get("hook", ""),
            "permalink": e.get("permalink"),
            "parts_count": len(parts),
            "views": (parts[0].get("views") if parts else None),  # 1/3 도달 = 대표값
            "views_all_parts": total("views"),
            "likes": total("likes"),
            "replies": total("replies"),
            "reposts": total("reposts"),
            "quotes": total("quotes"),
            "age_h": round(age, 1),
            "updated_at": now.isoformat(timespec="seconds"),
            "parts": parts,
        }
        ok += 1

    # 팔로워 수는 하루 한 번만 찍는다(일 증감을 보려면 이거면 충분하다).
    today = now.strftime("%Y-%m-%d")
    if not any(f.get("date") == today for f in metrics["followers"]):
        try:
            fc = user_followers(user_id, token)
            if fc is not None:
                metrics["followers"].append(
                    {"date": today, "at": now.isoformat(timespec="seconds"), "followers_count": fc}
                )
                log(f"팔로워 {fc}명 기록")
        except Exception as ex:
            log(f"팔로워 수집 실패: {ex}")

    save_metrics(metrics)
    log(f"수집 완료: 성공 {ok} / 실패 {fail} / API 호출 {_calls}회")


# ── 리포트 ────────────────────────────────────────────────────────────
def report():
    metrics = load_json(METRICS_PATH, empty_metrics())
    posts = list(metrics.get("posts", {}).values())
    if not posts:
        log("아직 쌓인 성과 데이터가 없습니다.")
        return

    posts.sort(key=lambda p: (p.get("views") or 0), reverse=True)
    print()
    print(f"{'조회':>8} {'답글':>5} {'좋아':>5} {'경과':>6}  {'분류':<8} 훅")
    print("-" * 100)
    for p in posts:
        ser = f"{p['series']}{p['ep']}" if p.get("series") else (p.get("category") or "")
        print(
            f"{(p.get('views') or 0):>8,} {(p.get('replies') or 0):>5} "
            f"{(p.get('likes') or 0):>5} {(p.get('age_h') or 0):>5.0f}h  "
            f"{ser:<8} {(p.get('hook') or p.get('question_id',''))[:44]}"
        )

    def avg(rows, k="views"):
        vals = [(r.get(k) or 0) for r in rows]
        return sum(vals) / len(vals) if vals else 0

    single = [p for p in posts if not p.get("series")]
    ep1 = [p for p in posts if p.get("ep") == 1]
    ep2 = [p for p in posts if p.get("ep") == 2]
    ep3 = [p for p in posts if p.get("ep") == 3]
    print()
    print(f"단편 {len(single):>3}편  평균 조회 {avg(single):>9,.0f}")
    print(f"1화  {len(ep1):>3}편  평균 조회 {avg(ep1):>9,.0f}")
    print(f"2화  {len(ep2):>3}편  평균 조회 {avg(ep2):>9,.0f}")
    print(f"3화  {len(ep3):>3}편  평균 조회 {avg(ep3):>9,.0f}")

    cats = {}
    for p in posts:
        cats.setdefault(p.get("category") or "?", []).append(p)
    print()
    for c, rows in sorted(cats.items(), key=lambda x: -avg(x[1])):
        print(f"{c:<10} {len(rows):>3}편  평균 조회 {avg(rows):>9,.0f}  평균 답글 {avg(rows,'replies'):>5.1f}")

    fols = metrics.get("followers", [])
    if len(fols) >= 2:
        print()
        print("팔로워 추이 (최근 14일)")
        prev = None
        for f in fols[-14:]:
            delta = "" if prev is None else f"  {f['followers_count']-prev:+d}"
            print(f"  {f['date']}  {f['followers_count']:>7,}{delta}")
            prev = f["followers_count"]


def main():
    args = set(sys.argv[1:])
    try:
        if "--report" in args:
            report()
        else:
            collect(dry_run=("--dry-run" in args))
            if "--quiet" not in args:
                report()
    except Exception as e:
        # 여기서 죽으면 발행 파이프라인에 영향이 가므로 반드시 삼킨다.
        log(f"예기치 못한 오류 (무시하고 종료): {e}")
    sys.exit(0)


if __name__ == "__main__":
    main()
