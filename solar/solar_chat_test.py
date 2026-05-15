# solar_prac/solar_chat_test.py

import os
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

response = client.chat.completions.create(
    model="solar-pro3",
    messages=[
        {
            "role": "system",
            "content": (
                "너는 ICAC 2026 예선 본선 진출을 목표로 하는 AI 해커톤 코치다. "
                "답변은 문제 정의, 대상 사용자, AI 활용 방식, 구현 가능성, 기대 효과, 리스크, 성과 지표 순서로 작성한다."
            )
        },
        {
            "role": "user",
            "content": "AI로 캠퍼스 내 반복 민원을 줄이는 솔루션을 제안해줘."
        }
    ],
    temperature=0.3,
)

print(response.choices[0].message.content)