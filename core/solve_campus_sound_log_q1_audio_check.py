from __future__ import annotations

import argparse
import csv
import html
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz


Q1_CANDIDATES = [
    ("L09", "track_05", "오늘의 리듬이 우리를 move"),
    ("L10", "track_01", "우리가 만든 future flow"),
    ("L03", "track_05", "강의실 밖으로 뛰어 나와"),
    ("L04", "track_06", "형광펜 자국은 별자리처럼"),
    ("L06", "track_02", "두근대는 우리 첫 story"),
    ("L08", "NONE", "도서관 옥상에서 별을 헤아려"),
]

# 최종적으로 검증하고 싶은 화면 선택지
DEFAULT_DECISION = {
    "L09=track_05": True,
    "L10=track_01": True,
    "L03=track_05": False,
    "L04=track_06": True,
    "L06=track_02": True,
    "L08=NONE": True,
}


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str


def run_command(cmd: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


def find_audio(input_dir: Path, track_id: str) -> Path:
    candidates = []
    for ext in ("*.wav", "*.mp3", "*.m4a", "*.flac", "*.ogg"):
        candidates.extend(input_dir.rglob(ext))

    for p in sorted(candidates):
        name = p.name.lower()
        if "zone.identifier" in name:
            continue
        if track_id.lower() in name:
            return p

    raise FileNotFoundError(f"{track_id} 오디오를 찾지 못했습니다: {input_dir}")


def normalize_text(text: str) -> str:
    text = text.lower()
    text = text.replace("future flow", "futureflow")
    text = text.replace("move", "move")
    text = re.sub(r"[^가-힣a-z0-9]+", "", text)
    return text


def keyword_hit_score(lyric: str, transcript: str) -> tuple[int, list[str]]:
    """
    ASR이 완벽하지 않아도 핵심 단어가 잡히는지 본다.
    """
    lyric_norm = normalize_text(lyric)
    trans_norm = normalize_text(transcript)

    score = fuzz.partial_ratio(lyric_norm, trans_norm)
    hits = []

    keyword_sets = {
        "L09": ["리듬", "move"],
        "L10": ["future", "flow", "futureflow"],
        "L03": ["강의실", "밖", "뛰어", "나와"],
        "L04": ["형광펜", "별자리"],
        "L06": ["두근", "첫", "story"],
        "L08": ["도서관", "옥상", "별"],
    }

    for key, words in keyword_sets.items():
        if lyric.startswith("오늘의 리듬"):
            target_words = keyword_sets["L09"]
        elif lyric.startswith("우리가 만든"):
            target_words = keyword_sets["L10"]
        elif lyric.startswith("강의실"):
            target_words = keyword_sets["L03"]
        elif lyric.startswith("형광펜"):
            target_words = keyword_sets["L04"]
        elif lyric.startswith("두근"):
            target_words = keyword_sets["L06"]
        elif lyric.startswith("도서관"):
            target_words = keyword_sets["L08"]
        else:
            target_words = []

    for w in target_words:
        if normalize_text(w) in trans_norm:
            hits.append(w)

    # 핵심 단어 보너스
    score = int(score + len(hits) * 15)
    return min(score, 100), hits


def transcribe_with_whisper(audio_path: Path, out_dir: Path, model: str) -> list[TranscriptSegment]:
    """
    openai-whisper CLI로 전사한다.
    결과 json을 읽어 segment 단위로 반환한다.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "whisper",
        str(audio_path),
        "--model", model,
        "--language", "ko",
        "--task", "transcribe",
        "--output_format", "json",
        "--output_dir", str(out_dir),
        "--fp16", "False",
    ]

    code, stdout, stderr = run_command(cmd)
    if code != 0:
        raise RuntimeError(
            f"whisper 실행 실패\nCMD={' '.join(cmd)}\nSTDOUT={stdout}\nSTDERR={stderr}"
        )

    json_path = out_dir / f"{audio_path.stem}.json"
    if not json_path.exists():
        raise FileNotFoundError(f"Whisper JSON 결과를 찾지 못함: {json_path}")

    data = json.loads(json_path.read_text(encoding="utf-8"))
    segments = []

    for seg in data.get("segments", []):
        segments.append(
            TranscriptSegment(
                start=float(seg.get("start", 0.0)),
                end=float(seg.get("end", 0.0)),
                text=str(seg.get("text", "")).strip(),
            )
        )

    return segments


def transcript_text(segments: list[TranscriptSegment]) -> str:
    return " ".join(s.text for s in segments)


def best_segment_match(
    lyric: str,
    segments: list[TranscriptSegment],
) -> tuple[int, list[str], TranscriptSegment | None]:
    best_score = -1
    best_hits: list[str] = []
    best_seg: TranscriptSegment | None = None

    # 한 segment 또는 인접 2~3개 segment를 합쳐서 매칭
    for i in range(len(segments)):
        for width in (1, 2, 3):
            chunk = segments[i:i + width]
            if not chunk:
                continue
            text = " ".join(s.text for s in chunk)
            score, hits = keyword_hit_score(lyric, text)
            if score > best_score:
                best_score = score
                best_hits = hits
                best_seg = TranscriptSegment(
                    start=chunk[0].start,
                    end=chunk[-1].end,
                    text=text,
                )

    return best_score, best_hits, best_seg


def make_audio_clip(
    src_audio: Path,
    dst_audio: Path,
    start: float,
    end: float,
) -> None:
    dst_audio.parent.mkdir(parents=True, exist_ok=True)

    start = max(0.0, start - 2.0)
    duration = max(5.0, end - start + 4.0)

    cmd = [
        "ffmpeg",
        "-y",
        "-ss", f"{start:.3f}",
        "-t", f"{duration:.3f}",
        "-i", str(src_audio),
        "-acodec", "mp3",
        str(dst_audio),
    ]

    code, stdout, stderr = run_command(cmd)
    if code != 0:
        raise RuntimeError(f"ffmpeg clip 생성 실패: {stderr}")


def build_review_html(
    out_dir: Path,
    rows: list[dict[str, Any]],
) -> None:
    html_path = out_dir / "q1_audio_review.html"

    lines = []
    lines.append("<html><head><meta charset='utf-8'><title>Q1 Audio Review</title></head><body>")
    lines.append("<h1>ICAC 4-1 실제 오디오 기반 가사 검산</h1>")
    lines.append("<p>Whisper 전사는 완벽하지 않으므로, 점수와 함께 클립을 직접 들어서 최종 판단하세요.</p>")

    for row in rows:
        lines.append("<hr>")
        lines.append(f"<h2>{html.escape(row['candidate'])}</h2>")
        lines.append(f"<p><b>lyric:</b> {html.escape(row['lyric'])}</p>")
        lines.append(f"<p><b>ASR score:</b> {row['score']} / hits={html.escape(str(row['hits']))}</p>")
        lines.append(f"<p><b>best segment:</b> {html.escape(row['best_segment_text'])}</p>")
        lines.append(f"<p><b>time:</b> {row['best_start']}s ~ {row['best_end']}s</p>")

        if row.get("clip_rel"):
            lines.append(f"<audio controls src='{html.escape(row['clip_rel'])}'></audio>")

        lines.append(f"<p><b>recommended:</b> {row['recommended']}</p>")
        lines.append(f"<p><b>note:</b> {html.escape(row['note'])}</p>")

    lines.append("</body></html>")
    html_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ICAC 2026 4-1 실제 오디오/Whisper 기반 가사 조각 검산"
    )
    parser.add_argument(
        "--input-dir",
        required=True,
        help="campus_sound_log 폴더. 예: inputs/campus_sound_log",
    )
    parser.add_argument(
        "--out",
        default="outputs/campus_sound_log_q1_audio_check",
        help="결과 저장 폴더",
    )
    parser.add_argument(
        "--model",
        default="small",
        help="Whisper model. 빠르게는 tiny/base, 정확도는 small/medium",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="기존 Whisper 결과가 있어도 재전사",
    )

    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    out_dir = Path(args.out)
    transcript_dir = out_dir / "transcripts"
    clips_dir = out_dir / "clips"

    out_dir.mkdir(parents=True, exist_ok=True)
    transcript_dir.mkdir(parents=True, exist_ok=True)
    clips_dir.mkdir(parents=True, exist_ok=True)

    tracks_to_check = sorted(
        {
            track_id for _lid, track_id, _lyric in Q1_CANDIDATES
            if track_id != "NONE"
        }
    )

    audio_paths = {
        track_id: find_audio(input_dir, track_id)
        for track_id in tracks_to_check
    }

    all_segments: dict[str, list[TranscriptSegment]] = {}

    print("\n[Whisper 전사 시작]")
    for track_id, audio_path in audio_paths.items():
        json_path = transcript_dir / f"{audio_path.stem}.json"

        if json_path.exists() and not args.force:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            segments = [
                TranscriptSegment(
                    start=float(seg.get("start", 0.0)),
                    end=float(seg.get("end", 0.0)),
                    text=str(seg.get("text", "")).strip(),
                )
                for seg in data.get("segments", [])
            ]
            print(f"- {track_id}: 기존 전사 사용 {json_path}")
        else:
            print(f"- {track_id}: 전사 중 {audio_path}")
            segments = transcribe_with_whisper(audio_path, transcript_dir, args.model)

        all_segments[track_id] = segments

    rows: list[dict[str, Any]] = []

    print("\n[4-1 후보별 실제 오디오 매칭]")
    for lid, track_id, lyric in Q1_CANDIDATES:
        candidate_key = f"{lid}={track_id}"

        if track_id == "NONE":
            # NONE 후보는 모든 track transcript를 뒤져서 강하게 잡히는지 확인
            best = (-1, [], None, "")
            for tid, segments in all_segments.items():
                score, hits, seg = best_segment_match(lyric, segments)
                if score > best[0]:
                    best = (score, hits, seg, tid)

            score, hits, seg, best_tid = best
            if score >= 70 and len(hits) >= 2:
                recommended = "NO"
                note = f"NONE이라고 보기 어려움. {best_tid}에서 유사 가사 가능성 있음."
            else:
                recommended = "YES"
                note = "전체 전사에서 강한 매칭이 없어 NONE 판단 유지."

            best_segment_text = seg.text if seg else ""
            best_start = round(seg.start, 2) if seg else ""
            best_end = round(seg.end, 2) if seg else ""
            clip_rel = ""

        else:
            segments = all_segments[track_id]
            score, hits, seg = best_segment_match(lyric, segments)

            if score >= 70 or len(hits) >= 2:
                recommended = "YES"
                note = "전사 또는 핵심 키워드가 후보 track에서 잡힘."
            else:
                recommended = "NO"
                note = "전사에서 직접 가사/핵심 키워드가 약함. 실제 청취에서 안 들리면 체크하지 않는 것이 안전."

            best_segment_text = seg.text if seg else ""
            best_start = round(seg.start, 2) if seg else ""
            best_end = round(seg.end, 2) if seg else ""

            clip_rel = ""
            if seg:
                audio_path = audio_paths[track_id]
                clip_path = clips_dir / f"{candidate_key.replace('=', '_')}.mp3"
                make_audio_clip(
                    src_audio=audio_path,
                    dst_audio=clip_path,
                    start=seg.start,
                    end=seg.end,
                )
                clip_rel = f"clips/{clip_path.name}"

        row = {
            "candidate": candidate_key,
            "lyric_id": lid,
            "track": track_id,
            "lyric": lyric,
            "score": score,
            "hits": hits,
            "best_segment_text": best_segment_text,
            "best_start": best_start,
            "best_end": best_end,
            "clip_rel": clip_rel,
            "recommended": recommended,
            "previous_final_decision": DEFAULT_DECISION.get(candidate_key),
            "note": note,
        }

        rows.append(row)

        print(
            f"- {candidate_key}: recommended={recommended}, "
            f"score={score}, hits={hits}, segment='{best_segment_text}'"
        )

    csv_path = out_dir / "q1_audio_check.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    build_review_html(out_dir, rows)

    print("\n[완료]")
    print(f"- CSV: {csv_path}")
    print(f"- HTML: {out_dir / 'q1_audio_review.html'}")
    print("\n[열기]")
    print(f'explorer.exe "$(wslpath -w {out_dir / "q1_audio_review.html"})"')


if __name__ == "__main__":
    main()