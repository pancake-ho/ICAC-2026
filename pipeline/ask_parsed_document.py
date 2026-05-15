# pipeline_prac/ask_parsed_document.py

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

question = "이 문서의 핵심 내용을 요약하고, ICAC 예선 문제 풀이에 활용할 수 있는 포인트를 정리해줘."

prompt = f"""
아래는 Document Parse로 추출한 문서 내용이다.

[문서 내용]
{parsed_text}

[질문]
{question}

[답변 조건]
1. 문서에 근거해서 답해라.
2. 문서에 없는 내용은 추측하지 말고 '문서에서 확인 불가'라고 써라.
3. ICAC 예선 답안에 활용 가능한 포인트를 따로 정리해라.
"""

response = client.chat.completions.create(
    model="solar-pro3",
    messages=[
        {
            "role": "system",
            "content": "너는 Document Parse 결과를 바탕으로 문서를 분석하는 AI다. 문서 근거 중심으로 답한다."
        },
        {
            "role": "user",
            "content": prompt
        }
    ],
    temperature=0.2,
)

print(response.choices[0].message.content)