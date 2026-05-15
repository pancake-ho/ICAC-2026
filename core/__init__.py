"""
ICAC 2026 실전용 Upstage API 파이프라인 패키지.

핵심 흐름:
    1. Document Parse로 문제 문서/공지/이미지를 구조화한다.
    2. Solar Pro 3로 문제 해석, 답안 생성, 검증을 수행한다.
    3. 결과를 outputs/에 제출 가능한 markdown 형태로 저장한다.
"""