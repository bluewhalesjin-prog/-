"""
1단계: 질문 선택 -> 본문 생성 -> (인스타 사용 시에만) 카드 이미지 생성 -> data/draft.json 저장

2026-09 개편: 스레드는 텍스트 전용으로 발행한다(국내 '썰' 계정 실측상 텍스트 중심 글의
반응이 더 좋았음). 카드/슬라이드 이미지는 Instagram 캐러셀 크로스포스팅에만 쓰인다.

2026-09-10: Instagram 운영을 중단했다.
  근거
    - 팔로워 5,000명 미만 계정에서 캐러셀은 비팔로워에게 사실상 도달하지 않는다.
      릴스가 게시물당 도달 3~5배이고, 작은 계정이 팔로워 밖으로 나가는 유일한 포맷이다.
    - 캐러셀이 이기는 지표(참여율 9~10%, 저장 2배, 프로필방문 3배)는 전부
      '이미 본 사람'에게서 나오는 숫자다. 볼 사람이 없으면 비율은 의미가 없다.
    - 게다가 기존 카드는 폐기된 밸런스게임(A/B VS) 포맷이라 썰 정체성과 어긋났다.
      정체성 수정과 도달 문제 해결이 별개 작업이라 둘 다 해야 겨우 출발선이었다.
    - 반면 스레드는 팔로워 25명으로 10만 조회가 나왔다. 되는 쪽에 자원을 몰아준다.
  코드는 지우지 않고 ENABLE_INSTAGRAM 스위치로 꺼둔다.
  나중에 릴스로 전환할 여력이 생기면 make_card.py 자산을 그대로 재활용할 수 있다.

환경변수:
  POST_SLOT=morning|evening (기본 evening)
    이제 두 슬롯 모두 텍스트 전용이다. 발행 시각 구분 용도로만 남아 있다.
  ENABLE_INSTAGRAM=true (기본 false)
    true일 때만 저녁 슬롯에서 카드 이미지를 만든다.
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

ENABLE_INSTAGRAM = os.environ.get("ENABLE_INSTAGRAM", "false").lower() == "true"


def main():
    slot = os.environ.get("POST_SLOT", "evening").strip().lower()
    if slot not in ("morning", "evening"):
        slot = "evening"

    today = datetime.now().strftime("%Y-%m-%d")
    blog_url = os.environ.get("BLOG_URL", "")

    thread = build_thread(HISTORY_PATH, blog_url)
    print(f"[슬롯] {slot} / 인스타 {'ON' if ENABLE_INSTAGRAM else 'OFF'}")
    print("[생성 결과]", json.dumps(thread, ensure_ascii=False))

    draft = {
        "date": today,
        "slot": slot,
        "card_path": None,
        "ig_slide1_path": None,
        "ig_slide2_path": None,
        **thread,
    }

    # 인스타를 켠 경우에만 이미지를 만든다.
    # 스레드 발행은 image_url=None으로 텍스트만 올리므로 이미지가 없어도 아무 문제 없다.
    if ENABLE_INSTAGRAM and slot == "evening":
        # Instagram 캐러셀용 이미지 3장 (서사 슬라이드 2장 + VS 카드 1장)
        # 주의: VS 카드는 폐기된 밸런스게임 포맷이다. 인스타를 다시 켤 거면
        #       카드 레이아웃부터 썰 서사형으로 재설계해야 한다.
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
