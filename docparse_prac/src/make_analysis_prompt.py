"""
Parsing된 Markdown을 읽어 ICAC 답안 생성용 프롬프트 생성 기능을 수행
"""

import argparse
from pathlib import Path

from config import OUTPUTS_DIR
from utils import save_text, now_string


ICAC_ANALYSIS_TEMPLATE = """너는 ICAC 2026 예선 본선 진출을 목표로 하는 AI 문제해결 해커톤 코치다.

아래 내용은 Document Parse로 추출한 캠퍼스 관련 문서의 Markdown 결과다.

너의 작업:
1. 이 문서가 다루는 캠퍼스 문제를 한 문장으로 정의하라.
2. 이 문서의 핵심 정보를 5줄로 요약하라.
3. 대상 사용자를 구체적으로 분류하라.
   - 예: 학부생, 대학원생, 신입생, 유학생, 장애학생, 교수, 조교, 행정직원 등
4. 사용자가 반드시 알아야 할 정보를 구조화하라.
   - 일정
   - 장소
   - 신청 조건
   - 제출 서류
   - 비용
   - 문의처
   - 주의사항
5. 이 문서를 기반으로 ICAC 제출용 AI 솔루션 아이디어 3개를 제안하라.
6. 각 아이디어마다 다음 항목을 포함하라.
   - 문제 정의
   - 제안 솔루션
   - AI 활용 방식
   - 필요한 데이터
   - 구현 가능성
   - 기대 효과
   - 리스크 및 대응
   - 성과 지표
7. 가장 본선 진출 가능성이 높은 아이디어 1개를 선택하고, 이유를 점수표로 설명하라.
8. 선택한 아이디어를 제출용 답안 초안으로 작성하라.

주의:
- 단순 챗봇으로 끝내지 마라.
- Document Parse를 단순 OCR이 아니라 비정형 캠퍼스 문서 구조화 도구로 활용하라.
- 개인정보, hallucination, 관리자 검토, 출처 표시를 반드시 포함하라.
- MVP 구현 범위는 현실적으로 작성하라.
- 심사위원이 30초 안에 장점을 파악할 수 있게 작성하라.

[Document Parse 결과 Markdown]
{parsed_markdown}
"""


def load_markdown(markdown_path: Path) -> str:
    if not markdown_path.exists():
        raise FileNotFoundError(f"Markdown 파일이 없습니다: {markdown_path}")

    with open(markdown_path, "r", encoding="utf-8") as f:
        return f.read()


def make_prompt(markdown: str) -> str:
    return ICAC_ANALYSIS_TEMPLATE.format(parsed_markdown=markdown)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--markdown",
        type=str,
        required=True,
        help="Document Parse로 생성된 parsed.md 경로",
    )

    args = parser.parse_args()

    markdown_path = Path(args.markdown)
    markdown = load_markdown(markdown_path)

    prompt = make_prompt(markdown)

    output_dir = markdown_path.parent
    prompt_path = output_dir / "icac_analysis_prompt.txt"

    header = f"""[ICAC Analysis Prompt]
created_at: {now_string()}
source_markdown: {markdown_path}

"""
    save_text(header + prompt, prompt_path)

    print("\nICAC 분석 프롬프트 생성 완료")
    print(f"- 저장 위치: {prompt_path}")
    print("\n이 파일 내용을 그대로 ChatGPT에 붙여넣고 답안 초안을 만들면 됨.")


if __name__ == "__main__":
    main()