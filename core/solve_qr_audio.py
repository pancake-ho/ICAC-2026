from __future__ import annotations

import argparse
import math
import wave
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


@dataclass
class AudioQrResult:
    module_size: int
    black_duration_sec: float
    white_duration_sec: float
    total_modules: int
    black_modules: int
    white_modules: int
    raw_qr_path: Path
    repaired_qr_path: Path
    decoded_raw: str
    decoded_repaired: str


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def load_wav_mono(wav_path: Path) -> tuple[int, np.ndarray]:
    if not wav_path.exists():
        raise FileNotFoundError(f"WAV 파일이 없습니다: {wav_path}")

    with wave.open(str(wav_path), "rb") as wav:
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        sample_rate = wav.getframerate()
        n_frames = wav.getnframes()
        raw = wav.readframes(n_frames)

    if sample_width != 2:
        raise ValueError(f"현재 코드는 16-bit PCM WAV만 지원합니다. sample_width={sample_width}")

    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32)

    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)

    max_abs = float(np.max(np.abs(audio)))
    if max_abs <= 0:
        raise ValueError("오디오 신호가 비어 있거나 무음입니다.")

    audio = audio / max_abs
    return sample_rate, audio


def detect_module_size_from_poster(poster_path: Path) -> int | None:
    """
    포스터 안의 QR을 OpenCV로 감지해서 straight QR의 크기를 가져온다.
    이 문제에서는 29 x 29가 나와야 한다.
    """
    if not poster_path.exists():
        return None

    image = cv2.imread(str(poster_path))
    if image is None:
        return None

    detector = cv2.QRCodeDetector()
    _, _, straight = detector.detectAndDecode(image)

    if straight is None:
        return None

    if straight.ndim != 2:
        return None

    h, w = straight.shape
    if h != w:
        return None

    return int(h)


def estimate_dominant_freq_labels(
    sample_rate: int,
    audio: np.ndarray,
    frame_sec: float = 0.02,
    hop_sec: float = 0.005,
) -> tuple[np.ndarray, np.ndarray, float, float, float]:
    """
    짧은 프레임마다 dominant frequency를 구해
    낮은 음/높은 음을 0/1로 분류한다.

    반환:
    - frame_centers: 각 프레임 중심 시간
    - labels: 낮은 음 0, 높은 음 1
    - low_freq: 낮은 음 대표 주파수
    - high_freq: 높은 음 대표 주파수
    - threshold_freq: 분류 기준 주파수
    """
    frame_len = int(sample_rate * frame_sec)
    hop_len = int(sample_rate * hop_sec)

    if frame_len <= 0 or hop_len <= 0:
        raise ValueError("frame_len/hop_len이 잘못되었습니다.")

    window = np.hanning(frame_len)
    freq_bins = np.fft.rfftfreq(frame_len, d=1.0 / sample_rate)

    valid_freq_mask = (freq_bins >= 100.0) & (freq_bins <= 2000.0)

    dominant_freqs: list[float] = []
    centers: list[float] = []

    for start in range(0, len(audio) - frame_len + 1, hop_len):
        frame = audio[start : start + frame_len]
        rms = float(np.sqrt(np.mean(frame * frame)))

        if rms < 1e-4:
            dominant_freqs.append(0.0)
            centers.append((start + frame_len / 2) / sample_rate)
            continue

        spectrum = np.fft.rfft(frame * window)
        magnitude = np.abs(spectrum)

        local_idx = int(np.argmax(magnitude[valid_freq_mask]))
        freq = float(freq_bins[valid_freq_mask][local_idx])

        dominant_freqs.append(freq)
        centers.append((start + frame_len / 2) / sample_rate)

    freqs = np.array(dominant_freqs, dtype=np.float64)
    centers_arr = np.array(centers, dtype=np.float64)

    nonzero = freqs[freqs > 0]
    if len(nonzero) == 0:
        raise ValueError("dominant frequency를 찾지 못했습니다.")

    # 이 문제에서는 대략 250Hz / 500Hz 두 음으로 나뉜다.
    # percentile 기반으로 두 대표 주파수를 안정적으로 추정한다.
    low_freq = float(np.percentile(nonzero, 25))
    high_freq = float(np.percentile(nonzero, 75))
    threshold_freq = (low_freq + high_freq) / 2.0

    labels = (freqs >= threshold_freq).astype(np.int32)

    return centers_arr, labels, low_freq, high_freq, threshold_freq


def labels_to_segments(
    labels: np.ndarray,
    frame_centers: np.ndarray,
    total_duration: float,
) -> list[tuple[int, float, float, float]]:
    """
    프레임 단위 label을 연속 구간으로 압축한다.

    반환 tuple:
    (label, start_time, end_time, duration)
    """
    if len(labels) == 0:
        raise ValueError("labels가 비어 있습니다.")

    segments: list[tuple[int, float, float, float]] = []

    current_label = int(labels[0])
    start_time = 0.0
    prev_center = float(frame_centers[0])

    for label, center in zip(labels[1:], frame_centers[1:]):
        label = int(label)
        center = float(center)

        if label != current_label:
            boundary = (prev_center + center) / 2.0
            segments.append(
                (
                    current_label,
                    start_time,
                    boundary,
                    boundary - start_time,
                )
            )
            start_time = boundary
            current_label = label

        prev_center = center

    segments.append(
        (
            current_label,
            start_time,
            total_duration,
            total_duration - start_time,
        )
    )

    return segments


