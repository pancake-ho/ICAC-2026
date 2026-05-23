from __future__ import annotations

import argparse
import csv
import json
import math
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2


PRODUCTION_SPEC_TEXT = """
- 같은 남자 대학생 주인공이 4개 클립 전체에 등장해야 한다.
- 전체 톤은 dark Korean trap rap music video여야 한다.
- 밝은 캠퍼스 축제, 로맨스, lo-fi 공부 분위기는 피해야 한다.
- 실제 GitHub 로고, 실제 학교 로고, 실제 회사 로고는 나오면 안 된다.
- 화면 텍스트는 짧은 UI 라벨만 허용한다.
- 핵심 라벨: 03:17, MERGE CONFLICT, BUILD FAILED, DEADLINE
""".strip()


Q5_OPTIONS = [
    {
        "id": "A",
        "text": "영상의 핵심 정서는 '심야 마감일에 대한 불안감'으로 해석할 수 있다.",
    },
    {
        "id": "B",
        "text": "눈가의 빨간 다크서클 남성이 나오지 않은 이유는 Production Spec을 준수했기 때문이다.",
    },
    {
        "id": "C",
        "text": "실제 GitHub 로고나 실제 학교 로고가 명확히 등장한다면 production_spec 위반이다.",
    },
    {
        "id": "D",
        "text": "현재 영상은 '동일한 외모의 같은 남자 대학생 주인공'이 실제로 4개 클립 전체에 등장했다고 할 수 있다.",
    },
    {
        "id": "E",
        "text": '"BUILD FAILED", "SUBMIT"처럼 짧은 UI 라벨이 등장하는 것은 production_spec과 충돌한다.',
    },
    {
        "id": "F",
        "text": "핵심라벨인 BUILD FAILED가 실제 영상에서는 BUILD FASEED로 환각 발생한다.",
    },
]


@dataclass
class VideoBasicInfo:
    path: Path
    fps: float
    frame_count: int
    duration_sec: float
    width: int
    height: int


@dataclass
class FrameShot:
    index: int
    time_sec: float
    path: Path


