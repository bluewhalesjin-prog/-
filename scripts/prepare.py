"""
1단계: 질문 선택 -> 본문 생성 -> (저녁 슬롯만) 카드 이미지 생성 -> data/draft.json 저장

2026-09 개편: 스레드는 텍스트 전용으로 발행한다(국내 '썰' 계정 실측상 텍스트 중심 글의
반응이 더 좋았음). 카드/슬라이드 이미지는 Instagram 캐러셀 크로스포스팅에만 쓰이므로
저녁 슬롯에서만 만든다.

환경변수:
  POST_SLOT=morning|evening (기본 evening)
    - morning : 텍스트만 생성. 이미지 생성/인스타 발행 없음.
    - evening : 텍스트 + 카드/슬라이드 이미지 생성. 인스타 캐러셀 크로스포스팅 대상.
  BLOG_URL (선택)
"""
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from generate_post import build_thread

HISTORY_PATH = "data/history.json"
CARDS_DIR = "data/cards"
DRAFT_PATH = "data/draft.json"


def main():
    slot = os.environ.get("POST_SLOT", "evening").strip().lower()
    if slot not in ("morning", "evening"):
        slot = "evening"

    today = datetime.now().strftime("%Y-%m-%d")
    blog_url = os.environ.get("BLOG_URL", "")

    thread = build_thread(HISTORY_PATH, blog_url)
    print(f"[슬롯] {slot}")
    print("[생성 결과]", json.dumps(thread, ensure_ascii=False))

    draft = {
        "date": today,
        "slot": slot,
        "card_path": None,
        "ig_slide1_path": None,
        "ig_slide2_path": None,
        **thread,
    }

    if slot == "evening":
        # Instagram 캐러셀용 이미지 3장 (서사 슬라이드 2장 + VS 카드 1장)
        from make_card import make_vs_card, make_text_slide

        os.makedirs(CARDS_DIR, exist_ok=True)
        card_path = os.path.join(CARDS_DIR, f"{today}.png")
        make_vs_card(
            option_a=thread["option_a"],
            option_a_sub=thread["option_a_sub"],
            option_b=thread["option_b"],
            option_b_sub=thread["option_b_sub"],
            out_path=card_path,
        )
        ig_slide1_path = os.path.join(CARDS_DIR, f"{today}_1.png")
        ig_slide2_path = os.path.join(CARDS_DIR, f"{today}_2.png")
        make_text_slide(thread["part1"], ig_slide1_path, slide_no=1, slide_total=3)
        make_text_slide(thread["part2"], ig_slide2_path, slide_no=2, slide_total=3)

        draft["card_path"] = card_path
        draft["ig_slide1_path"] = ig_slide1_path
        draft["ig_slide2_path"] = ig_slide2_path

    with open(DRAFT_PATH, "w", encoding="utf-8") as f:
        json.dump(draft, f, ensure_ascii=False, indent=2)

    print(f"draft saved: {DRAFT_PATH} (slot={slot}, card={draft['card_path']})")


if __name__ == "__main__":
    main()
