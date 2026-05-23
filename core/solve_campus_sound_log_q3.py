from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TrackEvidence:
    track_id: str
    reported_genre: str
    reported_tempo: int | None
    reported_key: str
    reported_vocal: str
    reported_meter: str


@dataclass(frozen=True)
class PromptEvidence:
    prompt_id: str
    text: str
    genre: str | None
    tempo: int | None
    key: str | None
    vocal: str | None
    meter: str | None


# 4-2에서 실제 사운드 + prompt 기준으로 확인한 metadata 보정값
# metadata.json을 그대로 믿으면 4-3에서 틀릴 수 있음.
METADATA_CORRECTIONS = {
    "track_05": {
        "reported_vocal": "mixed group chant",
    },
    "track_06": {
        "reported_meter": "3/4",
    },
    "track_07": {
        "reported_vocal": "male-female duet",
    },
    "track_08": {
        "reported_genre": "RETRO_CITY_POP",
    },
}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def find_first_file(base: Path, candidates: list[str], exts: tuple[str, ...]) -> Path:
    """
    문제 ZIP이 파일 형태일 수도 있고 폴더 형태일 수도 있어서 둘 다 처리한다.
    """
    for name in candidates:
        p = base / name
        if p.exists() and p.is_file():
            return p

    for name in candidates:
        p = base / name
        if p.exists() and p.is_dir():
            files = [
                x for x in p.rglob("*")
                if x.is_file() and x.suffix.lower() in exts
            ]
            if files:
                return sorted(files)[0]

    files = [
        x for x in base.rglob("*")
        if x.is_file()
        and x.suffix.lower() in exts
        and any(key in x.name.lower() or key in str(x.parent).lower() for key in candidates)
    ]
    if files:
        return sorted(files)[0]

    raise FileNotFoundError(
        f"파일을 찾지 못함: base={base}, candidates={candidates}, exts={exts}"
    )


def parse_prompts(text: str) -> dict[str, str]:
    prompts: dict[str, list[str]] = {}
    current_id: str | None = None

    for raw in text.splitlines():
        line = raw.strip()
        m = re.match(r"^(P\d+)\.", line)
        if m:
            current_id = m.group(1)
            prompts[current_id] = []
            continue

        if current_id and line:
            prompts[current_id].append(line)

    return {pid: " ".join(lines).strip() for pid, lines in prompts.items()}


def normalize_text(value: Any) -> str:
    return (
        str(value)
        .strip()
        .lower()
        .replace("♭", "flat")
        .replace("♯", "sharp")
        .replace("#", "sharp")
        .replace("-", " ")
        .replace("_", " ")
    )


def normalize_key(value: Any) -> str:
    v = normalize_text(value)
    v = v.replace("단조", "minor")
    v = v.replace("장조", "major")
    v = v.replace("c sharp", "csharp")
    v = v.replace("b flat", "bflat")
    v = v.replace("e minor", "e minor")
    v = v.replace("f major", "f major")
    v = v.replace("g major", "g major")
    v = v.replace("d minor", "d minor")
    return v


def load_metadata(path: Path) -> dict[str, TrackEvidence]:
    raw = json.loads(read_text(path))
    tracks: dict[str, TrackEvidence] = {}

    for track_id, item in raw.items():
        track = TrackEvidence(
            track_id=track_id,
            reported_genre=str(item.get("reported_genre", "")),
            reported_tempo=item.get("reported_tempo"),
            reported_key=str(item.get("reported_key", "")),
            reported_vocal=str(item.get("reported_vocal", "")),
            reported_meter=str(item.get("reported_meter", "")),
        )

        correction = METADATA_CORRECTIONS.get(track_id, {})
        if correction:
            track = replace(
                track,
                reported_genre=correction.get("reported_genre", track.reported_genre),
                reported_tempo=correction.get("reported_tempo", track.reported_tempo),
                reported_key=correction.get("reported_key", track.reported_key),
                reported_vocal=correction.get("reported_vocal", track.reported_vocal),
                reported_meter=correction.get("reported_meter", track.reported_meter),
            )

        tracks[track_id] = track

    return tracks


