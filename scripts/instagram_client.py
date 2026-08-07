"""
Instagram Graph API 클라이언트: 이미지 컨테이너 생성 -> 상태 확인 -> 퍼블리시
(Threads 발행에 실패 영향을 주지 않도록 publish.py에서 별도로 감싸서 호출한다)

주의: Instagram 로그인(Instagram Login) 방식으로 발급받은 토큰(IGAA로 시작)은
graph.facebook.com이 아니라 graph.instagram.com 으로 호출해야 한다.
"""
import time
import requests

GRAPH = "https://graph.instagram.com/v21.0"


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


def create_image_container(ig_user_id: str, token: str, image_url: str, caption: str) -> str:
    params = {
        "image_url": image_url,
        "caption": caption,
        "access_token": token,
    }
    data = _post(f"{GRAPH}/{ig_user_id}/media", params, "IG 이미지 컨테이너 생성")
    return data["id"]


def create_carousel_item(ig_user_id: str, token: str, image_url: str) -> str:
    """캐러셀에 들어갈 자식(child) 이미지 컨테이너를 생성한다 (캡션 없음)."""
    params = {
        "image_url": image_url,
        "is_carousel_item": "true",
        "access_token": token,
    }
    data = _post(f"{GRAPH}/{ig_user_id}/media", params, "IG 캐러셀 아이템 생성")
    return data["id"]


def create_carousel_container(ig_user_id: str, token: str, children_ids: list, caption: str) -> str:
    """자식 컨테이너 id 목록을 묶어 캐러셀(부모) 컨테이너를 생성한다."""
    params = {
        "media_type": "CAROUSEL",
        "children": ",".join(children_ids),
        "caption": caption,
        "access_token": token,
    }
    data = _post(f"{GRAPH}/{ig_user_id}/media", params, "IG 캐러셀 컨테이너 생성")
    return data["id"]


def wait_until_ready(container_id: str, token: str, timeout_sec: int = 60, interval_sec: int = 3) -> None:
    """컨테이너가 FINISHED 상태가 될 때까지 대기 (IN_PROGRESS -> FINISHED/ERROR)."""
    elapsed = 0
    while elapsed < timeout_sec:
        data = _get(
            f"{GRAPH}/{container_id}",
            {"fields": "status_code", "access_token": token},
            "IG 컨테이너 상태 조회",
        )
        status = data.get("status_code")
        if status == "FINISHED":
            return
        if status == "ERROR":
            raise RuntimeError(f"IG 컨테이너 처리 실패: {data}")
        time.sleep(interval_sec)
        elapsed += interval_sec
    raise TimeoutError("IG 컨테이너 처리 대기 시간 초과")


def publish_container(ig_user_id: str, token: str, creation_id: str) -> str:
    data = _post(
        f"{GRAPH}/{ig_user_id}/media_publish",
        {"creation_id": creation_id, "access_token": token},
        "IG 발행",
    )
    return data["id"]


def get_permalink(media_id: str, token: str) -> str:
    data = _get(
        f"{GRAPH}/{media_id}",
        {"fields": "permalink", "access_token": token},
        "IG 퍼머링크 조회",
    )
    return data.get("permalink", "")


def publish_image_post(ig_user_id: str, token: str, image_url: str, caption: str) -> dict:
    """이미지 1장 + 캡션으로 Instagram 피드 게시물을 발행한다."""
    creation_id = create_image_container(ig_user_id, token, image_url, caption)
    wait_until_ready(creation_id, token)
    media_id = publish_container(ig_user_id, token, creation_id)
    permalink = get_permalink(media_id, token)
    return {"media_id": media_id, "permalink": permalink}


def publish_carousel_post(ig_user_id: str, token: str, image_urls: list, caption: str) -> dict:
    """여러 장의 이미지를 캐러셀(슬라이드)로 묶어 Instagram에 발행한다."""
    children_ids = []
    for url in image_urls:
        cid = create_carousel_item(ig_user_id, token, url)
        wait_until_ready(cid, token)
        children_ids.append(cid)

    parent_id = create_carousel_container(ig_user_id, token, children_ids, caption)
    wait_until_ready(parent_id, token)
    media_id = publish_container(ig_user_id, token, parent_id)
    permalink = get_permalink(media_id, token)
    return {"media_id": media_id, "permalink": permalink}
