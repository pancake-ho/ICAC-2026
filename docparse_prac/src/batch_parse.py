"""
samples/ 내의 PDF 및 이미지를 전부 parsing하는 기능 수행
"""

from pathlib import Path

from config import SAMPLES_DIR, SUPPORTED_EXTENSIONS
from parse_document import parse_document, save_parse_result


def find_sample_files() -> list[Path]:
    files = []

    for file_path in SAMPLES_DIR.iterdir():
        if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_EXTENSIONS:
            files.append(file_path)

    return sorted(files)


def main() -> None:
    sample_files = find_sample_files()

    if not sample_files:
        print(f"samples 폴더에 테스트할 파일이 없습니다: {SAMPLES_DIR}")
        print("예: campus_notice.pdf, table_test.pdf, poster.png")
        return

    print(f"총 {len(sample_files)}개 파일 파싱 시작")

    for idx, file_path in enumerate(sample_files, start=1):
        print("\n" + "=" * 80)
        print(f"[{idx}/{len(sample_files)}] {file_path.name}")
        print("=" * 80)

        try:
            # 이미지나 스캔 문서가 섞여 있을 수 있으므로 연습에서는 auto로 시작
            result = parse_document(file_path=file_path, ocr="auto")
            save_parse_result(file_path, result)

        except Exception as e:
            print(f"[실패] {file_path.name}")
            print(e)

    print("\n전체 배치 파싱 완료")


if __name__ == "__main__":
    main()