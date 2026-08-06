"""
Threads API 클라이언트: 토큰 갱신, 2단계 발행(컨테이너 생성 -> 퍼블리시), 답글 작성
"""
import os
import time
import requests

GRAPH = "https://graph.threads.net/v1.0"


def refresh_token(token: str) -> dict:
    resp = requests.get(
        "https://graph.threads.net/refresh_access_token",
        params={"grant_type": "th_refresh_token", "access_token": token},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def create_text_container(user_id: str, token: str, text: str, reply_to_id: str = None) -> str:
    params = {"media_type": "TEXT", "text": text, "access_token": token}
    if reply_to_id:
        params["reply_to_id"] = reply_to_id
    resp = requests.post(f"{GRAPH}/{user_id}/threads", data=params, timeout=20)
    resp.raise_for_status()
    return resp.json()["id"]


def create_image_container(user_id: str, token: str, text: str, image_url: str) -> str:
    params = {"media_type": "IMAGE", "image_url": image_url, "text": text, "access_token": token}
    resp = requests.post(f"{GRAPH}/{user_id}/threads", data=params, timeout=20)
    resp.raise_for_status()
    return resp.json()["id"]


def publish_container(user_id: str, token: str, creation_id: str) -> str:
    resp = requests.post(
        f"{GRAPH}/{user_id}/threads_publish",
        data={"creation_id": creation_id, "access_token": token},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def get_permalink(post_id: str, token: str) -> str:
    resp = requests.get(
        f"{GRAPH}/{post_id}",
        params={"fields": "permalink", "access_token": token},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("permalink", "")


def publish_thread_sequence(user_id: str, token: str, parts: list[str], image_url: str,
                             comment_text: str = None) -> dict:
    post_ids = []
    prev_id = None
    for i, text in enumerate(parts):
        if i == len(parts) - 1 and image_url:
            cid = create_image_container(user_id, token, text, image_url)
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
    tok = os.environ["THREADS_ACCESS_TOKEN"]
    print(refresh_token(tok))
