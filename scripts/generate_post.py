"""
스레드 3파트 타래 글 생성 (밸런스게임/질문형 포맷, AI 호출 없음)

- question_bank.py 에서 최근에 안 쓴 질문을 골라 사용 (전체를 다 돌 때까지 반복 방지)
- 1~2파트: 상황극 설정 (질문 뱅크의 setup 두 줄, 각 파트 약 62~70자 narrative)
- 3파트: 그 질문의 실제 option_a/option_b를 넣어 만든 맞춤형 마무리 질문
  (범용 문구 랜덤이 아니라 매번 소재 자체에 맞는 클로징) + A/B 카드 이미지 + 댓글 유도 문구
- 첫 댓글: 본진블로그/프로필유도/무댓글 랜덤, 빈도 제한(본진블로그 주 2회, 연속 금지)
"""
import json
import os
import random
from datetime import datetime, timedelta

from question_bank import QUESTIONS


def has_batchim(word: str) -> bool:
    """단어의 마지막 글자에 받침이 있는지 확인 (조사 이/가, 이랑/랑, 이냐/냐 등 선택용)."""
    if not word:
        return False
    last = word[-1]
    code = ord(last)
    if 0xAC00 <= code <= 0xD7A3:
        return (code - 0xAC00) % 28 != 0
    return False


def josa(word: str, with_batchim: str, without_batchim: str) -> str:
    return with_batchim if has_batchim(word) else without_batchim


# 마무리 질문 템플릿. {a}/{b}에 그 질문의 실제 option_a/option_b가 들어가서
# 매번 소재에 딱 맞는 클로징 질문이 되도록 함 (범용 랜덤 문구 지양).
# {a_nya}/{b_nya}는 "이냐/냐", {a_rang}는 "이랑/랑" 조사가 붙은 형태.
CLOSING_TEMPLATES = [
    "{a} vs {b}, 너넨 뭐 고를 듯?",
    "나는 진짜 고민되던데 {a_nya} {b_nya}, 너넨 뭐 고를 듯?",
    "{a_rang} {b} 중에 딱 하나만 골라야 한다면 뭐 고를 듯?",
    "이건 진짜 케바케인 듯. {a} vs {b}, 너네 선택은 뭐임?",
    "생각보다 반반으로 갈릴 듯. {a} 아니면 {b}, 댓글로 골라줘.",
]

PROFILE_CTAS = [
    "이런 밸런스게임 매일 하나씩 올림. 프로필 확인 🔍",
    "다음 밸런스게임도 궁금하면 프로필 눌러보셈 👆",
    "이런 거 계속 보고 싶으면 프로필 링크 확인 🔗",
    "매일 하나씩 새 질문 올리는 중. 프로필 확인 ✅",
    "선택장애 유발자 계속 보고 싶으면 프로필 확인 🫶",
    "다른 질문들도 궁금하면 프로필에 있음 🧑‍💻",
    "매일 새 밸런스게임 올림. 궁금하면 프로필 확인 🎁",
    "이런 콘텐츠 계속 받고 싶으면 프로필 확인 🧐",
    "지난 밸런스게임들도 프로필에 다 있음 📚",
    "재밌으면 프로필 눌러서 팔로우 ✍️",
]

# 2026-09-08: 썰 계정으로 전환하면서 해시태그도 교체.
# 실측상 고성과 썰 게시물이 쓰던 태그 위주로 구성했다.
HASHTAGS = ["#직장인썰", "#회사썰", "#썰", "#직장생활", "#공감"]


def load_history(history_path: str) -> dict:
    if not os.path.exists(history_path):
        return {"entries": []}
    with open(history_path, "r", encoding="utf-8") as f:
        return json.load(f)


# 카테고리별 선택 가중치. 실제 조회수 데이터상 직장생활 카테고리가 평균적으로
# 반응이 좋아 살짝 더 자주 뽑히도록 하되, 완전히 몰아주지는 않는다(다양성 유지).
CATEGORY_WEIGHTS = {
    "직장생활": 1.5,
    "연애": 1.0,
    "라이프스타일": 1.0,
    "가벼운취향": 1.0,
}


def published_ids(history: dict) -> list:
    """실제로 발행에 성공한 question_id만 발행 순서대로 반환.
    dry-run/실패 기록은 제외한다(예전 버그: 미발행 기록이 섞여 반복 방지가 조기 소진됨)."""
    return [
        e.get("question_id") for e in history.get("entries", [])
        if e.get("published") and e.get("question_id")
    ]


def unused_questions(history: dict) -> list:
    """아직 한 번도 발행된 적 없는 질문 목록 (재고 감시용)."""
    used = set(published_ids(history))
    return [q for q in QUESTIONS if q["id"] not in used]


def is_v2(q: dict) -> bool:
    """v2(썰 구조: hook/body/closing) 항목인지."""
    return bool(q.get("hook"))


def next_series_episode(history: dict):
    """진행 중인 시리즈가 있으면 그 다음 화를 돌려준다.
    1화가 나갔는데 2화가 안 나갔으면 2화를 반드시 먼저 발행해 순서를 보장한다."""
    used = set(published_ids(history))
    candidates = []
    for q in QUESTIONS:
        if not q.get("series") or q["id"] in used:
            continue
        ep = q.get("ep") or 1
        if ep == 1:
            continue
        prev = [p for p in QUESTIONS
                if p.get("series") == q["series"] and (p.get("ep") or 1) == ep - 1]
        if prev and prev[0]["id"] in used:
            candidates.append(q)
    if not candidates:
        return None
    return sorted(candidates, key=lambda q: (q["series"], q.get("ep") or 1))[0]


