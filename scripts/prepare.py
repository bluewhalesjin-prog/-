"""
1단계: 밸런스게임 질문 선택 -> 3파트 타래 생성 -> A/B 카드 이미지 생성 -> data/draft.json 저장
"""
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from generate_post import build_thread
from make_card import make_vs_card

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

    draft = {"date": today, "card_path": card_path, **thread}
    with open(DRAFT_PATH, "w", encoding="utf-8") as f:
        json.dump(draft, f, ensure_ascii=False, indent=2)

    print(f"draft saved: {DRAFT_PATH}, card: {card_path}")


if __name__ == "__main__":
    main()
