"""
발행 소재 뱅크 진입점.

2026-09-08: 밸런스게임(v1) 포맷을 폐기하고 '썰'(v2) 포맷 전용으로 전환했다.
v1 66편은 이 파일에서 제거했으며, 필요하면 git 이력에서 복구할 수 있다.

폐기 이유
  - v1은 setup 2줄(약 260자) + "너넨 뭐 고를 듯?" 구조라 훅도 대사도 없었다.
  - 실측상 고성과 썰 게시물은 제목형 훅 + 직접 대사 + 이야기 요구형 마무리였고,
    우리 v1 글은 게시물당 좋아요가 1~2개에 그쳤다.

실제 소재는 question_bank_v2.py 에 있다. 새 글은 전부 그쪽에 추가한다.
이 파일은 기존 import 경로(from question_bank import QUESTIONS)를 유지하려고 남겨둔다.
"""

from question_bank_v2 import V2_QUESTIONS

QUESTIONS = V2_QUESTIONS
