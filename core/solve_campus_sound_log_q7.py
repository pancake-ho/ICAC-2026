from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TrackStyle:
    track_id: str
    prompt_id: str
    genre: str
    tempo: int | None
    key: str
    vocal: str
    meter: str
    energy: str
    instruments: set[str]
    mood_keywords: set[str]
    prompt_text: str


# 4-2에서 확인한 metadata 보정값
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

# 4-3에서 확정한 track -> prompt 매칭
FALLBACK_Q3_MATCHING = {
    "track_01": "P04",
    "track_02": "P10",
    "track_03": "P06",
    "track_04": "P02",
    "track_05": "P13",
    "track_06": "P08",
    "track_07": "P15",
    "track_08": "P11",
}

Q7_OPTIONS = [
    ("track_01", "track_05"),
    ("track_02", "track_08"),
    ("track_03", "track_06"),
    ("track_04", "track_07"),
    ("track_05", "track_08"),
    ("track_01", "track_04"),
]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def find_first_file(base: Path, candidates: list[str], exts: tuple[str, ...]) -> Path:
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


def parse_q3_answer(text: str) -> dict[str, str]:
    result: dict[str, str] = {}

    for part in text.strip().split(","):
        part = part.strip()
        if not part or "=" not in part:
            continue
        track_id, prompt_id = part.split("=", 1)
        result[track_id.strip()] = prompt_id.strip()

    return result


def load_q3_matching(q3_answer_path: Path | None) -> dict[str, str]:
    if q3_answer_path and q3_answer_path.exists():
        parsed = parse_q3_answer(read_text(q3_answer_path))
        if parsed:
            return parsed
    return dict(FALLBACK_Q3_MATCHING)


def normalize(value: Any) -> str:
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


def load_corrected_metadata(path: Path) -> dict[str, dict[str, Any]]:
    raw = json.loads(read_text(path))
    result: dict[str, dict[str, Any]] = {}

    for track_id, item in raw.items():
        fixed = dict(item)
        correction = METADATA_CORRECTIONS.get(track_id, {})
        fixed.update(correction)
        result[track_id] = fixed

    return result


def extract_tempo(prompt_text: str) -> int | None:
    m = re.search(r"(\d+)\s*bpm", prompt_text.lower())
    if not m:
        return None
    return int(m.group(1))


def extract_key(prompt_text: str) -> str:
    candidates = [
        ("E단조", "E minor"),
        ("F장조", "F major"),
        ("D단조", "D minor"),
        ("B♭단조", "B-flat minor"),
        ("G장조", "G major"),
        ("C♯단조", "C-sharp minor"),
        ("C장조", "C major"),
    ]
    for raw, key in candidates:
        if raw in prompt_text:
            return key
    return ""


def infer_genre(prompt_text: str, metadata_genre: str) -> str:
    p = prompt_text.lower()

    if "ai 챌린지 앤섬" in p or "k-pop edm" in p:
        return "KPOP_EDM_ANTHEM"
    if "축제 앤섬" in prompt_text:
        return "KPOP_EDM_ANTHEM"
    if "k-pop 신스팝" in p or "캠퍼스 k-pop" in p:
        return "KPOP"
    if "트랩 랩" in prompt_text:
        return "TRAP"
    if "로파이" in prompt_text:
        return "LOFI"
    if "재즈 왈츠" in prompt_text:
        return "JAZZ_WALTZ"
    if "어쿠스틱 포크" in prompt_text:
        return "ACOUSTIC_FOLK"
    if "레트로" in prompt_text and "시티팝" in prompt_text:
        return "RETRO_CITY_POP"

    return str(metadata_genre)


def infer_vocal(prompt_text: str, metadata_vocal: str) -> str:
    if "혼성 그룹 챈트" in prompt_text:
        return "mixed group chant"
    if "혼성 그룹 보컬" in prompt_text:
        return "mixed group vocals"
    if "여성 보컬" in prompt_text:
        return "female vocal"
    if "남성 랩" in prompt_text:
        return "male rap"
    if "보컬 없음" in prompt_text or "인스트루멘탈" in prompt_text:
        return "instrumental"
    if "남녀 듀엣" in prompt_text:
        return "male-female duet"

    return str(metadata_vocal)


def infer_meter(prompt_text: str, metadata_meter: str) -> str:
    if "3박자" in prompt_text or "왈츠" in prompt_text:
        return "3/4"
    if "비트 없음" in prompt_text:
        return "none"
    return str(metadata_meter) if metadata_meter else "4/4"


