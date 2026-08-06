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

HASHTAGS = ["#밸런스게임", "#선택장애", "#TMI", "#공감"]


def load_history(history_path: str) -> dict:
    if not os.path.exists(history_path):
        return {"entries": []}
    with open(history_path, "r", encoding="utf-8") as f:
        return json.load(f)


def pick_question(history: dict) -> dict:
    """최근에 안 쓴 질문 우선 선택. 전체를 다 쓰면 다시 처음부터 순환."""
    entries = history.get("entries", [])
    used_ids = [e.get("question_id") for e in entries if e.get("question_id")]
    recent_used = set(used_ids[-(len(QUESTIONS) - 1):])  # 전체 뱅크를 거의 다 돌기 전엔 반복 안 함

    candidates = [q for q in QUESTIONS if q["id"] not in recent_used]
    if not candidates:
        candidates = QUESTIONS
    return random.choice(candidates)


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

    setup_lines = q["setup"].split("\n")
    part1 = setup_lines[0]
    part2 = setup_lines[1] if len(setup_lines) > 1 else ""

    closing = build_closing(q)
    tags = " ".join(random.sample(HASHTAGS, 2))
    part3 = f"{closing}\n{tags}"

    comment_type, comment_text = pick_comment_type(history, blog_url, today=today)

    return {
        "question_id": q["id"],
        "category": q["category"],
        "part1": part1,
        "part2": part2,
        "part3": part3,
        "option_a": q["option_a"],
        "option_a_sub": q["option_a_sub"],
        "option_b": q["option_b"],
        "option_b_sub": q["option_b_sub"],
        "comment_type": comment_type,
        "comment_text": comment_text,
        "title": q["setup"].split("\n")[0],
    }


if __name__ == "__main__":
    result = build_thread("data/history.json", os.environ.get("BLOG_URL", ""))
    print(json.dumps(result, ensure_ascii=False, indent=2))
