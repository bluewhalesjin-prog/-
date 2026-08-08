"""
격리된 읽기 전용 진단: THREADS_ACCESS_TOKEN/계정이 완전히 막힌 것인지,
아니면 발행(쓰기)만 막힌 것인지 확인한다. 어떤 발행/쓰기 동작도 하지 않는다.
"""
import os
import requests

token = os.environ["THREADS_ACCESS_TOKEN"]
user_id = os.environ["THREADS_USER_ID"]

print("=== 1) /me (기본 프로필 조회, 읽기 전용) ===")
resp = requests.get(
    "https://graph.threads.com/v1.0/me",
    params={"fields": "id,username,threads_profile_picture_url", "access_token": token},
    timeout=20,
)
print("status:", resp.status_code)
print("body:", resp.text)

print()
print("=== 2) 발행 한도 조회 (threads_publishing_limit, 읽기 전용) ===")
resp2 = requests.get(
    f"https://graph.threads.com/v1.0/{user_id}/threads_publishing_limit",
    params={"fields": "quota_usage,config", "access_token": token},
    timeout=20,
)
print("status:", resp2.status_code)
print("body:", resp2.text)