def infer_energy(prompt_text: str, genre: str) -> str:
    p = prompt_text.lower()
    g = normalize(genre)

    if "edm" in p or "앤섬" in prompt_text or "축제" in prompt_text:
        return "high"
    if "트랩" in prompt_text or "랩" in prompt_text:
        return "high"
    if "로파이" in prompt_text or "스터디" in prompt_text:
        return "low"
    if "재즈" in prompt_text or "왈츠" in prompt_text:
        return "medium-low"
    if "어쿠스틱" in prompt_text or "포크" in prompt_text:
        return "medium-low"
    if "시티팝" in prompt_text:
        return "medium"

    if "kpop edm anthem" in g:
        return "high"
    return "medium"


def infer_instruments(prompt_text: str, genre: str) -> set[str]:
    p = prompt_text.lower()
    instruments: set[str] = set()

    if "edm" in p or "앤섬" in prompt_text:
        instruments |= {"kick", "snare", "synth", "bass", "lead", "pad"}
    if "k-pop" in p or "kpop" in p:
        instruments |= {"drums", "bass", "synth", "vocal"}
    if "트랩" in prompt_text:
        instruments |= {"trap drums", "808 bass", "rap vocal", "dark synth"}
    if "로파이" in prompt_text:
        instruments |= {"lofi drums", "soft keys", "pad", "bass"}
    if "재즈" in prompt_text or "왈츠" in prompt_text:
        instruments |= {"piano", "jazz drums", "double bass", "brush"}
    if "어쿠스틱" in prompt_text or "포크" in prompt_text:
        instruments |= {"acoustic guitar", "soft percussion", "duet vocal"}
    if "시티팝" in prompt_text:
        instruments |= {"retro synth", "electric piano", "citypop drums", "bass"}

    if not instruments:
        instruments.add(normalize(genre))

    return instruments


def infer_mood_keywords(prompt_text: str) -> set[str]:
    keywords = set(re.findall(r"[가-힣a-zA-Z0-9]+", prompt_text.lower()))
    boosted = set()

    if "ai 챌린지" in prompt_text or "future flow" in prompt_text.lower():
        boosted |= {"anthem", "edm", "future", "challenge", "high_energy"}
    if "축제" in prompt_text or "무대" in prompt_text:
        boosted |= {"anthem", "edm", "festival", "stage", "high_energy"}
    if "새 학기" in prompt_text or "오리엔테이션" in prompt_text:
        boosted |= {"bright", "fresh", "campus", "pop"}
    if "로파이" in prompt_text or "도서관" in prompt_text:
        boosted |= {"lofi", "study", "calm", "instrumental"}
    if "마감" in prompt_text or "빌드 에러" in prompt_text:
        boosted |= {"dark", "deadline", "trap", "stress"}
    if "재즈 왈츠" in prompt_text or "시험" in prompt_text:
        boosted |= {"jazz", "waltz", "rainy", "exam"}
    if "고백" in prompt_text or "호수" in prompt_text:
        boosted |= {"acoustic", "romance", "duet", "lake"}
    if "졸업" in prompt_text or "셔틀" in prompt_text:
        boosted |= {"retro", "citypop", "graduation", "night"}

    return keywords | boosted


def build_track_styles(
    metadata: dict[str, dict[str, Any]],
    prompts: dict[str, str],
    q3_matching: dict[str, str],
) -> dict[str, TrackStyle]:
    styles: dict[str, TrackStyle] = {}

    for track_id, prompt_id in q3_matching.items():
        item = metadata[track_id]
        prompt_text = prompts[prompt_id]

        genre = infer_genre(prompt_text, item.get("reported_genre", ""))
        tempo = extract_tempo(prompt_text) or item.get("reported_tempo")
        key = extract_key(prompt_text) or str(item.get("reported_key", ""))
        vocal = infer_vocal(prompt_text, item.get("reported_vocal", ""))
        meter = infer_meter(prompt_text, item.get("reported_meter", ""))
        energy = infer_energy(prompt_text, genre)
        instruments = infer_instruments(prompt_text, genre)
        mood_keywords = infer_mood_keywords(prompt_text)

        styles[track_id] = TrackStyle(
            track_id=track_id,
            prompt_id=prompt_id,
            genre=genre,
            tempo=tempo,
            key=key,
            vocal=vocal,
            meter=meter,
            energy=energy,
            instruments=instruments,
            mood_keywords=mood_keywords,
            prompt_text=prompt_text,
        )

    return styles