def run_command(cmd: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(
        cmd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


def find_video(input_dir: Path, explicit_video: Path | None) -> Path:
    if explicit_video and explicit_video.exists():
        return explicit_video

    candidates = []
    for ext in ("*.mp4", "*.mov", "*.mkv", "*.webm"):
        candidates.extend(input_dir.rglob(ext))

    candidates = sorted(candidates)
    if candidates:
        # track_04_mv 우선
        for p in candidates:
            if "track_04" in p.name.lower() and "mv" in p.name.lower():
                return p
        return candidates[0]

    raise FileNotFoundError(
        "track_04_mv.mp4를 찾지 못했습니다. "
        "inputs/campus_sound_log/video/track_04_mv.mp4 위치에 넣거나 --video로 지정하세요."
    )


def get_video_info(video_path: Path) -> VideoBasicInfo:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"영상 파일을 열 수 없습니다: {video_path}")

    fps = float(cap.get(cv2.CAP_PROP_FPS))
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration_sec = frame_count / fps if fps > 0 else 0.0

    cap.release()

    return VideoBasicInfo(
        path=video_path,
        fps=fps,
        frame_count=frame_count,
        duration_sec=duration_sec,
        width=width,
        height=height,
    )


def extract_frames(
    video_path: Path,
    out_dir: Path,
    every_sec: float = 1.0,
    max_frames: int = 80,
) -> list[FrameShot]:
    out_dir.mkdir(parents=True, exist_ok=True)

    info = get_video_info(video_path)
    cap = cv2.VideoCapture(str(video_path))

    shots: list[FrameShot] = []
    if info.duration_sec <= 0:
        return shots

    num = min(max_frames, max(1, int(math.ceil(info.duration_sec / every_sec)) + 1))
    times = [min(info.duration_sec, i * every_sec) for i in range(num)]

    for t in times:
        frame_index = int(t * info.fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ok, frame = cap.read()
        if not ok:
            continue

        frame_path = out_dir / f"frame_{len(shots):03d}_{t:06.2f}s.jpg"
        cv2.imwrite(str(frame_path), frame)
        shots.append(
            FrameShot(
                index=frame_index,
                time_sec=t,
                path=frame_path,
            )
        )

    cap.release()
    return shots


def image_brightness_score(image_path: Path) -> float:
    img = cv2.imread(str(image_path))
    if img is None:
        return 0.0
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return float(gray.mean())


def frame_darkness_summary(shots: list[FrameShot]) -> dict[str, Any]:
    if not shots:
        return {
            "avg_brightness": None,
            "dark_frame_ratio": None,
            "comment": "프레임 없음",
        }

    values = [image_brightness_score(s.path) for s in shots]
    avg = sum(values) / len(values)
    dark_ratio = sum(1 for v in values if v < 95) / len(values)

    return {
        "avg_brightness": round(avg, 2),
        "dark_frame_ratio": round(dark_ratio, 3),
        "comment": "dark tone 가능" if dark_ratio >= 0.45 or avg < 115 else "밝은 톤 가능성 있음",
    }


def try_ocr_with_tesseract(image_path: Path) -> str:
    """
    tesseract가 설치되어 있으면 OCR 수행.
    설치 안 되어 있으면 빈 문자열 반환.
    Ubuntu 설치:
      sudo apt update
      sudo apt install -y tesseract-ocr
    """
    code, out, err = run_command(
        [
            "tesseract",
            str(image_path),
            "stdout",
            "--psm",
            "6",
        ]
    )
    if code != 0:
        return ""
    return out.strip()


def run_ocr_on_frames(shots: list[FrameShot], max_ocr_frames: int = 40) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    # 모든 프레임 OCR하면 느리니 균등 샘플링
    if len(shots) <= max_ocr_frames:
        target = shots
    else:
        step = max(1, len(shots) // max_ocr_frames)
        target = shots[::step][:max_ocr_frames]

    for s in target:
        text = try_ocr_with_tesseract(s.path)
        results.append(
            {
                "time_sec": round(s.time_sec, 2),
                "frame_path": str(s.path),
                "ocr_text": text,
            }
        )

    return results


def normalize_ocr_text(text: str) -> str:
    return re.sub(r"[^A-Z0-9: ]+", " ", text.upper())


def analyze_ocr_texts(ocr_rows: list[dict[str, Any]]) -> dict[str, Any]:
    joined = "\n".join(row.get("ocr_text", "") for row in ocr_rows)
    norm = normalize_ocr_text(joined)

    found = {
        "03:17": "03:17" in norm or "03 17" in norm,
        "MERGE CONFLICT": "MERGE CONFLICT" in norm,
        "BUILD FAILED": "BUILD FAILED" in norm,
        "BUILD FASEED": "BUILD FASEED" in norm or "BU1LD FASEED" in norm,
        "DEADLINE": "DEADLINE" in norm,
        "SUBMIT": "SUBMIT" in norm,
        "GITHUB": "GITHUB" in norm,
    }

    suspicious_logo_text = []
    for key in ["GITHUB", "KHU", "KYUNG HEE", "GOOGLE", "APPLE", "MICROSOFT"]:
        if key in norm:
            suspicious_logo_text.append(key)

    return {
        "joined_ocr_text": joined,
        "normalized_ocr_text": norm,
        "found_labels": found,
        "suspicious_logo_text": suspicious_logo_text,
    }


def write_inspection_guide(out_dir: Path, shots: list[FrameShot]) -> None:
    """
    사람 검수용 HTML.
    프레임을 빠르게 훑어서:
    - 동일 주인공 유지 여부
    - 실제 로고 등장 여부
    - BUILD FASEED 오타 여부
    를 눈으로 확인하게 한다.
    """
    html_lines = []
    html_lines.append("<html><head><meta charset='utf-8'><title>Q5 Video Frames</title></head><body>")
    html_lines.append("<h1>ICAC 4-5 track_04_mv 프레임 검수</h1>")
    html_lines.append("<p>확인 항목: 동일 주인공 4클립 유지 / 실제 로고 / UI 텍스트 오타 / dark trap rap tone</p>")

    for s in shots:
        rel = s.path.name
        html_lines.append("<div style='margin-bottom:24px;'>")
        html_lines.append(f"<h3>{s.time_sec:.2f}s</h3>")
        html_lines.append(f"<img src='frames/{rel}' style='width:720px; max-width:100%; border:1px solid #ccc;'>")
        html_lines.append("</div>")

    html_lines.append("</body></html>")
    (out_dir / "manual_frame_review.html").write_text("\n".join(html_lines), encoding="utf-8")


def judge_options(
    darkness: dict[str, Any],
    ocr_analysis: dict[str, Any],
    manual_same_character: str,
    manual_real_logo: str,
) -> list[dict[str, Any]]:
    """
    자동 판정 + 수동 체크값 결합.

    manual_same_character:
      yes / no / unknown

    manual_real_logo:
      yes / no / unknown
    """
    found = ocr_analysis["found_labels"]

    rows: list[dict[str, Any]] = []

    # A
    a_yes = darkness.get("dark_frame_ratio") is not None and (
        darkness["dark_frame_ratio"] >= 0.35 or darkness["avg_brightness"] < 125
    )
    rows.append(
        {
            "id": "A",
            "option": Q5_OPTIONS[0]["text"],
            "submit_check": "YES" if a_yes else "REVIEW",
            "reason": f"darkness={darkness}",
        }
    )

    # B
    rows.append(
        {
            "id": "B",
            "option": Q5_OPTIONS[1]["text"],
            "submit_check": "NO",
            "reason": "production_spec은 '같은 남자 대학생 주인공'을 요구할 뿐, 빨간 다크서클 남성을 금지/요구하지 않는다. 해당 설명은 spec 준수 근거로 부적절하다.",
        }
    )

    # C
    c_yes = True
    rows.append(
        {
            "id": "C",
            "option": Q5_OPTIONS[2]["text"],
            "submit_check": "YES",
            "reason": "production_spec에 실제 GitHub/학교/회사 로고 금지가 명시되어 있으므로, 명확히 등장한다면 위반이다.",
        }
    )

    # D
    if manual_same_character == "yes":
        d = "YES"
        d_reason = "수동 검수 결과 4개 클립 전체에서 같은 외모의 남자 대학생으로 판단됨."
    elif manual_same_character == "no":
        d = "NO"
        d_reason = "수동 검수 결과 4개 클립 전체의 동일 인물 일관성이 부족함."
    else:
        d = "REVIEW"
        d_reason = "동일 인물 여부는 OCR/밝기만으로 확정 불가. manual_frame_review.html에서 직접 확인 필요."
    rows.append(
        {
            "id": "D",
            "option": Q5_OPTIONS[3]["text"],
            "submit_check": d,
            "reason": d_reason,
        }
    )

    # E
    rows.append(
        {
            "id": "E",
            "option": Q5_OPTIONS[4]["text"],
            "submit_check": "NO",
            "reason": "spec은 짧은 UI 라벨을 허용한다. BUILD FAILED는 핵심 라벨이고, SUBMIT도 짧은 UI 라벨이므로 등장 자체는 충돌이 아니다.",
        }
    )

    # F
    f_yes = bool(found.get("BUILD FASEED"))
    rows.append(
        {
            "id": "F",
            "option": Q5_OPTIONS[5]["text"],
            "submit_check": "YES" if f_yes else "REVIEW",
            "reason": (
                "OCR에서 BUILD FASEED 또는 유사 오타가 탐지됨."
                if f_yes
                else "자동 OCR만으로 BUILD FASEED 오타를 확정하지 못함. 프레임을 직접 확인해야 함."
            ),
        }
    )

    return rows


def save_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return

    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ICAC 2026 4-5 production_spec vs track_04_mv 검수"
    )
    parser.add_argument(
        "--input-dir",
        default="inputs/campus_sound_log",
        help="campus_sound_log 폴더",
    )
    parser.add_argument(
        "--video",
        default=None,
        help="track_04_mv.mp4 직접 경로",
    )
    parser.add_argument(
        "--out",
        default="outputs/campus_sound_log_q5",
        help="결과 저장 폴더",
    )
    parser.add_argument(
        "--every-sec",
        type=float,
        default=1.0,
        help="프레임 추출 간격",
    )
    parser.add_argument(
        "--manual-same-character",
        choices=["yes", "no", "unknown"],
        default="unknown",
        help="4개 클립 전체 동일 남자 주인공 여부. 직접 보고 yes/no 입력 가능.",
    )
    parser.add_argument(
        "--manual-real-logo",
        choices=["yes", "no", "unknown"],
        default="unknown",
        help="실제 GitHub/학교/회사 로고 명확 등장 여부. 직접 보고 yes/no 입력 가능.",
    )

    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    explicit_video = Path(args.video) if args.video else None
    out_dir = Path(args.out)
    frames_dir = out_dir / "frames"
    out_dir.mkdir(parents=True, exist_ok=True)

    video_path = find_video(input_dir=input_dir, explicit_video=explicit_video)
    info = get_video_info(video_path)

    shots = extract_frames(
        video_path=video_path,
        out_dir=frames_dir,
        every_sec=args.every_sec,
        max_frames=100,
    )

    darkness = frame_darkness_summary(shots)
    ocr_rows = run_ocr_on_frames(shots, max_ocr_frames=50)
    ocr_analysis = analyze_ocr_texts(ocr_rows)

    write_inspection_guide(out_dir=out_dir, shots=shots)

    option_rows = judge_options(
        darkness=darkness,
        ocr_analysis=ocr_analysis,
        manual_same_character=args.manual_same_character,
        manual_real_logo=args.manual_real_logo,
    )

    save_json(
        out_dir / "video_info.json",
        {
            "video": str(video_path),
            "fps": info.fps,
            "frame_count": info.frame_count,
            "duration_sec": info.duration_sec,
            "width": info.width,
            "height": info.height,
            "production_spec": PRODUCTION_SPEC_TEXT,
        },
    )
    save_json(out_dir / "ocr_analysis.json", ocr_analysis)
    save_csv(out_dir / "ocr_rows.csv", ocr_rows)
    save_csv(out_dir / "q5_option_judgement.csv", option_rows)

    print("\n[ICAC 4-5 영상 검수 완료]")
    print(f"- 영상 파일: {video_path}")
    print(f"- 결과 폴더: {out_dir}")
    print(f"- 프레임 검수 HTML: {out_dir / 'manual_frame_review.html'}")
    print(f"- OCR 분석: {out_dir / 'ocr_analysis.json'}")
    print(f"- 선택지 판단 CSV: {out_dir / 'q5_option_judgement.csv'}")

    print("\n[영상 기본 정보]")
    print(f"- duration={info.duration_sec:.2f}s, fps={info.fps:.2f}, size={info.width}x{info.height}")
    print(f"- brightness={darkness}")

    print("\n[OCR 탐지 라벨]")
    for k, v in ocr_analysis["found_labels"].items():
        print(f"- {k}: {v}")

    print("\n[4-5 선택지 판단]")
    for row in option_rows:
        print(f"- {row['id']}: {row['submit_check']} | {row['option']}")
        print(f"  reason: {row['reason']}")

    print("\n[주의]")
    print("- OCR은 AI 영상의 왜곡된 텍스트를 놓칠 수 있다.")
    print("- manual_frame_review.html을 열어 BUILD FASEED, 실제 로고, 동일 인물 여부를 직접 최종 확인해라.")
    print("- 최종 제출은 YES만 체크하고 REVIEW는 직접 확인 후 결정해라.")


if __name__ == "__main__":
    main()