def segments_to_bits(
    segments: list[tuple[int, float, float, float]],
    black_duration_sec: float,
    white_duration_sec: float,
) -> list[int]:
    """
    높은 음 label=1 -> 검은색 블록
    낮은 음 label=0 -> 흰색/회색 블록

    각 segment duration을 블록 1개의 길이로 나누어 run-length decoding 한다.
    """
    bits: list[int] = []

    for label, _, _, duration in segments:
        unit = black_duration_sec if label == 1 else white_duration_sec
        count = int(round(duration / unit))

        if count <= 0:
            raise ValueError(
                f"잘못된 segment count: label={label}, duration={duration}, unit={unit}"
            )

        bits.extend([label] * count)

    return bits


def bits_to_qr_matrix(bits: list[int], module_size: int) -> np.ndarray:
    expected = module_size * module_size

    if len(bits) != expected:
        raise ValueError(
            f"복원된 블록 수가 QR 크기와 맞지 않습니다. "
            f"bits={len(bits)}, expected={expected} "
            f"({module_size}x{module_size})"
        )

    return np.array(bits, dtype=np.uint8).reshape(module_size, module_size)


def repair_qr_function_patterns(matrix: np.ndarray) -> np.ndarray:
    """
    오디오 경계 검출/런 길이 반올림 과정에서 QR의 finder/timing pattern이
    1~2칸 틀어지면 디코딩이 실패할 수 있다.

    QR 표준상 고정되는 영역:
    - 좌상단/우상단/좌하단 finder pattern
    - separator
    - timing pattern

    이 영역은 문제의 숨겨진 데이터가 아니라 QR 구조 자체이므로 보정한다.
    """
    repaired = matrix.copy()
    n = repaired.shape[0]

    if n < 21:
        return repaired

    finder = np.zeros((7, 7), dtype=np.uint8)
    finder[0, :] = 1
    finder[6, :] = 1
    finder[:, 0] = 1
    finder[:, 6] = 1
    finder[2:5, 2:5] = 1

    finder_positions = [
        (0, 0),
        (0, n - 7),
        (n - 7, 0),
    ]

    for r, c in finder_positions:
        repaired[r : r + 7, c : c + 7] = finder

        # separator 보정
        if r + 7 < n:
            c_end = min(c + 8, n)
            repaired[r + 7, c:c_end] = 0

        if c + 7 < n:
            r_end = min(r + 8, n)
            repaired[r:r_end, c + 7] = 0

    # timing pattern: row 6, col 6
    for k in range(8, n - 8):
        value = 1 if k % 2 == 0 else 0
        repaired[6, k] = value
        repaired[k, 6] = value

    return repaired


def save_qr_image(matrix: np.ndarray, out_path: Path, scale: int = 20, quiet_zone: int = 4) -> None:
    """
    matrix 값:
    - 1: black
    - 0: white
    """
    ensure_dir(out_path.parent)

    module_img = (1 - matrix).astype(np.uint8) * 255
    scaled = np.kron(module_img, np.ones((scale, scale), dtype=np.uint8))

    border = quiet_zone * scale
    scaled = cv2.copyMakeBorder(
        scaled,
        border,
        border,
        border,
        border,
        cv2.BORDER_CONSTANT,
        value=255,
    )

    ok = cv2.imwrite(str(out_path), scaled)
    if not ok:
        raise RuntimeError(f"이미지 저장 실패: {out_path}")


def decode_qr_image(image_path: Path) -> str:
    image = cv2.imread(str(image_path))
    if image is None:
        return ""

    detector = cv2.QRCodeDetector()
    data, _, _ = detector.detectAndDecode(image)
    return data or ""