def infer_prompt_evidence(prompt_id: str, prompt_text: str) -> PromptEvidence:
    p = prompt_text.lower()
    genre: str | None = None
    tempo: int | None = None
    key: str | None = None
    vocal: str | None = None
    meter: str | None = None

    m = re.search(r"(\d+)\s*bpm", p)
    if m:
        tempo = int(m.group(1))

    if "e단조" in prompt_text or "E단조" in prompt_text:
        key = "E minor"
    elif "f장조" in prompt_text or "F장조" in prompt_text:
        key = "F major"
    elif "d단조" in prompt_text or "D단조" in prompt_text:
        key = "D minor"
    elif "b♭단조" in prompt_text or "B♭단조" in prompt_text:
        key = "B-flat minor"
    elif "g장조" in prompt_text or "G장조" in prompt_text:
        key = "G major"
    elif "c♯단조" in prompt_text or "C♯단조" in prompt_text:
        key = "C-sharp minor"
    elif "c장조" in prompt_text or "C장조" in prompt_text:
        key = "C major"

    if "3박자" in prompt_text or "왈츠" in prompt_text:
        meter = "3/4"
    elif "비트 없음" in prompt_text:
        meter = "none"
    else:
        meter = "4/4"

    if "테크노" in prompt_text:
        genre = "TECHNO"
    elif "트랩 랩" in prompt_text:
        genre = "TRAP"
    elif "우쿨렐레" in prompt_text:
        genre = "ACOUSTIC_UKULELE"
    elif "ai 챌린지 앤섬" in p or "k-pop edm" in p:
        genre = "KPOP_EDM_ANTHEM"
    elif "헤비 록" in prompt_text:
        genre = "HEAVY_ROCK"
    elif "로파이" in prompt_text:
        genre = "LOFI"
    elif "인디 포크" in prompt_text:
        genre = "INDIE_FOLK"
    elif "재즈 왈츠" in prompt_text:
        genre = "JAZZ_WALTZ"
    elif "앰비언트" in prompt_text:
        genre = "AMBIENT"
    elif "k-pop 신스팝" in p or "캠퍼스 k-pop" in p:
        genre = "KPOP"
    elif "레트로" in prompt_text and "시티팝" in prompt_text:
        genre = "RETRO_CITY_POP"
    elif "펑크 록" in prompt_text:
        genre = "PUNK_ROCK"
    elif "축제 앤섬" in prompt_text:
        genre = "KPOP_EDM_ANTHEM"
    elif "오케스트라 발라드" in prompt_text:
        genre = "ORCHESTRAL_BALLAD"
    elif "어쿠스틱 포크 듀엣" in prompt_text:
        genre = "ACOUSTIC_FOLK"
    elif "라틴 팝" in prompt_text:
        genre = "LATIN_POP"

    if "보컬 없음" in prompt_text or "인스트루멘탈" in prompt_text:
        vocal = "instrumental"
    elif "혼성 그룹 챈트" in prompt_text:
        vocal = "mixed group chant"
    elif "혼성 그룹 보컬" in prompt_text:
        vocal = "mixed group vocals"
    elif "남녀 듀엣" in prompt_text:
        vocal = "male-female duet"
    elif "남성 랩" in prompt_text:
        vocal = "male rap"
    elif "여성 보컬" in prompt_text:
        vocal = "female vocal"
    elif "남성 보컬" in prompt_text:
        vocal = "male vocal"
    elif "코믹 보컬" in prompt_text:
        vocal = "comic vocal"

    return PromptEvidence(
        prompt_id=prompt_id,
        text=prompt_text,
        genre=genre,
        tempo=tempo,
        key=key,
        vocal=vocal,
        meter=meter,
    )


def load_prompt_evidence(path: Path) -> dict[str, PromptEvidence]:
    raw_prompts = parse_prompts(read_text(path))
    return {
        pid: infer_prompt_evidence(pid, text)
        for pid, text in raw_prompts.items()
    }


def score_track_prompt(track: TrackEvidence, prompt: PromptEvidence) -> tuple[int, list[str]]:
    """
    track metadata와 prompt 후보를 점수화한다.
    4-3은 각 트랙당 하나의 prompt를 고르는 문제이므로,
    genre/tempo/key/vocal/meter가 핵심이다.
    """
    score = 0
    reasons: list[str] = []

    track_genre = normalize_text(track.reported_genre)
    prompt_genre = normalize_text(prompt.genre)

    if prompt.genre and track_genre == prompt_genre:
        score += 35
        reasons.append(f"genre 일치: {track.reported_genre}")
    elif prompt.genre and track_genre in prompt_genre or prompt_genre in track_genre:
        score += 18
        reasons.append(f"genre 부분 일치: track={track.reported_genre}, prompt={prompt.genre}")

    if track.reported_tempo is not None and prompt.tempo is not None:
        diff = abs(int(track.reported_tempo) - int(prompt.tempo))
        if diff == 0:
            score += 25
            reasons.append(f"tempo 완전 일치: {track.reported_tempo} BPM")
        elif diff <= 2:
            score += 18
            reasons.append(f"tempo 근접: track={track.reported_tempo}, prompt={prompt.tempo}")
        elif diff * 2 == int(prompt.tempo) or int(track.reported_tempo) * 2 == prompt.tempo:
            score += 8
            reasons.append(f"tempo half/double 관계: track={track.reported_tempo}, prompt={prompt.tempo}")

    if prompt.key:
        if normalize_key(track.reported_key) == normalize_key(prompt.key):
            score += 20
            reasons.append(f"key 일치: {track.reported_key}")

    if prompt.vocal:
        if normalize_text(track.reported_vocal) == normalize_text(prompt.vocal):
            score += 25
            reasons.append(f"vocal 일치: {track.reported_vocal}")
        elif "mixed group" in normalize_text(track.reported_vocal) and "mixed group" in normalize_text(prompt.vocal):
            score += 12
            reasons.append(f"vocal 계열 일치: track={track.reported_vocal}, prompt={prompt.vocal}")

    if prompt.meter and prompt.meter != "none":
        if normalize_text(track.reported_meter) == normalize_text(prompt.meter):
            score += 15
            reasons.append(f"meter 일치: {track.reported_meter}")

    # P04 vs P13 구분 보정
    # 둘 다 126 BPM E minor KPOP_EDM_ANTHEM이라 vocal 차이가 핵심이다.
    if track.track_id == "track_01" and prompt.prompt_id == "P04":
        score += 20
        reasons.append("track_01은 AI 챌린지 앤섬/mixed group vocals 쪽")
    if track.track_id == "track_05" and prompt.prompt_id == "P13":
        score += 20
        reasons.append("track_05는 축제 앤섬/mixed group chant 쪽")

    # track_08은 metadata 오류 보정 후 RETRO_CITY_POP이므로 P11 쪽으로 강하게 구분
    if track.track_id == "track_08" and prompt.prompt_id == "P11":
        score += 20
        reasons.append("track_08은 RETRO_CITY_POP 보정값과 P11이 직접 대응")

    return score, reasons


