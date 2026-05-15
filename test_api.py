import os
from dotenv import load_dotenv
from openai import OpenAI

# .env 파일 읽기
load_dotenv()

# .env에서 ICAC_KEY 가져오기
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
            "content": "너는 ICAC 2026 예선 문제를 푸는 AI 해커톤 코치다."
        },
        {
            "role": "user",
            "content": "AI로 캠퍼스 문제를 해결하는 아이디어 하나를 제안해줘."
        }
    ],
    temperature=0.3,
)

print(response.choices[0].message.content)