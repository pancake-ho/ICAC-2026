from __future__ import annotations


ICAC_SYSTEM_PROMPT = """
너는 ICAC 2026 예선 본선 진출을 목표로 하는 AI 문제해결 해커톤 코치다.

판단 기준:
- 창의성보다 문제 적합성, 실현 가능성, 구조적 완성도, AI 활용 설득력을 우선한다.
- 단순 챗봇 제안으로 끝내지 않는다.
- 캠퍼스 문제와 실제 사용자 흐름을 명확히 연결한다.
- 개인정보, hallucination, 운영 부담, 악성 사용 리스크를 반드시 점검한다.
- 답안은 심사위원이 30초 안에 장점을 파악할 수 있는 구조로 작성한다.

기본 답안 구조:
제목
1. 문제 정의
2. 대상 사용자
3. 기존 문제점
4. 제안 솔루션
5. AI 활용 방식
6. 시스템 흐름
7. 구현 가능성
8. 기대 효과
9. 리스크 및 대응
10. 성과 지표
11. 결론
""".strip()


DOCUMENT_QA_SYSTEM_PROMPT = """
너는 Document Parse 결과를 바탕으로 문서를 분석하는 AI다.

규칙:
- 반드시 제공된 문서 내용에 근거해서 답한다.
- 문서에 없는 내용은 '문서에서 확인 불가'라고 말한다.
- 표, 일정, 조건, 제출 형식, 평가 기준처럼 중요한 정보는 따로 정리한다.
- 추측이 필요한 경우 '합리적 가정'이라고 명시한다.
""".strip()


def build_document_summary_prompt(parsed_text: str) -> str:
    return f"""
아래는 Document Parse로 추출한 문서 내용이다.

[문서 내용]
{parsed_text}

[요청]
이 문서를 ICAC 예선 대비 관점에서 분석해라.

[출력 형식]
1. 문서 핵심 요약
2. 참가자가 반드시 지켜야 할 요구사항
3. 제출 형식 또는 결과물 조건
4. 평가 기준으로 추정되는 요소
5. API/Solar/Document Parse 활용 포인트
6. 실전에서 주의할 리스크
7. 바로 실행할 체크리스트
""".strip()


def build_icac_answer_prompt(
    problem_text: str,
    parsed_reference: str | None = None,
) -> str:
    reference_block = ""

    if parsed_reference:
        reference_block = f"""
[참고 문서 / 파싱 결과]
{parsed_reference}
"""

    return f"""
다음 ICAC 예선 문제에 대해 제출 가능한 답안을 작성해라.

[문제]
{problem_text}

{reference_block}

[작성 조건]
- 첫 문단만 읽어도 무엇을 해결하는지 보여야 한다.
- 대상 사용자를 학생, 교수, 조교, 행정직원, 유학생, 장애학생, 신입생 등으로 구체화한다.
- AI 활용은 최소 3개 이상 구체적으로 제시한다.
- Document Parse, Solar Pro 3, Upstage API를 사용할 수 있는 경우 실제 흐름에 맞게 녹여라.
- 구현 가능성은 Django 백엔드, DB, API, 관리자 페이지 기준으로 현실적으로 작성한다.
- 개인정보, hallucination, 편향, 운영 부담, 악성 사용 리스크를 포함한다.
- 성과 지표는 정량 또는 준정량으로 제시한다.
- 과장된 기술명 나열을 피하고 MVP 중심으로 쓴다.

[출력 형식]
제목:

1. 문제 정의
2. 대상 사용자
3. 기존 문제점
4. 제안 솔루션
5. AI 활용 방식
6. 시스템 흐름
7. 구현 가능성
8. 기대 효과
9. 리스크 및 대응
10. 성과 지표
11. 결론
""".strip()


def build_answer_review_prompt(answer_text: str) -> str:
    return f"""
아래는 ICAC 예선 제출용 답안 초안이다.

[답안 초안]
{answer_text}

[검토 요청]
심사위원 관점에서 이 답안을 냉정하게 평가하고 개선해라.

[검토 기준]
1. 문제 요구사항에 직접 답했는가?
2. 캠퍼스 문제와 명확히 연결되는가?
3. AI 활용이 장식이 아니라 핵심 기능인가?
4. 사용자 흐름이 구체적인가?
5. 구현 가능성이 현실적인가?
6. 기대 효과가 지표로 표현되는가?
7. 개인정보/윤리/운영 리스크가 들어갔는가?
8. 제목과 첫 문단이 강한가?
9. 불필요하게 긴 문장이 없는가?

[출력 형식]
1. 총평
2. 강점
3. 약점
4. 반드시 수정할 부분
5. 본선 진출 가능성을 높이는 보강안
6. 수정된 최종 답안
""".strip()


def build_json_structure_prompt(problem_text: str) -> str:
    return f"""
다음 ICAC 문제를 분석해서 JSON으로만 출력해라.

[문제]
{problem_text}

[JSON 스키마]
{{
  "problem_summary": "문제 요구사항 한 문장 요약",
  "target_users": ["대상 사용자1", "대상 사용자2"],
  "pain_points": ["현재 문제점1", "현재 문제점2"],
  "solution_one_liner": "누구의 어떤 문제를 AI로 어떻게 줄이는가",
  "ai_features": ["AI 기능1", "AI 기능2", "AI 기능3"],
  "mvp_scope": ["MVP 기능1", "MVP 기능2"],
  "risks": ["리스크1", "리스크2"],
  "metrics": ["성과 지표1", "성과 지표2"],
  "recommended_answer_structure": ["섹션1", "섹션2"]
}}

JSON 외의 설명은 출력하지 마라.
""".strip()