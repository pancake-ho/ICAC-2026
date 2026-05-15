from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.config import AppConfig
from core.docparse import ParseArtifacts, parse_and_save
from core.prompt import (
    ICAC_SYSTEM_PROMPT,
    DOCUMENT_QA_SYSTEM_PROMPT,
    build_answer_review_prompt,
    build_document_summary_prompt,
    build_final_answer_prompt,
    build_icac_answer_prompt,
    build_json_structure_prompt,
)
from core.solar import call_solar, call_solar_json
from core.upstage_client import UpstageClients
from core.utils import compact_text, ensure_dir, load_text, now_compact, save_json, save_text


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
    parsed_text = compact_text(
        parsed_text,
        max_chars=config.max_reference_chars,
        label="parsed_document",
    )

    prompt = build_document_summary_prompt(parsed_text)

    return call_solar(
        config=config,
        clients=clients,
        system_prompt=DOCUMENT_QA_SYSTEM_PROMPT,
        user_prompt=prompt,
        temperature=0.2,
    )


def _fallback_problem_analysis(problem_text: str, error: Exception) -> dict[str, Any]:
    """
    JSON 분석 실패 시에도 답안 생성은 계속 진행하기 위한 fallback.
    실전에서는 JSON 구조화보다 최종 답안 생성이 더 중요하다.
    """
    return {
        "problem_summary": "Solar JSON 분석 실패. problem.txt와 draft/final 답안을 직접 확인해야 함.",
        "submission_format": "자동 분석 실패",
        "estimated_evaluation_criteria": [],
        "target_users": [],
        "pain_points": [],
        "solution_one_liner": "",
        "ai_features": [],
        "data_inputs": [],
        "mvp_scope": [],
        "implementation_blocks": [],
        "risks": ["JSON 파싱 실패"],
        "metrics": [],
        "recommended_answer_structure": [],
        "error": str(error),
        "problem_preview": problem_text[:1200],
    }


def solve_from_text(
    config: AppConfig,
    clients: UpstageClients,
    problem_text: str,
    parsed_reference: str | None = None,
    parsed_markdown_path: Path | None = None,
    make_json: bool = True,
) -> SolveArtifacts:
    """
    문제 텍스트와 선택적 참고 문서를 받아 제출용 답안 초안, 검토본, 최종본을 생성한다.

    실전 안정성:
    1. 문제 분석 JSON 실패해도 계속 진행
    2. draft -> review -> clean final 3단계 분리
    3. final_answer_path에는 제출 가능한 본문만 저장
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

    safe_problem_text = compact_text(
        problem_text,
        max_chars=config.max_problem_chars,
        label="problem_text",
    )

    safe_reference = None
    if parsed_reference:
        safe_reference = compact_text(
            parsed_reference,
            max_chars=config.max_reference_chars,
            label="parsed_reference",
        )

    if make_json:
        try:
            json_analysis = call_solar_json(
                config=config,
                clients=clients,
                system_prompt=ICAC_SYSTEM_PROMPT,
                user_prompt=build_json_structure_prompt(safe_problem_text),
                temperature=0.1,
            )
        except Exception as exc:
            json_analysis = _fallback_problem_analysis(safe_problem_text, exc)

        save_json(json_analysis_path, json_analysis)

    draft_prompt = build_icac_answer_prompt(
        problem_text=safe_problem_text,
        parsed_reference=safe_reference,
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

    try:
        final_answer = call_solar(
            config=config,
            clients=clients,
            system_prompt=ICAC_SYSTEM_PROMPT,
            user_prompt=build_final_answer_prompt(
                problem_text=safe_problem_text,
                draft_answer=draft_answer,
                review_text=review,
                parsed_reference=safe_reference,
            ),
            temperature=0.15,
        )
    except Exception as exc:
        final_answer = (
            "# 최종 답안 생성 실패 - 초안 기반 대체본\n\n"
            "아래 답안은 최종 재작성 단계에서 오류가 발생하여 1차 초안을 대체 저장한 것입니다.\n"
            "제출 전 반드시 사람이 직접 검토해야 합니다.\n\n"
            f"[오류]\n{exc}\n\n"
            "[1차 초안]\n"
            f"{draft_answer}"
        )

    save_text(final_answer_path, final_answer)

    return SolveArtifacts(
        output_dir=output_dir,
        parsed_markdown_path=parsed_markdown_path,
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
        parsed_markdown_path=parse_artifacts.markdown_path,
        make_json=True,
    )

    return parse_artifacts, solve_artifacts