# pipeline_prac/make_icac_answer.py

import os
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

api_key = os.getenv("ICAC_KEY")
if not api_key:
    raise ValueError("ICAC_KEY가 .env에 없습니다.")

client = OpenAI(
    api_key=api_key,
    base_url="https://api.upstage.ai/v1"
)

parsed_path = Path("docparse_prac/outputs/parse.md")

if not parsed_path.exists():
    raise FileNotFoundError(f"파싱 결과 파일이 없습니다: {parsed_path}")

parsed_text = parsed_path.read_text(encoding="utf-8")

problem = """
캠퍼스 생활에서 학생들이 겪는 불편을 AI로 해결하는 서비스를 제안하라.
문제 정의, 해결 방안, AI 활용 방식, 기대 효과, 리스크 대응을 포함하라.
"""

prompt = f"""
너는 ICAC 2026 예선 본선 진출을 목표로 하는 참가자다.

아래 문제에 대해 제출 가능한 답안을 작성해라.

[문제]
{problem}

[참고 문서: Document Parse 결과]
{parsed_text}

[작성 조건]
- 첫 문단만 읽어도 어떤 문제를 해결하는지 알 수 있어야 한다.
- 단순 챗봇 제안으로 끝내지 마라.
- AI 활용 방식은 최소 3개 이상 구체적으로 써라.
- 구현 가능성은 Django 백엔드, DB, API, 관리자 페이지 기준으로 현실적으로 써라.
- 개인정보, hallucination, 운영 부담 리스크를 반드시 포함해라.
- 성과 지표를 정량 또는 준정량으로 제시해라.

[출력 형식]
제목:
1. 문제 정의
2. 제안 솔루션
3. AI 활용 방식
4. 시스템 흐름
5. 구현 가능성
6. 기대 효과
7. 리스크 및 대응
8. 성과 지표
9. 결론
"""

response = client.chat.completions.create(
    model="solar-pro3",
    messages=[
        {
            "role": "system",
            "content": (
                "너는 ICAC 2026 예선에서 본선 진출 가능성이 높은 답안을 작성하는 AI 코치다. "
                "창의성보다 문제 적합성, 실현 가능성, AI 활용 설득력, 구조적 완성도를 우선한다."
            )
        },
        {
            "role": "user",
            "content": prompt
        }
    ],
    temperature=0.25,
)

answer = response.choices[0].message.content

output_path = Path("pipeline_prac/icac_answer.md")
output_path.parent.mkdir(parents=True, exist_ok=True)
output_path.write_text(answer, encoding="utf-8")

print(answer)
print(f"\n[저장 완료] {output_path}")