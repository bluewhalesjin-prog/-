"""
Threads API 클라이언트: 토큰 갱신, 2단계 발행(컨테이너 생성 -> 퍼블리시), 답글 작성
"""
import os
import time
import requests

GRAPH = "https://graph.threads.com/v1.0"


def _post(url: str, params: dict, label: str) -> dict:
    resp = requests.post(url, data=params, timeout=20)
    if not resp.ok:
        print(f"[{label} 실패] status={resp.status_code}")
        print(f"[{label} 응답 본문] {resp.text}")
    resp.raise_for_status()
    return resp.json()


def _get(url: str, params: dict, label: str) -> dict:
    resp = requests.get(url, params=params, timeout=20)
    if not resp.ok:
        print(f"[{label} 실패] status={resp.status_code}")
        print(f"[{label} 응답 본문] {resp.text}")
    resp.raise_for_status()
    return resp.json()


def refresh_token(token: str) -> dict:
    """장기 토큰 갱신. 발급 후 24시간 이상 지난 토큰만 갱신 가능."""
    return _get(
        "https://graph.threads.com/refresh_access_token",
        {"grant_type": "th_refresh_token", "access_token": token},
        "토큰 갱신",
    )


def create_text_container(user_id: str, token: str, text: str, reply_to_id: str = None) -> str:
    params = {"media_type": "TEXT", "text": text, "access_token": token}
    if reply_to_id:
        params["reply_to_id"] = reply_to_id
    data = _post(f"{GRAPH}/{user_id}/threads", params, "텍스트 컨테이너 생성")
    return data["id"]


def create_image_container(user_id: str, token: str, text: str, image_url: str, reply_to_id: str = None) -> str:
    params = {
        "media_type": "IMAGE",
        "image_url": image_url,
        "text": text,
        "access_token": token,
    }
    if reply_to_id:
        params["reply_to_id"] = reply_to_id
    data = _post(f"{GRAPH}/{user_id}/threads", params, "이미지 컨테이너 생성")
    return data["id"]


def publish_container(user_id: str, token: str, creation_id: str) -> str:
    data = _post(
        f"{GRAPH}/{user_id}/threads_publish",
        {"creation_id": creation_id, "access_token": token},
        "발행",
    )
    return data["id"]


def get_permalink(post_id: str, token: str) -> str:
    data = _get(
        f"{GRAPH}/{post_id}",
        {"fields": "permalink", "access_token": token},
        "퍼머링크 조회",
    )
    return data.get("permalink", "")


def publish_thread_sequence(user_id: str, token: str, parts: list[str], image_url: str,
                             comment_text: str = None) -> dict:
    """
    parts: [part1, part2, part3] 텍스트 리스트. part3에 이미지가 붙는다.
    각 파트는 이전 파트에 대한 답글(reply_to_id)로 이어붙인다.
    """
    post_ids = []
    prev_id = None
    for i, text in enumerate(parts):
        if i == len(parts) - 1 and image_url:
            cid = create_image_container(user_id, token, text, image_url, reply_to_id=prev_id)
        else:
            cid = create_text_container(user_id, token, text, reply_to_id=prev_id)
        time.sleep(3)
        pid = publish_container(user_id, token, cid)
        post_ids.append(pid)
        prev_id = pid
        time.sleep(2)

    result = {"post_ids": post_ids, "root_id": post_ids[0]}
    result["permalink"] = get_permalink(post_ids[0], token)

    if comment_text:
        time.sleep(2)
        ccid = create_text_container(user_id, token, comment_text, reply_to_id=post_ids[-1])
        time.sleep(3)
        comment_id = publish_container(user_id, token, ccid)
        result["comment_id"] = comment_id

    return result


if __name__ == "__main__":
    # 단독 실행 시 토큰 갱신만 테스트
    tok = os.environ["THREADS_ACCESS_TOKEN"]
    print(refresh_token(tok))
