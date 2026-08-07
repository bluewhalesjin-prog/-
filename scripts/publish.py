"""
2단계: data/draft.json 을 읽어 실제 Threads 발행(또는 DRY_RUN)까지 수행하고
history.json / last_result.json 을 갱신한다. 이미지가 이미 공개 URL로 접근 가능해야 한다.
Threads 발행이 끝나면 동일 콘텐츠를 Instagram에도 캐러셀(서사 슬라이드 2장 + VS 카드 1장)로
크로스포스팅한다 (IG_ACCESS_TOKEN / IG_USER_ID가 설정된 경우에만 시도하며,
실패해도 Threads 결과에는 영향 없음).
환경변수:
THREADS_ACCESS_TOKEN, THREADS_USER_ID (필수)
IMAGE_BASE_URL (필수. 예: https://cdn.jsdelivr.net/gh/OWNER/REPO@SHA)
IG_ACCESS_TOKEN, IG_USER_ID (선택. Instagram 크로스포스팅용)
DRY_RUN=true (선택)
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import threads_client
import instagram_client

STATE_DIR = "data/state"
HISTORY_PATH = "data/history.json"
DRAFT_PATH = "data/draft.json"


def load_token() -> str:
    cached = os.path.join(STATE_DIR, "token.txt")
    if os.path.exists(cached):
        with open(cached, "r", encoding="utf-8") as f:
            tok = f.read().strip()
        if tok:
            return tok
    return os.environ["THREADS_ACCESS_TOKEN"]


def save_token(token: str):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(os.path.join(STATE_DIR, "token.txt"), "w", encoding="utf-8") as f:
        f.write(token)


def append_history(entry: dict):
    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            history = json.load(f)
    else:
        history = {"entries": []}
    history["entries"].append(entry)
    history["entries"] = history["entries"][-90:]
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def build_instagram_caption(draft: dict) -> str:
    """캡션 앞부분(125~150자)이 가장 중요하므로 이미 후킹용으로 다듬어진
    part1을 그대로 앞에 쓰고, 스와이프 유도 문구 + part3에 있는 해시태그를 붙인다."""
    hook = draft.get("part1", "")
    hashtags = " ".join(
        tok for tok in (draft.get("part3") or "").split() if tok.startswith("#")
    )
    caption = f"{hook}\n\n👉 스와이프해서 마지막 장 밸런스게임 확인!"
    if hashtags:
        caption += f"\n\n{hashtags}"
    return caption


def cross_post_instagram(draft: dict, image_base: str, image_url: str, dry_run: bool) -> dict:
    """IG_ACCESS_TOKEN/IG_USER_ID가 설정된 경우에만 Instagram에 캐러셀로 발행한다."""
    ig_token = os.environ.get("IG_ACCESS_TOKEN")
    ig_user_id = os.environ.get("IG_USER_ID")
    if not ig_token or not ig_user_id:
        return {"instagram_published": False, "instagram_skipped_reason": "IG_ACCESS_TOKEN/IG_USER_ID 미설정"}

    slide1_path = draft.get("ig_slide1_path")
    slide2_path = draft.get("ig_slide2_path")
    if not slide1_path or not slide2_path:
        return {"instagram_published": False, "instagram_skipped_reason": "ig_slide 경로 없음 (draft.json 확인 필요)"}

    image_urls = [
        f"{image_base}/{slide1_path}",
        f"{image_base}/{slide2_path}",
        image_url,
    ]
    caption = build_instagram_caption(draft)

    if dry_run:
        print(f"[DRY_RUN] Instagram 캐러셀 발행 생략. 캡션 미리보기:\n{caption}")
        print(f"[DRY_RUN] 슬라이드 URL: {image_urls}")
        return {"instagram_published": False, "instagram_skipped_reason": "DRY_RUN"}

    try:
        ig_result = instagram_client.publish_carousel_post(
            ig_user_id=ig_user_id,
            token=ig_token,
            image_urls=image_urls,
            caption=caption,
        )
        print(f"[Instagram 발행 성공] {ig_result['permalink']}")
        return {
            "instagram_published": True,
            "instagram_media_id": ig_result["media_id"],
            "instagram_permalink": ig_result["permalink"],
        }
    except Exception as e:
        print(f"[경고] Instagram 발행 실패 (Threads 발행 결과에는 영향 없음): {e}")
        return {"instagram_published": False, "instagram_error": str(e)}


def main():
    with open(DRAFT_PATH, "r", encoding="utf-8") as f:
        draft = json.load(f)

    dry_run = os.environ.get("DRY_RUN", "false").lower() == "true"
    token = load_token()
    user_id = os.environ["THREADS_USER_ID"]
    image_base = os.environ["IMAGE_BASE_URL"].rstrip("/")
    image_url = f"{image_base}/{draft['card_path']}"

    result = {
        "date": draft["date"],
        "question_id": draft["question_id"],
        "category": draft["category"],
        "comment_type": draft["comment_type"],
        "cta_index": draft["comment_type"].split(":")[1] if ":" in draft["comment_type"] else None,
        "card_image": draft["card_path"],
        "image_url": image_url,
        "published": False,
    }

    if dry_run:
        print(f"[DRY_RUN] 발행 생략. 이미지 URL 확인용: {image_url}")
    else:
        publish_result = threads_client.publish_thread_sequence(
            user_id=user_id,
            token=token,
            parts=[draft["part1"], draft["part2"], draft["part3"]],
            image_url=image_url,
            comment_text=draft["comment_text"],
        )
        result["published"] = True
        result["permalink"] = publish_result["permalink"]
        result["post_ids"] = publish_result["post_ids"]

        try:
            refreshed = threads_client.refresh_token(token)
            save_token(refreshed["access_token"])
        except Exception as e:
            print(f"[경고] 토큰 갱신 실패, 기존 토큰 유지: {e}")

    result.update(cross_post_instagram(draft, image_base, image_url, dry_run))

    append_history(result)
    with open("data/last_result.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
