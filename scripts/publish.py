"""
2단계: data/draft.json 을 읽어 실제 Threads 발행(또는 DRY_RUN)까지 수행하고
history.json / last_result.json 을 갱신한다. 이미지가 이미 공개 URL로 접근 가능해야 한다.

환경변수:
    THREADS_ACCESS_TOKEN, THREADS_USER_ID  (필수)
    IMAGE_BASE_URL                          (필수. 예: https://cdn.jsdelivr.net/gh/OWNER/REPO@SHA)
    DRY_RUN=true                            (선택)
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import threads_client

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

    append_history(result)
    with open("data/last_result.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
