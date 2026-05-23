
from pathlib import Path

from core.config import load_config
from core.upstage_client import UpstageClients
from core.solar import call_solar

reference_path = Path("outputs/festival_receipts_merged/all_receipts_and_rules.md")
reference = reference_path.read_text(encoding="utf-8")

system_prompt = """
너는 회계 정산 계산기다.
아이디어 제안, 서비스 설계, 구현 방안, 기대효과, 리스크 설명을 절대 하지 마라.
오직 제공된 정산 기준과 영수증 OCR 결과를 근거로 객관식 정답을 계산하라.
계산 과정은 간단히 쓰되, 최종 답은 반드시 2-1, 2-2, 2-3, 2-4 형식으로 출력하라.
""".strip()

user_prompt = f"""
아래 [정산 기준 + 전체 영수증 OCR 결과]만 사용해서 문제를 풀어라.

[정산 기준 + 전체 영수증 OCR 결과]
{reference}

[문제]
2번. 축제 주점 장부 만들기

해야 할 일:
1. 모든 영수증 품목을 거래 시각 순서로 정렬한다.
2. 학생회 정산 기준에 따라 정산 대상/비대상과 예산 항목을 분류한다.
3. 최종 정산 지출액을 계산한다.
4. 기타 항목으로 분류되는 정산 대상 품목 행 수를 센다.
5. 각 예산 항목에서 처음으로 예산을 초과하게 만든 품목을 찾는다.
6. 추가 지원 기준에 따라 초과 항목별 최대 1개 품목을 고르되, 신청 품목 금액 합계는 50,000원을 넘지 않게 하여 준혁이가 부담할 최소 사비 금액을 계산한다.

[선택지]

2-1 최종 정산 지출액
1) 889,700원
2) 901,900원
3) 914,100원
4) 923,800원

2-2 기타 항목 품목 행 수
1) 24
2) 21
3) 27
4) 30

2-3 예산 초과 품목 조합
1) 식자재 receipt_01 사이다 1.5L 1,800원 / 운영물품 receipt_21 일회용 접시 50인 4,500원 / 홍보인쇄 receipt_07 현수막 300x90 출력 36,000원 / 장비대여 receipt_18 냉장 쇼케이스 대여 42,000원 / 기타 receipt_18 배송비 3,000원
2) 식자재 receipt_05 떡볶이떡 5kg 14,000원 / 운영물품 receipt_25 물티슈 10팩 9,900원 / 홍보인쇄 receipt_04 홍보 전단 12,000원 / 장비대여 receipt_20 이동식 스피커 대여 30,000원 / 기타 receipt_07 배송비 2,500원
3) 식자재 receipt_18 생수 2L 6입 9,000원 / 운영물품 receipt_21 종이컵 50입 1,800원 / 홍보인쇄 receipt_07 A2 포스터 인쇄 3,000원 / 장비대여 receipt_14 천막 3x3 대여 28,000원 / 기타 receipt_18 결제 수수료 800원
4) 식자재 receipt_01 캔맥주 500ml 6입 13,200원 / 운영물품 receipt_17 쓰레기봉투 50L 20매 5,900원 / 홍보인쇄 receipt_23 QR 안내판 출력 4,000원 / 장비대여 receipt_11 멀티탭 대여 3,000원 / 기타 receipt_24 배송비 3,000원

2-4 최소 사비 금액
1) 149,700원
2) 161,900원
3) 174,100원
4) 199,700원

[출력 형식]
근거 요약:
- 최종 정산 지출액:
- 기타 항목 행 수:
- 최초 예산 초과 품목 조합:
- 추가 지원 후 최소 사비:

최종 정답:
2-1: 번호, 금액
2-2: 번호, 개수
2-3: 번호
2-4: 번호, 금액
""".strip()

config = load_config()
clients = UpstageClients(config)

answer = call_solar(
    config=config,
    clients=clients,
    system_prompt=system_prompt,
    user_prompt=user_prompt,
    temperature=0.0,
    max_tokens=4096,
)

out_path = Path("outputs/festival_receipts_merged/answer_calc.md")
out_path.write_text(answer, encoding="utf-8")

print(answer)
print()
print(f"[SAVED] {out_path}")