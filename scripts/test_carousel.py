"""
임시 테스트 스크립트: Instagram 캐러셀(서사 슬라이드 2장 + VS 카드 1장) 발행만 단독으로 검증한다.
Threads 쪽 코드는 전혀 건드리지 않는다. 검증 후 이 파일과 전용 워크플로우는 삭제 예정.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import instagram_client
from publish import build_instagram_caption

def main():
    ig_token = os.environ["IG_ACCESS_TOKEN"]
    ig_user_id = os.environ["IG_USER_ID"]
    image_base = os.environ["IMAGE_BASE_URL"].rstrip("/")

    with open("data/draft.json", "r", encoding="utf-8") as f:
        draft = json.load(f)

    image_urls = [
        f"{image_base}/{draft['ig_slide1_path']}",
        f"{image_base}/{draft['ig_slide2_path']}",
        f"{image_base}/{draft['card_path']}",
    ]
    caption = "[테스트] " + build_instagram_caption(draft)

    print("슬라이드 URL:", image_urls)
    print("캡션:", caption)

    result = instagram_client.publish_carousel_post(
        ig_user_id=ig_user_id,
        token=ig_token,
        image_urls=image_urls,
        caption=caption,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