def pick_question(history: dict) -> dict:
    """중복 없이 뽑는다.
    0순위: 이미 시작된 시리즈의 다음 화 (순서가 꼬이면 안 되므로 최우선).
    1순위: 아직 안 쓴 v2(썰 구조) 항목. 구조가 개선된 글부터 소진한다.
    2순위: 아직 안 쓴 나머지 항목.
    3순위: 전부 소진됐을 때만 '가장 오래전에 쓴 것'부터 재사용해 간격을 최대로 벌린다.
           (예전에는 이 상황에서 전체를 무작위로 다시 열어버려 어제 질문까지 재등장했음)"""
    nxt = next_series_episode(history)
    if nxt:
        return nxt

    unused = unused_questions(history)
    if unused:
        # 시리즈 2화 이상은 위에서만 나가야 하므로 일반 추첨 대상에서 제외
        pool = [q for q in unused if (q.get("ep") or 1) == 1]
        if not pool:
            pool = unused
        v2_pool = [q for q in pool if is_v2(q)]
        target = v2_pool or pool
        weights = [CATEGORY_WEIGHTS.get(q["category"], 1.0) for q in target]
        return random.choices(target, weights=weights, k=1)[0]

    pubs = published_ids(history)
    last_seen = {}
    for i, qid in enumerate(pubs):
        last_seen[qid] = i
    return sorted(QUESTIONS, key=lambda q: last_seen.get(q["id"], -1))[0]


def build_closing(q: dict) -> str:
    """그 질문의 실제 option_a/option_b를 넣어 소재에 맞는 마무리 질문을 만든다."""
    a, b = q["option_a"], q["option_b"]
    template = random.choice(CLOSING_TEMPLATES)
    return template.format(
        a=a, b=b,
        a_nya=a + josa(a, "이냐", "냐"),
        b_nya=b + josa(b, "이냐", "냐"),
        a_rang=a + josa(a, "이랑", "랑"),
    )


def build_full_text(part1: str, part2: str, part3: str) -> str:
    """Threads 단일 포스트용 통합 본문.
    답글 체인 대신 포스트 1개로 발행해 조회수·참여가 분산되지 않도록 한다."""
    return f"{part1}\n\n{part2}\n\n{part3}"


def pick_comment_type(history: dict, blog_url: str, today=None) -> tuple[str, str]:
    """comment_type 랜덤 선택. 본진블로그는 주 2회, 연속 금지."""
    entries = history.get("entries", [])
    today = today or datetime.now().date()
    week_start = today - timedelta(days=today.weekday())

    this_week_blog_count = 0
    last_type = None
    for e in entries:
        try:
            edate = datetime.fromisoformat(e["date"]).date()
        except (KeyError, ValueError):
            continue
        if edate >= week_start and e.get("comment_type") == "본진블로그":
            this_week_blog_count += 1
        last_type = e.get("comment_type") if edate == today - timedelta(days=1) else last_type

    candidates = ["본진블로그", "프로필유도", "무댓글"]
    if not blog_url or this_week_blog_count >= 2 or last_type == "본진블로그":
        if "본진블로그" in candidates:
            candidates.remove("본진블로그")

    chosen = random.choice(candidates)

    if chosen == "본진블로그":
        return chosen, f"숨은 이야기 더 보기 👉 {blog_url}"
    if chosen == "프로필유도":
        used_recent = {e.get("cta_index") for e in entries[-3:] if e.get("comment_type") == "프로필유도"}
        pool = [i for i in range(len(PROFILE_CTAS)) if i not in used_recent] or list(range(len(PROFILE_CTAS)))
        idx = random.choice(pool)
        return f"프로필유도:{idx}", PROFILE_CTAS[idx]
    return "무댓글", None


def build_thread(history_path: str, blog_url: str, today=None) -> dict:
    history = load_history(history_path)
    q = pick_question(history)

    tags = " ".join(random.sample(HASHTAGS, 2))

    if is_v2(q):
        # v2 썰 구조: hook(제목형 훅) + body(대사 포함 본문) + closing(썰 요청형 CTA)
        hook, body, closing = q["hook"], q["body"], q["closing"]
        full_text = f"{hook}\n\n{body}\n\n{closing}\n{tags}"
        # Instagram 슬라이드는 짧아야 하므로 훅과 본문 첫 문단만 쓴다
        part1 = hook
        part2 = body.split("\n\n")[0]
        part3 = f"{closing}\n{tags}"
        title = hook
    else:
        # v1 구조(구버전): setup 2줄 + 자동 생성 클로징
        setup_lines = q["setup"].split("\n")
        part1 = setup_lines[0]
        part2 = setup_lines[1] if len(setup_lines) > 1 else ""
        closing = build_closing(q)
        part3 = f"{closing}\n{tags}"
        full_text = build_full_text(part1, part2, part3)
        title = part1

    comment_type, comment_text = pick_comment_type(history, blog_url, today=today)

    return {
        "question_id": q["id"],
        "category": q["category"],
        "format": "v2" if is_v2(q) else "v1",
        "series": q.get("series"),
        "ep": q.get("ep"),
        "ep_total": q.get("ep_total"),
        "part1": part1,
        "part2": part2,
        "part3": part3,
        "full_text": full_text,
        "option_a": q["option_a"],
        "option_a_sub": q["option_a_sub"],
        "option_b": q["option_b"],
        "option_b_sub": q["option_b_sub"],
        "comment_type": comment_type,
        "comment_text": comment_text,
        "title": title,
    }


if __name__ == "__main__":
    result = build_thread("data/history.json", os.environ.get("BLOG_URL", ""))
    print(json.dumps(result, ensure_ascii=False, indent=2))
