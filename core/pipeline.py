from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.config import AppConfig
from core.docparse import ParseArtifacts, parse_and_save
from core.prompt import (
    ICAC_SYSTEM_PROMPT,
    DOCUMENT_QA_SYSTEM_PROMPT,
    build_answer_review_prompt,
    build_document_summary_prompt,
    build_icac_answer_prompt,
    build_json_structure_prompt,
)
from core.solar import call_solar, call_solar_json
from core.upstage_client import UpstageClients
from core.utils import ensure_dir, load_text, now_compact, save_json, save_text


@dataclass(frozen=True)
class SolveArtifacts:
    output_dir: Path
    parsed_markdown_path: Path | None
    problem_text_path: Path
    draft_answer_path: Path
    review_path: Path
    final_answer_path: Path
    json_analysis_path: Path | None


def summarize_document(
    config: AppConfig,
    clients: UpstageClients,
    parsed_markdown_path: Path,
) -> str:
    parsed_text = load_text(parsed_markdown_path)

    prompt = build_document_summary_prompt(parsed_text)

    return call_solar(
        config=config,
        clients=clients,
        system_prompt=DOCUMENT_QA_SYSTEM_PROMPT,
        user_prompt=prompt,
        temperature=0.2,
    )


def solve_from_text(
    config: AppConfig,
    clients: UpstageClients,
    problem_text: str,
    parsed_reference: str | None = None,
    make_json: bool = True,
) -> SolveArtifacts:
    """
    문제 텍스트와 선택적 참고 문서를 받아 제출용 답안 초안, 검토본, 최종본을 생성한다.
    """
    run_id = now_compact()
    output_dir = config.outputs_dir / "solve" / run_id
    ensure_dir(output_dir)

    problem_text_path = output_dir / "problem.txt"
    draft_answer_path = output_dir / "01_draft_answer.md"
    review_path = output_dir / "02_review.md"
    final_answer_path = output_dir / "03_final_answer.md"
    json_analysis_path = output_dir / "00_problem_analysis.json"

    save_text(problem_text_path, problem_text)

    json_analysis = None
    if make_json:
        json_analysis = call_solar_json(
            config=config,
            clients=clients,
            system_prompt=ICAC_SYSTEM_PROMPT,
            user_prompt=build_json_structure_prompt(problem_text),
            temperature=0.1,
        )
        save_json(json_analysis_path, json_analysis)

    draft_prompt = build_icac_answer_prompt(
        problem_text=problem_text,
        parsed_reference=parsed_reference,
    )

    draft_answer = call_solar(
        config=config,
        clients=clients,
        system_prompt=ICAC_SYSTEM_PROMPT,
        user_prompt=draft_prompt,
        temperature=0.25,
    )
    save_text(draft_answer_path, draft_answer)

    review = call_solar(
        config=config,
        clients=clients,
        system_prompt=ICAC_SYSTEM_PROMPT,
        user_prompt=build_answer_review_prompt(draft_answer),
        temperature=0.2,
    )
    save_text(review_path, review)

    # review 안에 '수정된 최종 답안'이 포함되므로 그대로 최종 후보로 저장
    save_text(final_answer_path, review)

    return SolveArtifacts(
        output_dir=output_dir,
        parsed_markdown_path=None,
        problem_text_path=problem_text_path,
        draft_answer_path=draft_answer_path,
        review_path=review_path,
        final_answer_path=final_answer_path,
        json_analysis_path=json_analysis_path if make_json else None,
    )


def solve_from_document(
    config: AppConfig,
    clients: UpstageClients,
    file_path: Path,
    ocr: str = "auto",
    extra_problem_instruction: str | None = None,
) -> tuple[ParseArtifacts, SolveArtifacts]:
    """
    문제 파일을 Document Parse로 읽고, 그 결과를 바탕으로 ICAC 답안을 생성한다.
    """
    parse_artifacts = parse_and_save(
        config=config,
        file_path=file_path,
        ocr=ocr,
    )

    parsed_text = parse_artifacts.markdown

    problem_text = f"""
아래는 ICAC 예선 문제 또는 참고 문서를 Document Parse로 추출한 내용이다.
이 문서를 문제 원문으로 보고, 제출 가능한 답안을 작성해라.

[Document Parse 결과]
{parsed_text}
""".strip()

    if extra_problem_instruction:
        problem_text += f"\n\n[추가 지시]\n{extra_problem_instruction.strip()}"

    solve_artifacts = solve_from_text(
        config=config,
        clients=clients,
        problem_text=problem_text,
        parsed_reference=parsed_text,
        make_json=True,
    )

    return parse_artifacts, solve_artifacts