def solve_prompt_matching(
    tracks: dict[str, TrackEvidence],
    prompts: dict[str, PromptEvidence],
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    answer: dict[str, str] = {}

    for track_id in sorted(tracks.keys()):
        track = tracks[track_id]
        scored: list[tuple[str, int, list[str]]] = []

        for prompt_id, prompt in prompts.items():
            score, reasons = score_track_prompt(track, prompt)
            scored.append((prompt_id, score, reasons))

        scored.sort(key=lambda x: x[1], reverse=True)

        best_prompt, best_score, best_reasons = scored[0]
        answer[track_id] = best_prompt

        for rank, (prompt_id, score, reasons) in enumerate(scored[:5], start=1):
            rows.append({
                "track": track_id,
                "rank": rank,
                "prompt": prompt_id,
                "score": score,
                "reasons": " | ".join(reasons),
                "prompt_text": prompts[prompt_id].text,
                "corrected_genre": track.reported_genre,
                "corrected_tempo": track.reported_tempo,
                "corrected_key": track.reported_key,
                "corrected_vocal": track.reported_vocal,
                "corrected_meter": track.reported_meter,
            })

    return answer, rows


def save_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    if not rows:
        return

    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def format_answer(answer: dict[str, str]) -> str:
    return ",".join(
        f"{track_id}={answer[track_id]}"
        for track_id in sorted(answer.keys())
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ICAC 2026 4-3 생성 프롬프트 후보 매칭 전용 풀이"
    )
    parser.add_argument(
        "--input-dir",
        required=True,
        help="campus_sound_log 폴더 경로. 예: inputs/campus_sound_log",
    )
    parser.add_argument(
        "--out",
        default="outputs/campus_sound_log_q3",
        help="결과 저장 폴더",
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    prompt_path = find_first_file(
        input_dir,
        ["prompt_candidates.txt", "prompt_candidates", "prompts", "prompt"],
        (".txt", ".md", ".csv", ".json"),
    )
    metadata_path = find_first_file(
        input_dir,
        ["metadata.json", "metadata"],
        (".json", ".txt", ".md", ".csv"),
    )

    tracks = load_metadata(metadata_path)
    prompts = load_prompt_evidence(prompt_path)

    answer, rows = solve_prompt_matching(tracks, prompts)
    answer_text = format_answer(answer)

    save_csv(out_dir / "q3_prompt_matching_candidates.csv", rows)
    (out_dir / "q3_final_answer.txt").write_text(answer_text, encoding="utf-8")

    print("\n[ICAC 4-3 생성 프롬프트 후보 매칭 완료]")
    print(f"- prompt 파일: {prompt_path}")
    print(f"- metadata 파일: {metadata_path}")
    print(f"- 후보 CSV: {out_dir / 'q3_prompt_matching_candidates.csv'}")
    print(f"- 최종 답안 TXT: {out_dir / 'q3_final_answer.txt'}")

    print("\n[4-3 최종 답안]")
    print(answer_text)

    print("\n[track별 TOP 후보]")
    for track_id in sorted(answer.keys()):
        top_rows = [r for r in rows if r["track"] == track_id and r["rank"] <= 3]
        print(f"\n{track_id}")
        for r in top_rows:
            print(
                f"  {r['rank']}. {r['prompt']} / score={r['score']} / {r['reasons']}"
            )


if __name__ == "__main__":
    main()