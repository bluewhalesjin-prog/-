"""
1단계: 밸런스게임 질문 선택 -> 3파트 타래 생성 -> A/B 카드 이미지 생성 -> data/draft.json 저장
Instagram 캐러셀용 서사 텍스트 슬라이드(part1, part2) 이미지도 함께 생성한다.
"""
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from generate_post import build_thread
from make_card import make_vs_card, make_text_slide

HISTORY_PATH = "data/history.json"
CARDS_DIR = "data/cards"
DRAFT_PATH = "data/draft.json"


def main():
    os.makedirs(CARDS_DIR, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")

    blog_url = os.environ.get("BLOG_URL", "")
    thread = build_thread(HISTORY_PATH, blog_url)
    print("[생성 결과]", json.dumps(thread, ensure_ascii=False))

    card_path = os.path.join(CARDS_DIR, f"{today}.png")
    make_vs_card(
        option_a=thread["option_a"],
        option_a_sub=thread["option_a_sub"],
        option_b=thread["option_b"],
        option_b_sub=thread["option_b_sub"],
        out_path=card_path,
    )

    # Instagram 캐러셀용 서사 텍스트 슬라이드 (1/3, 2/3) - 3번째 슬라이드는 위 VS 카드 재사용
    ig_slide1_path = os.path.join(CARDS_DIR, f"{today}_1.png")
    ig_slide2_path = os.path.join(CARDS_DIR, f"{today}_2.png")
    make_text_slide(thread["part1"], ig_slide1_path, slide_no=1, slide_total=3)
    make_text_slide(thread["part2"], ig_slide2_path, slide_no=2, slide_total=3)

    draft = {
        "date": today,
        "card_path": card_path,
        "ig_slide1_path": ig_slide1_path,
        "ig_slide2_path": ig_slide2_path,
        **thread,
    }
    with open(DRAFT_PATH, "w", encoding="utf-8") as f:
        json.dump(draft, f, ensure_ascii=False, indent=2)

    print(f"draft saved: {DRAFT_PATH}, card: {card_path}, "
          f"ig_slides: [{ig_slide1_path}, {ig_slide2_path}]")


if __name__ == "__main__":
    main()
