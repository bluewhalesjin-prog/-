"""
임시 테스트 스크립트: Instagram 크로스포스팅 로직만 단독으로 검증한다.
Threads 쪽 코드는 전혀 건드리지 않는다. 검증 후 이 파일과 전용 워크플로우는 삭제 예정.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import instagram_client

def main():
    ig_token = os.environ["IG_ACCESS_TOKEN"]
    ig_user_id = os.environ["IG_USER_ID"]

    with open("data/last_result.json", "r", encoding="utf-8") as f:
        last = json.load(f)
    image_url = last["image_url"]

    caption = "[테스트] Instagram 연동 확인용 게시물입니다. 정상 확인 후 삭제됩니다."

    result = instagram_client.publish_image_post(
        ig_user_id=ig_user_id,
        token=ig_token,
        image_url=image_url,
        caption=caption,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
