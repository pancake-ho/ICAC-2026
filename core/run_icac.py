from __future__ import annotations

import argparse
import sys
from pathlib import Path


# python3 core/run_icac.py 형태로 직접 실행해도
# from core.xxx import ... 이 안정적으로 동작하도록 루트 경로를 보정한다.
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


from core.config import load_config
from core.docparse import parse_and_save
from core.pipeline import (
    solve_from_document,
    solve_from_text,
    summarize_document,
)
from core.upstage_client import UpstageClients
from core.utils import load_text, save_text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="ICAC 2026 실전용 Upstage Document Parse + Solar Pro 3 파이프라인"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    parse_parser = subparsers.add_parser(
        "parse",
        help="문서/PDF/이미지를 Document Parse로 구조화",
    )
    parse_parser.add_argument("--file", required=True, help="입력 문서 경로")
    parse_parser.add_argument(
        "--ocr",
        default="auto",
        choices=["auto", "force"],
        help="OCR 옵션. 스캔본/이미지면 force 권장",
    )

    summary_parser = subparsers.add_parser(
        "summary",
        help="이미 파싱된 parsed.md를 Solar Pro 3로 요약/분석",
    )
    summary_parser.add_argument(
        "--parsed",
        required=True,
        help="Document Parse 결과 markdown 경로",
    )
    summary_parser.add_argument(
        "--out",
        default=None,
        help="요약 결과 저장 경로",
    )

    solve_text_parser = subparsers.add_parser(
        "solve-text",
        help="텍스트 문제를 Solar Pro 3로 ICAC 제출 답안화",
    )
    solve_text_parser.add_argument(
        "--problem",
        required=True,
        help="문제 텍스트 파일 경로",
    )
    solve_text_parser.add_argument(
        "--reference",
        default=None,
        help="선택: 참고 문서 markdown 경로",
    )
    solve_text_parser.add_argument(
        "--no-json",
        action="store_true",
        help="문제 분석 JSON 생성을 생략하고 바로 답안 생성",
    )

    solve_doc_parser = subparsers.add_parser(
        "solve-doc",
        help="문제 문서를 파싱한 뒤 바로 ICAC 제출 답안 생성",
    )
    solve_doc_parser.add_argument("--file", required=True, help="입력 문제 문서 경로")
    solve_doc_parser.add_argument(
        "--ocr",
        default="auto",
        choices=["auto", "force"],
        help="OCR 옵션",
    )
    solve_doc_parser.add_argument(
        "--instruction",
        default=None,
        help="추가 지시문. 예: 'Django 백엔드와 DB 구현 가능성을 강조해줘'",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    config = load_config()
    clients = UpstageClients(config)

    if args.command == "parse":
        artifacts = parse_and_save(
            config=config,
            file_path=Path(args.file),
            ocr=args.ocr,
        )

        print("\n[Document Parse 완료]")
        print(f"- 원본: {artifacts.source_file}")
        print(f"- 결과 폴더: {artifacts.output_dir}")
        print(f"- Markdown: {artifacts.markdown_path}")
        print(f"- HTML: {artifacts.html_path}")
        print(f"- Raw JSON: {artifacts.raw_json_path}")

    elif args.command == "summary":
        parsed_path = Path(args.parsed)
        summary = summarize_document(
            config=config,
            clients=clients,
            parsed_markdown_path=parsed_path,
        )

        print(summary)

        if args.out:
            out_path = Path(args.out)
            save_text(out_path, summary)
            print(f"\n[저장 완료] {out_path}")

    elif args.command == "solve-text":
        problem_text = load_text(Path(args.problem))

        reference_text = None
        if args.reference:
            reference_text = load_text(Path(args.reference))

        artifacts = solve_from_text(
            config=config,
            clients=clients,
            problem_text=problem_text,
            parsed_reference=reference_text,
            make_json=not args.no_json,
        )

        print("\n[ICAC 답안 생성 완료]")
        print(f"- 결과 폴더: {artifacts.output_dir}")
        print(f"- 문제 분석 JSON: {artifacts.json_analysis_path}")
        print(f"- 초안: {artifacts.draft_answer_path}")
        print(f"- 검토: {artifacts.review_path}")
        print(f"- 최종 제출 후보: {artifacts.final_answer_path}")
        print("\n[다음 행동]")
        print(f"1) {artifacts.final_answer_path} 열기")
        print("2) 문제 요구사항 누락 여부 확인")
        print("3) 개인정보/과장 표현/구현 가능성 직접 검토 후 제출")

    elif args.command == "solve-doc":
        parse_artifacts, solve_artifacts = solve_from_document(
            config=config,
            clients=clients,
            file_path=Path(args.file),
            ocr=args.ocr,
            extra_problem_instruction=args.instruction,
        )

        print("\n[문서 파싱 + ICAC 답안 생성 완료]")
        print(f"- 파싱 결과 폴더: {parse_artifacts.output_dir}")
        print(f"- Parsed Markdown: {parse_artifacts.markdown_path}")
        print(f"- 답안 결과 폴더: {solve_artifacts.output_dir}")
        print(f"- 문제 분석 JSON: {solve_artifacts.json_analysis_path}")
        print(f"- 초안: {solve_artifacts.draft_answer_path}")
        print(f"- 검토: {solve_artifacts.review_path}")
        print(f"- 최종 제출 후보: {solve_artifacts.final_answer_path}")
        print("\n[다음 행동]")
        print(f"1) {solve_artifacts.final_answer_path} 열기")
        print("2) 제목/첫 문단/성과 지표/리스크 대응 확인")
        print("3) 제출 형식에 맞춰 복붙 전 최종 다듬기")

    else:
        raise ValueError(f"지원하지 않는 command입니다: {args.command}")


if __name__ == "__main__":
    main()