def set_jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def score_pair(a: TrackStyle, b: TrackStyle) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []

    if normalize(a.genre) == normalize(b.genre):
        score += 35
        reasons.append(f"genre 일치: {a.genre}")

    if a.tempo is not None and b.tempo is not None:
        diff = abs(int(a.tempo) - int(b.tempo))
        if diff == 0:
            score += 25
            reasons.append(f"BPM 완전 일치: {a.tempo}")
        elif diff <= 2:
            score += 18
            reasons.append(f"BPM 근접: {a.tempo} vs {b.tempo}")
        elif diff <= 5:
            score += 8
            reasons.append(f"BPM 약간 근접: {a.tempo} vs {b.tempo}")

    if normalize(a.key) == normalize(b.key):
        score += 20
        reasons.append(f"Key 일치: {a.key}")

    # vocal은 mixed group vocals와 mixed group chant를 같은 계열로 인정
    av = normalize(a.vocal)
    bv = normalize(b.vocal)
    if av == bv:
        score += 20
        reasons.append(f"보컬 구성 완전 일치: {a.vocal}")
    elif "mixed group" in av and "mixed group" in bv:
        score += 15
        reasons.append(f"보컬 구성 계열 일치: {a.vocal} vs {b.vocal}")

    if normalize(a.meter) == normalize(b.meter):
        score += 10
        reasons.append(f"박자 일치: {a.meter}")

    if normalize(a.energy) == normalize(b.energy):
        score += 10
        reasons.append(f"에너지 레벨 일치: {a.energy}")

    inst_sim = set_jaccard(a.instruments, b.instruments)
    mood_sim = set_jaccard(a.mood_keywords, b.mood_keywords)

    if inst_sim >= 0.4:
        score += int(inst_sim * 15)
        reasons.append(f"악기 구성 유사도={inst_sim:.2f}")

    if mood_sim >= 0.12:
        score += int(mood_sim * 10)
        reasons.append(f"스타일/무드 키워드 유사도={mood_sim:.2f}")

    return score, reasons


def solve_q7(styles: dict[str, TrackStyle]) -> tuple[str, list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []

    for track_a, track_b in Q7_OPTIONS:
        a = styles[track_a]
        b = styles[track_b]
        score, reasons = score_pair(a, b)

        rows.append(
            {
                "pair": f"{track_a} - {track_b}",
                "score": score,
                "track_a_prompt": a.prompt_id,
                "track_b_prompt": b.prompt_id,
                "track_a_style": f"{a.genre}, {a.tempo} BPM, {a.key}, {a.vocal}, {a.meter}, {a.energy}",
                "track_b_style": f"{b.genre}, {b.tempo} BPM, {b.key}, {b.vocal}, {b.meter}, {b.energy}",
                "reason": " | ".join(reasons),
                "track_a_prompt_text": a.prompt_text,
                "track_b_prompt_text": b.prompt_text,
            }
        )

    rows.sort(key=lambda r: r["score"], reverse=True)
    return rows[0]["pair"], rows


def save_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    if not rows:
        return

    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ICAC 2026 4-7 다른 가사, 같은 스타일 쌍 찾기"
    )
    parser.add_argument(
        "--input-dir",
        required=True,
        help="campus_sound_log 폴더 경로. 예: inputs/campus_sound_log",
    )
    parser.add_argument(
        "--q3-answer",
        default="outputs/campus_sound_log_q3/q3_final_answer.txt",
        help="4-3 최종 답안 파일",
    )
    parser.add_argument(
        "--out",
        default="outputs/campus_sound_log_q7",
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

    prompts = parse_prompts(read_text(prompt_path))
    metadata = load_corrected_metadata(metadata_path)
    q3_matching = load_q3_matching(Path(args.q3_answer))

    styles = build_track_styles(
        metadata=metadata,
        prompts=prompts,
        q3_matching=q3_matching,
    )

    answer, rows = solve_q7(styles)

    save_csv(out_dir / "q7_pair_scores.csv", rows)
    (out_dir / "q7_final_answer.txt").write_text(answer, encoding="utf-8")

    print("\n[ICAC 4-7 같은 스타일 트랙 쌍 분석 완료]")
    print(f"- prompt 파일: {prompt_path}")
    print(f"- metadata 파일: {metadata_path}")
    print(f"- q3 답안 파일: {args.q3_answer}")
    print(f"- 점수 CSV: {out_dir / 'q7_pair_scores.csv'}")
    print(f"- 최종 답안 TXT: {out_dir / 'q7_final_answer.txt'}")

    print("\n[4-7 최종 답안]")
    print(answer)

    print("\n[후보별 점수]")
    for r in rows:
        print(f"- {r['pair']}: score={r['score']}")
        print(f"  {r['track_a_prompt']} style: {r['track_a_style']}")
        print(f"  {r['track_b_prompt']} style: {r['track_b_style']}")
        print(f"  reason: {r['reason']}")


if __name__ == "__main__":
    main()