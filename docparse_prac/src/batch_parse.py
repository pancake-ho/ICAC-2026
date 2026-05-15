from pathlib import Path

from config import SAMPLES_DIR, SUPPORTED_EXTENSIONS
from parse_document import parse_document, save_parse_result


def find_sample_files() -> list[Path]:
    """
    samples 폴더 아래의 모든 PDF/이미지 파일을 재귀적으로 탐색한다.

    예:
    samples/campus_notice.pdf
    samples/ghost_text/task.pdf
    samples/ghost_text/student_a.pdf
    """
    files = []

    for file_path in SAMPLES_DIR.rglob("*"):
        if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_EXTENSIONS:
            files.append(file_path)

    return sorted(files)


def main() -> None:
    sample_files = find_sample_files()

    if not sample_files:
        print(f"samples 폴더에 테스트할 PDF/이미지 파일이 없습니다: {SAMPLES_DIR}")
        print("예: samples/campus_notice.pdf")
        print("예: samples/ghost_text/task.pdf")
        return

    print(f"총 {len(sample_files)}개 파일 파싱 시작")

    for idx, file_path in enumerate(sample_files, start=1):
        print("\n" + "=" * 80)
        print(f"[{idx}/{len(sample_files)}] {file_path}")
        print("=" * 80)

        try:
            result = parse_document(file_path=file_path, ocr="auto")
            save_parse_result(file_path, result)

        except Exception as e:
            print(f"[실패] {file_path}")
            print(e)

    print("\n전체 배치 파싱 완료")


if __name__ == "__main__":
    main()