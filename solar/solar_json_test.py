# solar_prac/solar_json_test.py

import os
import json
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

prompt = """
다음 주제에 대해 ICAC 예선 제출용 아이디어를 JSON으로 정리해줘.

주제:
AI로 캠퍼스 공지 접근성을 개선하는 서비스

반드시 아래 key를 포함해:
- title
- problem
- users
- solution
- ai_usage
- system_flow
- implementation
- expected_effects
- risks
- metrics

JSON만 출력해.
"""

response = client.chat.completions.create(
    model="solar-pro3",
    messages=[
        {
            "role": "system",
            "content": "너는 JSON 형식으로만 답하는 AI 해커톤 기획 보조자다."
        },
        {
            "role": "user",
            "content": prompt
        }
    ],
    temperature=0.2,
)

content = response.choices[0].message.content
print(content)

try:
    data = json.loads(content)
    print("\n[JSON 파싱 성공]")
    print(json.dumps(data, ensure_ascii=False, indent=2))
except json.JSONDecodeError:
    print("\n[주의] 모델 출력이 완전한 JSON이 아닐 수 있습니다.")