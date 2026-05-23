from __future__ import annotations

import argparse
import csv
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import librosa
import numpy as np


REQUIRED_STEMS = [
    ("lead_vocals", ["lead vocal", "lead_vocal", "lead vocals", "vocal"]),
    ("drums", ["drum", "drums"]),
    ("Bass", ["bass"]),
    ("keyboard", ["keyboard", "keys", "piano"]),
    ("synth", ["synth", "synthesizer"]),
]


@dataclass(frozen=True)
class SessionAudio:
    session_id: str
    stem_label: str
    path: Path


def find_target_track(input_dir: Path, track_id: str = "track_08") -> Path:
    candidates = []

    for ext in ("*.wav", "*.mp3", "*.m4a", "*.flac", "*.ogg"):
        candidates.extend(input_dir.rglob(ext))

    for p in sorted(candidates):
        name = p.name.lower()
        if track_id.lower() in name and "zone.identifier" not in name:
            return p

    raise FileNotFoundError(f"{track_id} 오디오 파일을 찾지 못했습니다: {input_dir}")


def find_session_pool(input_dir: Path) -> Path:
    direct = input_dir / "session_pool"
    if direct.exists() and direct.is_dir():
        return direct

    for p in input_dir.rglob("*"):
        if p.is_dir() and p.name.lower() == "session_pool":
            return p

    raise FileNotFoundError(f"session_pool 폴더를 찾지 못했습니다: {input_dir}")


def parse_session_audio(path: Path) -> SessionAudio | None:
    name = path.stem
    m = re.search(r"(S\d+)", name, re.IGNORECASE)
    if not m:
        return None

    session_id = m.group(1).upper()

    stem_label = re.sub(r"S\d+", "", name, flags=re.IGNORECASE)
    stem_label = stem_label.replace("_", " ").replace("-", " ").strip()

    return SessionAudio(
        session_id=session_id,
        stem_label=stem_label,
        path=path,
    )


def load_sessions(session_pool: Path) -> list[SessionAudio]:
    exts = {".wav", ".mp3", ".m4a", ".flac", ".ogg"}
    sessions: list[SessionAudio] = []

    for p in sorted(session_pool.rglob("*")):
        if not p.is_file():
            continue
        if p.suffix.lower() not in exts:
            continue
        if "zone.identifier" in p.name.lower():
            continue

        parsed = parse_session_audio(p)
        if parsed:
            sessions.append(parsed)

    if not sessions:
        raise RuntimeError(f"session_pool에서 세션 음원을 찾지 못했습니다: {session_pool}")

    return sessions


def normalize_label(text: str) -> str:
    return text.lower().replace("_", " ").replace("-", " ").strip()


def infer_required_stem(stem_label: str) -> str | None:
    label = normalize_label(stem_label)

    # backing vocals는 lead_vocals와 다르므로 제외
    if "backing" in label:
        return None

    for required_name, aliases in REQUIRED_STEMS:
        for alias in aliases:
            if alias in label:
                return required_name

    return None


def safe_normalize_audio(y: np.ndarray) -> np.ndarray:
    y = np.asarray(y, dtype=np.float32)
    y = np.nan_to_num(y)

    max_abs = float(np.max(np.abs(y))) if y.size else 0.0
    if max_abs > 1e-8:
        y = y / max_abs

    return y


def load_audio(path: Path, sr: int, duration: float | None = None) -> np.ndarray:
    y, _ = librosa.load(path, sr=sr, mono=True, duration=duration)
    return safe_normalize_audio(y)


def zscore_feature(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float32)
    return (x - x.mean(axis=1, keepdims=True)) / (x.std(axis=1, keepdims=True) + 1e-6)


