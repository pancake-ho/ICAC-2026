from pathlib import Path
from datetime import datetime


BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = BASE_DIR / "outputs"

TARGET_DIR_ORDER = [
    "task",
    "student_a",
    "student_b",
    "student_c",
    "student_d",
    "student_e",
    "student_f",
    "student_g",
]


def read_text(path: Path) -> str:
    if not path.exists():
        return ""

    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def collect_parsed_markdowns() -> str:
    """
    outputs/task/parsed.md
    outputs/student_a/parsed.md
    ...
    outputs/student_g/parsed.md

    위 파일들을 하나의 분석 입력으로 합친다.
    """
    sections = []

    for dir_name in TARGET_DIR_ORDER:
        parsed_path = OUTPUTS_DIR / dir_name / "parsed.md"

        if not parsed_path.exists():
            print(f"[경고] 파일 없음: {parsed_path}")
            continue

        content = read_text(parsed_path).strip()

        section = f"""
============================================================
[{dir_name}]
source: {parsed_path}
============================================================

{content}
"""
        sections.append(section)

    return "\n\n".join(sections)


def build_icac_prompt(combined_markdown: str) -> str:
    return f"""너는 ICAC 2026 예선 문제를 푸는 AI 문제해결 코치다.

아래는 문제 설명 PDF와 학생별 제출 PDF를 Document Parse로 추출한 Markdown이다.

이번 문제의 목표:
- 교수님이 학생들의 과제를 채점하고 있다.
- 일부 학생은 생성형 AI 답변을 그대로 복사/붙여넣기 했을 가능성이 있다.
- 문제 지시사항과 숨겨진 함정을 기준으로 학생 제출물을 판단해야 한다.
- 부정행위로 적발되지 않아 채점 대상이 된 학생을 모두 골라야 한다.
- 부정행위의 이유도 설명해야 한다.

분석 절차:
1. 먼저 [task] 문서에서 과제 요구사항과 채점 조건을 정확히 추출하라.
2. 각 학생 student_a ~ student_g의 제출물을 하나씩 검사하라.
3. 다음 기준을 반드시 확인하라.
   - 마크다운 언어로 작성했는가?
   - 보고서를 꼭 3장 작성했는가?
   - 제목에 "vs"를 포함했는가?
   - 생성형 AI에 대해 긍정적인 주제로 작성했는가?
   - 문제에서 요구한 형식과 다른 부분이 있는가?
   - 생성형 AI 답변을 그대로 복사한 흔적이 있는가?
   - 숨겨진 함정에 걸린 학생이 있는가?
4. 각 학생별로 판정하라.
   - 채점 대상
   - 부정행위 의심/적발
   - 형식 위반
   - 근거
5. 최종적으로 문항 2의 답을 알파벳 소문자 하나로 제시하라.
6. 문항 3의 답을 학생 알파벳 목록으로 제시하라.
7. 문항 3에 대한 이유를 학생별로 구체적으로 작성하라.

주의:
- 단순히 글이 AI처럼 보인다는 이유만으로 판단하지 마라.
- 반드시 task 문서의 조건과 학생 제출물을 근거로 비교하라.
- 답은 제출용으로 바로 쓸 수 있게 간결하고 명확하게 작성하라.
- 확실하지 않은 부분은 "추정"이라고 표시하라.

[Document Parse 결과 모음]

{combined_markdown}
"""


def main() -> None:
    combined_markdown = collect_parsed_markdowns()

    if not combined_markdown.strip():
        print("[오류] 합칠 parsed.md 파일이 없습니다.")
        return

    prompt = build_icac_prompt(combined_markdown)

    output_path = OUTPUTS_DIR / "ghost_text_analysis_prompt.txt"

    header = f"""# ICAC Ghost Text Analysis Prompt

created_at: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
source_dir: {OUTPUTS_DIR}

"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(header + prompt)

    print("분석 프롬프트 생성 완료")
    print(f"- 저장 위치: {output_path}")
    print()
    print("다음 단계:")
    print(f"1. {output_path} 파일을 연다.")
    print("2. 전체 내용을 ChatGPT에 붙여넣는다.")
    print("3. 나온 답을 다시 task 조건과 parsed.md 원문으로 검증한다.")


if __name__ == "__main__":
    main()