def solve_qr_audio(
    wav_path: Path,
    poster_path: Path,
    output_dir: Path,
    module_size: int | None = None,
    black_duration_sec: float = 0.5,
    white_duration_sec: float = 0.3,
) -> AudioQrResult:
    ensure_dir(output_dir)

    detected_module_size = detect_module_size_from_poster(poster_path)

    if module_size is None:
        if detected_module_size is None:
            raise ValueError(
                "QR module size를 자동 감지하지 못했습니다. "
                "--module-size 29 처럼 직접 지정하세요."
            )
        module_size = detected_module_size

    sample_rate, audio = load_wav_mono(wav_path)
    total_duration = len(audio) / sample_rate

    frame_centers, labels, low_freq, high_freq, threshold_freq = estimate_dominant_freq_labels(
        sample_rate=sample_rate,
        audio=audio,
    )

    segments = labels_to_segments(
        labels=labels,
        frame_centers=frame_centers,
        total_duration=total_duration,
    )

    bits = segments_to_bits(
        segments=segments,
        black_duration_sec=black_duration_sec,
        white_duration_sec=white_duration_sec,
    )

    matrix = bits_to_qr_matrix(bits, module_size)
    repaired = repair_qr_function_patterns(matrix)

    raw_qr_path = output_dir / "qr_raw.png"
    repaired_qr_path = output_dir / "qr_repaired.png"

    save_qr_image(matrix, raw_qr_path)
    save_qr_image(repaired, repaired_qr_path)

    decoded_raw = decode_qr_image(raw_qr_path)
    decoded_repaired = decode_qr_image(repaired_qr_path)

    meta_path = output_dir / "meta.txt"
    meta_path.write_text(
        "\n".join(
            [
                "[QR Audio Solve Result]",
                f"wav_path={wav_path}",
                f"poster_path={poster_path}",
                f"sample_rate={sample_rate}",
                f"audio_duration_sec={total_duration:.6f}",
                f"detected_module_size_from_poster={detected_module_size}",
                f"module_size={module_size}",
                f"low_freq={low_freq:.3f}",
                f"high_freq={high_freq:.3f}",
                f"threshold_freq={threshold_freq:.3f}",
                f"black_duration_sec={black_duration_sec}",
                f"white_duration_sec={white_duration_sec}",
                f"total_modules={len(bits)}",
                f"black_modules={int(np.sum(matrix))}",
                f"white_modules={int(matrix.size - np.sum(matrix))}",
                f"raw_qr_path={raw_qr_path}",
                f"repaired_qr_path={repaired_qr_path}",
                f"decoded_raw={decoded_raw}",
                f"decoded_repaired={decoded_repaired}",
            ]
        ),
        encoding="utf-8",
    )

    return AudioQrResult(
        module_size=module_size,
        black_duration_sec=black_duration_sec,
        white_duration_sec=white_duration_sec,
        total_modules=len(bits),
        black_modules=int(np.sum(matrix)),
        white_modules=int(matrix.size - np.sum(matrix)),
        raw_qr_path=raw_qr_path,
        repaired_qr_path=repaired_qr_path,
        decoded_raw=decoded_raw,
        decoded_repaired=decoded_repaired,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ICAC 5번: output.wav를 분석해 숨겨진 QR 코드를 복원합니다."
    )

    parser.add_argument(
        "--input-dir",
        default="inputs/qr_code",
        help="output.wav와 poster.jpg가 들어 있는 폴더",
    )
    parser.add_argument(
        "--wav",
        default=None,
        help="직접 WAV 경로 지정. 생략하면 input-dir/output.wav 사용",
    )
    parser.add_argument(
        "--poster",
        default=None,
        help="직접 poster.jpg 경로 지정. 생략하면 input-dir/poster.jpg 사용",
    )
    parser.add_argument(
        "--out",
        default="outputs/qr_code",
        help="결과 저장 폴더",
    )
    parser.add_argument(
        "--module-size",
        type=int,
        default=None,
        help="QR 한 변의 블록 수. 생략하면 poster.jpg에서 자동 감지",
    )
    parser.add_argument(
        "--black-sec",
        type=float,
        default=0.5,
        help="검은색 블록 하나에 해당하는 높은 음 길이",
    )
    parser.add_argument(
        "--white-sec",
        type=float,
        default=0.3,
        help="흰색/회색 블록 하나에 해당하는 낮은 음 길이",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    input_dir = Path(args.input_dir)
    wav_path = Path(args.wav) if args.wav else input_dir / "output.wav"
    poster_path = Path(args.poster) if args.poster else input_dir / "poster.jpg"
    output_dir = Path(args.out)

    result = solve_qr_audio(
        wav_path=wav_path,
        poster_path=poster_path,
        output_dir=output_dir,
        module_size=args.module_size,
        black_duration_sec=args.black_sec,
        white_duration_sec=args.white_sec,
    )

    print("\n[ICAC 5번 QR Audio 풀이 완료]")
    print(f"- 5-1 QR 한 변 블록 수: {result.module_size}")
    print(
        f"- 5-2 검은색/흰색 블록 소리 길이: "
        f"{result.black_duration_sec}, {result.white_duration_sec}"
    )
    print(f"- 전체 블록 수: {result.total_modules}")
    print(f"- 검은색 블록 수: {result.black_modules}")
    print(f"- 흰색/회색 블록 수: {result.white_modules}")
    print(f"- Raw QR 이미지: {result.raw_qr_path}")
    print(f"- Repaired QR 이미지: {result.repaired_qr_path}")

    if result.decoded_raw:
        print(f"- Raw QR 디코딩 결과: {result.decoded_raw}")
    else:
        print("- Raw QR 디코딩 결과: 실패")

    if result.decoded_repaired:
        print(f"- Repaired QR 디코딩 결과: {result.decoded_repaired}")
    else:
        print("- Repaired QR 디코딩 결과: 실패")

    print("\n[제출용]")
    print(f"5-1: {result.module_size}")
    print(f"5-2: {result.black_duration_sec}, {result.white_duration_sec}")

    if result.decoded_repaired:
        print(f"5-3 링크: {result.decoded_repaired}")


if __name__ == "__main__":
    main()