def extract_features(y: np.ndarray, sr: int, hop_length: int) -> dict[str, np.ndarray]:
    mel = librosa.feature.melspectrogram(
        y=y,
        sr=sr,
        n_mels=32,
        fmax=min(4000, sr // 2),
        hop_length=hop_length,
    )
    mel = zscore_feature(np.log1p(mel))

    chroma = librosa.feature.chroma_stft(
        y=y,
        sr=sr,
        hop_length=hop_length,
    )
    chroma = zscore_feature(chroma)

    onset = librosa.onset.onset_strength(
        y=y,
        sr=sr,
        hop_length=hop_length,
    )
    onset = onset.reshape(1, -1)
    onset = zscore_feature(onset)

    low_mel = librosa.feature.melspectrogram(
        y=y,
        sr=sr,
        n_mels=24,
        fmax=min(500, sr // 2),
        hop_length=hop_length,
    )
    low_mel = zscore_feature(np.log1p(low_mel))

    return {
        "mel": mel,
        "chroma": chroma,
        "onset": onset,
        "low_mel": low_mel,
    }


def max_sliding_cosine(candidate: np.ndarray, target: np.ndarray, step_frames: int) -> tuple[float, int]:
    """
    candidate feature가 target full mix 안에 얼마나 잘 포함되는지 sliding cosine으로 비교.
    session stem은 80초, track_08 full mix는 더 길 수 있으므로 target 안에서 가장 잘 맞는 위치를 찾는다.
    """
    cand = candidate
    targ = target

    cand_len = cand.shape[1]
    targ_len = targ.shape[1]

    if cand_len == 0 or targ_len == 0:
        return -999.0, 0

    if targ_len < cand_len:
        cand, targ = targ, cand
        cand_len, targ_len = targ_len, cand_len

    cand_norm = cand / (np.linalg.norm(cand, axis=0, keepdims=True) + 1e-6)
    targ_norm = targ / (np.linalg.norm(targ, axis=0, keepdims=True) + 1e-6)

    best_score = -999.0
    best_offset = 0

    max_offset = targ_len - cand_len
    for offset in range(0, max_offset + 1, max(1, step_frames)):
        segment = targ_norm[:, offset:offset + cand_len]
        score = float(np.mean(np.sum(cand_norm * segment, axis=0)))

        if score > best_score:
            best_score = score
            best_offset = offset

    return best_score, best_offset


def score_session_against_track(
    session: SessionAudio,
    target_features: dict[str, np.ndarray],
    sr: int,
    hop_length: int,
) -> dict[str, Any]:
    y = load_audio(session.path, sr=sr, duration=90.0)
    features = extract_features(y, sr=sr, hop_length=hop_length)

    step_frames = max(1, int(sr / hop_length))  # 약 1초 간격

    mel_score, mel_offset = max_sliding_cosine(
        features["mel"],
        target_features["mel"],
        step_frames=step_frames,
    )
    chroma_score, chroma_offset = max_sliding_cosine(
        features["chroma"],
        target_features["chroma"],
        step_frames=step_frames,
    )
    onset_score, onset_offset = max_sliding_cosine(
        features["onset"],
        target_features["onset"],
        step_frames=step_frames,
    )
    low_mel_score, low_mel_offset = max_sliding_cosine(
        features["low_mel"],
        target_features["low_mel"],
        step_frames=step_frames,
    )

    # full mix 안에 포함된 stem을 찾는 문제라 mel/chroma/onset/low band를 종합
    combo = (
        0.45 * mel_score
        + 0.25 * chroma_score
        + 0.20 * onset_score
        + 0.10 * low_mel_score
    )

    return {
        "session_id": session.session_id,
        "stem_label": session.stem_label,
        "required_stem": infer_required_stem(session.stem_label),
        "path": str(session.path),
        "mel_score": mel_score,
        "chroma_score": chroma_score,
        "onset_score": onset_score,
        "low_mel_score": low_mel_score,
        "combo_score": combo,
        "best_offset_sec": round(mel_offset * hop_length / sr, 3),
    }


def save_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    if not rows:
        return

    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def solve_required_sessions(rows: list[dict[str, Any]]) -> tuple[list[str], list[dict[str, Any]]]:
    selected: list[str] = []
    selected_rows: list[dict[str, Any]] = []

    for required_name, _aliases in REQUIRED_STEMS:
        candidates = [
            r for r in rows
            if r["required_stem"] == required_name
        ]

        if not candidates:
            raise RuntimeError(f"{required_name} 후보 세션을 찾지 못했습니다.")

        candidates.sort(key=lambda r: r["combo_score"], reverse=True)
        best = candidates[0]

        selected.append(best["session_id"])
        selected_rows.append(best)

    return selected, selected_rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ICAC 2026 4-6 Campus Light track_08 세션 복원"
    )
    parser.add_argument(
        "--input-dir",
        required=True,
        help="campus_sound_log 폴더 경로. 예: inputs/campus_sound_log",
    )
    parser.add_argument(
        "--out",
        default="outputs/campus_sound_log_q6",
        help="결과 저장 폴더",
    )
    parser.add_argument(
        "--sr",
        type=int,
        default=8000,
        help="분석용 sampling rate. 빠른 검증은 8000 권장",
    )
    parser.add_argument(
        "--hop-length",
        type=int,
        default=512,
        help="feature hop length",
    )

    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    target_path = find_target_track(input_dir, track_id="track_08")
    session_pool = find_session_pool(input_dir)
    sessions = load_sessions(session_pool)

    print("\n[파일 감지]")
    print(f"- target track: {target_path}")
    print(f"- session_pool: {session_pool}")
    print(f"- sessions: {len(sessions)}개")

    target_y = load_audio(target_path, sr=args.sr, duration=None)
    target_features = extract_features(target_y, sr=args.sr, hop_length=args.hop_length)

    rows: list[dict[str, Any]] = []
    for session in sessions:
        row = score_session_against_track(
            session=session,
            target_features=target_features,
            sr=args.sr,
            hop_length=args.hop_length,
        )
        rows.append(row)

    rows.sort(key=lambda r: r["combo_score"], reverse=True)

    selected, selected_rows = solve_required_sessions(rows)

    save_csv(out_dir / "q6_all_session_scores.csv", rows)
    save_csv(out_dir / "q6_selected_sessions.csv", selected_rows)

    answer_json = json.dumps(selected, ensure_ascii=False)
    (out_dir / "q6_final_answer.json").write_text(answer_json, encoding="utf-8")

    print("\n[ICAC 4-6 Campus Light 세션 복원 완료]")
    print(f"- 전체 점수 CSV: {out_dir / 'q6_all_session_scores.csv'}")
    print(f"- 선택 세션 CSV: {out_dir / 'q6_selected_sessions.csv'}")
    print(f"- 최종 답안 JSON: {out_dir / 'q6_final_answer.json'}")

    print("\n[stem별 선택 결과]")
    for r in selected_rows:
        print(
            f"- {r['required_stem']}: {r['session_id']} "
            f"({r['stem_label']}) score={r['combo_score']:.4f}, "
            f"offset={r['best_offset_sec']}s"
        )

    print("\n[전체 TOP 점수]")
    for r in rows[:10]:
        print(
            f"- {r['session_id']} {r['stem_label']}: "
            f"required={r['required_stem']}, score={r['combo_score']:.4f}, "
            f"mel={r['mel_score']:.4f}, chroma={r['chroma_score']:.4f}, onset={r['onset_score']:.4f}"
        )

    print("\n[4-6 최종 제출 JSON]")
    print(answer_json)


if __name__ == "__main__":
    main()