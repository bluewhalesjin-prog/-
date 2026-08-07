"""
격리된 1회성 테스트: 이미 저장소에 커밋되어 있는 오늘자 draft.json/카드 이미지를 그대로 써서
Instagram 캐러셀 샘플 게시물을 실제로 1건 발행해본다. Threads 발행 로직은 전혀 건드리지 않는다.
검증이 끝나면 이 파일과 대응 워크플로우는 삭제한다.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import publish
import instagram_client


def main():
    with open("data/draft.json", "r", encoding="utf-8") as f:
        draft = json.load(f)

    image_base = os.environ["IMAGE_BASE_URL"].rstrip("/")
    image_url = f"{image_base}/{draft['card_path']}"
    image_urls = [
        f"{image_base}/{draft['ig_slide1_path']}",
        f"{image_base}/{draft['ig_slide2_path']}",
        image_url,
    ]
    caption = publish.build_instagram_caption(draft)
    print("캡션 미리보기:\n" + caption)
    print("슬라이드 URL:", image_urls)

    ig_token = publish.load_ig_token()
    ig_user_id = os.environ["IG_USER_ID"]

    result = instagram_client.publish_carousel_post(
        ig_user_id=ig_user_id,
        token=ig_token,
        image_urls=image_urls,
        caption=caption,
    )
    print("[발행 성공]", json.dumps(result, ensure_ascii=False))

    try:
        refreshed = instagram_client.refresh_token(ig_token)
        publish.save_ig_token(refreshed["access_token"])
        print("[토큰 갱신 성공]", refreshed.get("expires_in"), "초 후 만료")
    except Exception as e:
        print(f"[토큰 갱신 실패 - 발급 24시간 이내면 정상] {e}")


if __name__ == "__main__":
    main()
