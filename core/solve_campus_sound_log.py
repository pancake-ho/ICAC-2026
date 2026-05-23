from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# 앨범 커버 후보 이미지에서 직접 확인되는 강한 단서
# track_01: 호수 고백
# track_04: 새벽 프로젝트 마감
# track_06: AI 챌린지
# track_08: 대학 축제 무대
COVER_PROMPT_OVERRIDES = {
    "track_01": "P15",
    "track_04": "P02",
    "track_06": "P04",
    "track_08": "P13",
}

# 가사가 붙으면 안 되는 instrumental prompt
INSTRUMENTAL_PROMPTS = {"P06"}

KOREAN_STOPWORDS = {
    "그리고", "하지만", "아직도", "우리", "우리가", "오늘의", "때", "끝에서",
    "밖으로", "사이로", "자국은", "사진은", "만든", "노래를",
}

# 1번 화면에 보이는 후보. 필요하면 여기만 추가/수정하면 됨.
DEFAULT_Q1_CANDIDATES = [
    ("L09", "track_05"),
    ("L10", "track_01"),
    ("L03", "track_05"),
    ("L04", "track_06"),
    ("L06", "track_02"),
    ("L08", "NONE"),
]

Q2_CANDIDATES = [
    ("track_03", "reported_vocal", "female vocal"),
    ("track_04", "reported_tempo", 72),
    ("track_05", "reported_vocal", "mixed group chant"),
    ("track_06", "reported_meter", "3/4"),
    ("track_07", "reported_vocal", "male-female duet"),
    ("track_08", "reported_genre", "RETRO_CITY_POP"),
]

# 4-2는 prompt + 실제 사운드 청취 기반으로 확정 가능한 보정 매핑
# cover override가 아니라, prompt_candidates와 실제 오디오 검증을 합친 최종 매핑으로 둔다.
Q2_TRACK_PROMPT_HINTS = {
    "track_01": "P04",
    "track_02": "P10",
    "track_03": "P06",
    "track_04": "P02",
    "track_05": "P13",
    "track_06": "P08",
    "track_07": "P15",
    "track_08": "P11",
}


@dataclass
class TrackEvidence:
    track_id: str
    reported_genre: str
    reported_tempo: Any
    reported_key: str
    reported_vocal: str
    reported_meter: str


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_lyrics(text: str) -> dict[str, str]:
    lyrics: dict[str, str] = {}
    for line in text.splitlines():
        m = re.match(r"^(L\d+)\.\s*(.+)$", line.strip())
        if m:
            lyrics[m.group(1)] = m.group(2).strip()
    return lyrics


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


def tokenize_ko_en(text: str) -> set[str]:
    text = text.lower()
    tokens = re.findall(r"[가-힣a-zA-Z0-9♭#\-]+", text)
    return {
        t for t in tokens
        if len(t) >= 2 and t not in KOREAN_STOPWORDS
    }


def load_metadata(path: Path) -> dict[str, TrackEvidence]:
    raw = json.loads(read_text(path))
    tracks: dict[str, TrackEvidence] = {}

    for track_id, item in raw.items():
        tracks[track_id] = TrackEvidence(
            track_id=track_id,
            reported_genre=str(item.get("reported_genre", "")),
            reported_tempo=item.get("reported_tempo"),
            reported_key=str(item.get("reported_key", "")),
            reported_vocal=str(item.get("reported_vocal", "")),
            reported_meter=str(item.get("reported_meter", "")),
        )
    return tracks


def normalize_value(value: Any) -> str:
    return str(value).strip().lower().replace("♭", "flat").replace("-", "_").replace(" ", "_")


def expected_metadata_from_prompt(prompt_text: str) -> dict[str, Any]:
    """
    prompt_candidates.txt에서 metadata로 쓸 수 있는 값을 추출한다.
    4-2는 특히 genre/vocal/meter/tempo가 중요하다.
    """
    p = prompt_text.lower()
    expected: dict[str, Any] = {}

    # tempo
    m = re.search(r"(\d+)\s*bpm", p)
    if m:
        expected["reported_tempo"] = int(m.group(1))

    # meter
    if "3박자" in prompt_text or "왈츠" in prompt_text:
        expected["reported_meter"] = "3/4"
    elif "비트 없음" not in prompt_text:
        expected["reported_meter"] = "4/4"

    # genre
    if "레트로" in prompt_text and "시티팝" in prompt_text:
        expected["reported_genre"] = "RETRO_CITY_POP"
    elif "재즈 왈츠" in prompt_text:
        expected["reported_genre"] = "JAZZ_WALTZ"
    elif "트랩 랩" in prompt_text:
        expected["reported_genre"] = "TRAP"
    elif "로파이" in prompt_text:
        expected["reported_genre"] = "LOFI"
    elif "축제 앤섬" in prompt_text or "ai 챌린지 앤섬" in p:
        expected["reported_genre"] = "KPOP_EDM_ANTHEM"
    elif "어쿠스틱 포크" in prompt_text:
        expected["reported_genre"] = "ACOUSTIC_FOLK"
    elif "k-pop 신스팝" in p or "kpop" in p:
        expected["reported_genre"] = "KPOP"

    # vocal
    if "보컬 없음" in prompt_text or "인스트루멘탈" in prompt_text:
        expected["reported_vocal"] = "instrumental"
    elif "혼성 그룹 챈트" in prompt_text:
        expected["reported_vocal"] = "mixed group chant"
    elif "혼성 그룹 보컬" in prompt_text:
        expected["reported_vocal"] = "mixed group vocals"
    elif "남녀 듀엣" in prompt_text:
        expected["reported_vocal"] = "male-female duet"
    elif "남성 랩" in prompt_text:
        expected["reported_vocal"] = "male rap"
    elif "여성 보컬" in prompt_text:
        expected["reported_vocal"] = "female vocal"
    elif "남성 보컬" in prompt_text:
        expected["reported_vocal"] = "male vocal"

    return expected


def solve_q2_metadata_errors(
    tracks: dict[str, TrackEvidence],
    prompts: dict[str, str],
) -> list[dict[str, Any]]:
    """
    4-2 metadata 오류 탐지.
    화면 선택지의 '수정값'이 prompt/실제 사운드 기반 expected 값과 맞는지 판단한다.
    """
    rows: list[dict[str, Any]] = []

    for track_id, field, proposed_value in Q2_CANDIDATES:
        prompt_id = Q2_TRACK_PROMPT_HINTS.get(track_id)
        prompt_text = prompts.get(prompt_id, "") if prompt_id else ""
        expected = expected_metadata_from_prompt(prompt_text)

        current_track = tracks[track_id]
        current_value = getattr(current_track, field)

        expected_value = expected.get(field)

        if expected_value is None:
            submit_check = "NO"
            reason = "prompt에서 해당 field의 기대값을 안정적으로 추출하지 못함"
        else:
            submit_check = (
                "YES"
                if normalize_value(expected_value) == normalize_value(proposed_value)
                and normalize_value(current_value) != normalize_value(expected_value)
                else "NO"
            )
            reason = (
                f"{track_id}는 {prompt_id} 기준으로 {field}={expected_value}가 자연스럽고, "
                f"metadata 현재값은 {current_value}"
            )

        rows.append({
            "candidate": f"{track_id}:{field}={proposed_value}",
            "track": track_id,
            "field": field,
            "metadata_current": current_value,
            "proposed_value": proposed_value,
            "expected_from_prompt": expected_value,
            "via_prompt": prompt_id,
            "submit_check": submit_check,
            "reason": reason,
        })

    return rows

def score_prompt_for_track(track: TrackEvidence, prompt_text: str) -> int:
    """
    metadata와 prompt 후보의 정합성 점수.
    단, 문제에서 metadata 오류가 섞였다고 했으므로 정답 확정용이 아니라 후보 압축용이다.
    """
    p = prompt_text.lower()
    score = 0

    if track.reported_tempo and str(track.reported_tempo) in p:
        score += 4

    key_norm = track.reported_key.lower().replace("-", " ").replace("♭", "flat")
    p_norm = p.replace("♭", "flat")
    for word in key_norm.split():
        if len(word) >= 2 and word in p_norm:
            score += 1

    genre = track.reported_genre.lower()
    if "kpop" in genre or "k-pop" in p:
        if "k-pop" in p or "kpop" in p or "한국 캠퍼스 k-pop" in p:
            score += 2
    if "edm" in genre and "edm" in p:
        score += 2
    if "jazz" in genre and "재즈" in p:
        score += 3
    if "waltz" in genre and ("왈츠" in p or "3박자" in p):
        score += 3
    if "lofi" in genre and ("로파이" in p or "스터디 비트" in p):
        score += 3
    if "trap" in genre and ("트랩" in p or "랩" in p):
        score += 3
    if "folk" in genre and ("포크" in p or "어쿠스틱" in p):
        score += 2

    vocal = track.reported_vocal.lower()
    if "instrumental" in vocal and ("보컬 없음" in p or "인스트루멘탈" in p):
        score += 4
    if "female" in vocal and "여성" in p:
        score += 2
    if "male" in vocal and "남성" in p:
        score += 2
    if "mixed" in vocal and ("혼성" in p or "그룹" in p):
        score += 2

    return score


def build_track_prompt_candidates(
    tracks: dict[str, TrackEvidence],
    prompts: dict[str, str],
) -> dict[str, list[tuple[str, int, str]]]:
    result: dict[str, list[tuple[str, int, str]]] = {}

    for track_id, track in tracks.items():
        scored = []
        for pid, ptext in prompts.items():
            s = score_prompt_for_track(track, ptext)
            if s > 0:
                scored.append((pid, s, ptext))
        scored.sort(key=lambda x: x[1], reverse=True)
        result[track_id] = scored[:5]

    return result


def semantic_bonus(lyric: str, prompt: str) -> int:
    """
    가사 조각과 prompt의 의미 연결 보정.
    이 문제는 정확히 같은 단어가 없더라도 장면 연결이 중요해서
    핵심 캠퍼스 상황별 보너스를 둔다.
    """
    l = lyric.lower()
    p = prompt.lower()
    bonus = 0

    if any(x in l for x in ["학생증", "파란 후드", "첫 story"]) and any(
        x in p for x in ["학생증", "파란 후드", "새 학기", "오리엔테이션", "첫 캠퍼스"]
    ):
        bonus += 8

    if any(x in l for x in ["형광펜", "별자리"]) and any(
        x in p for x in ["형광펜", "시험 기간", "열람실", "비 오는", "재즈 왈츠"]
    ):
        bonus += 8

    if any(x in l for x in ["future flow", "문제 해결", "ai"]) and any(
        x in p for x in ["future flow", "ai 챌린지", "문서 파싱", "리더보드", "워크플로"]
    ):
        bonus += 10

    if any(x in l for x in ["리듬", "move", "뛰어 나와"]) and any(
        x in p for x in ["축제", "야외 무대", "푸드트럭", "조명", "앤섬", "edm"]
    ):
        bonus += 6

    if any(x in l for x in ["학식"]) and any(
        x in p for x in ["학식", "구내식당"]
    ):
        bonus += 10

    if any(x in l for x in ["호수", "고백"]) and any(
        x in p for x in ["호수", "고백", "듀엣"]
    ):
        bonus += 10

    if any(x in l for x in ["도서관", "별을 헤아려", "옥상"]) and any(
        x in p for x in ["도서관", "스터디", "로파이"]
    ):
        # 도서관은 맞지만 '옥상/별'은 prompt와 완전 일치가 아니므로 낮게만 준다.
        bonus += 3

    return bonus


def score_lyric_to_prompt(lyric: str, prompt: str) -> int:
    lt = tokenize_ko_en(lyric)
    pt = tokenize_ko_en(prompt)
    overlap = len(lt & pt)
    return overlap * 3 + semantic_bonus(lyric, prompt)


def build_lyric_prompt_candidates(
    lyrics: dict[str, str],
    prompts: dict[str, str],
) -> dict[str, list[tuple[str, int, str]]]:
    result: dict[str, list[tuple[str, int, str]]] = {}

    for lid, lyric in lyrics.items():
        scored = []
        for pid, ptext in prompts.items():
            s = score_lyric_to_prompt(lyric, ptext)
            if s > 0:
                scored.append((pid, s, ptext))
        scored.sort(key=lambda x: x[1], reverse=True)
        result[lid] = scored[:5]

    return result


def invert_track_prompt_candidates(
    track_prompt: dict[str, list[tuple[str, int, str]]]
) -> dict[str, list[tuple[str, int]]]:
    prompt_to_tracks: dict[str, list[tuple[str, int]]] = {}

    for track_id, rows in track_prompt.items():
        for pid, score, _ in rows:
            prompt_to_tracks.setdefault(pid, []).append((track_id, score))

    for pid in prompt_to_tracks:
        prompt_to_tracks[pid].sort(key=lambda x: x[1], reverse=True)

    return prompt_to_tracks

def infer_lyric_to_tracks(
    lyric_prompt: dict[str, list[tuple[str, int, str]]],
    prompt_to_tracks: dict[str, list[tuple[str, int]]],
) -> dict[str, list[tuple[str, int, str]]]:
    """
    lyric -> prompt -> track으로 후보 전파.

    보강 사항:
    1. instrumental prompt는 가사 조각 매칭에서 제외한다.
    2. track_cover_candidate 이미지에서 확인된 track->prompt override를 강하게 반영한다.
    """
    result: dict[str, list[tuple[str, int, str]]] = {}

    # prompt_to_tracks에 cover override를 강제로 추가
    corrected_prompt_to_tracks = {k: list(v) for k, v in prompt_to_tracks.items()}

    for track_id, prompt_id in COVER_PROMPT_OVERRIDES.items():
        corrected_prompt_to_tracks.setdefault(prompt_id, [])

        # 이미 있으면 점수 보강, 없으면 강한 점수로 추가
        exists = False
        new_rows = []
        for tid, score in corrected_prompt_to_tracks[prompt_id]:
            if tid == track_id:
                new_rows.append((tid, max(score, 30)))
                exists = True
            else:
                new_rows.append((tid, score))

        if not exists:
            new_rows.append((track_id, 30))

        new_rows.sort(key=lambda x: x[1], reverse=True)
        corrected_prompt_to_tracks[prompt_id] = new_rows

    for lid, p_rows in lyric_prompt.items():
        candidates: list[tuple[str, int, str]] = []

        for pid, lp_score, _ in p_rows:
            # 보컬 없는 instrumental prompt는 가사 조각 후보에서 제외
            if pid in INSTRUMENTAL_PROMPTS:
                continue

            for track_id, pt_score in corrected_prompt_to_tracks.get(pid, []):
                total = lp_score + pt_score

                # cover override와 직접 연결되는 경우 보너스
                if COVER_PROMPT_OVERRIDES.get(track_id) == pid:
                    total += 20

                candidates.append((track_id, total, pid))

        candidates.sort(key=lambda x: x[1], reverse=True)

        dedup: list[tuple[str, int, str]] = []
        seen = set()
        for track_id, total, pid in candidates:
            if track_id not in seen:
                dedup.append((track_id, total, pid))
                seen.add(track_id)

        result[lid] = dedup[:5]

    return result


def save_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_report(
    out_dir: Path,
    lyrics: dict[str, str],
    prompts: dict[str, str],
    tracks: dict[str, TrackEvidence],
    track_prompt: dict[str, list[tuple[str, int, str]]],
    lyric_prompt: dict[str, list[tuple[str, int, str]]],
    lyric_tracks: dict[str, list[tuple[str, int, str]]],
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    track_rows = []
    for track_id, rows in track_prompt.items():
        for rank, (pid, score, ptext) in enumerate(rows, start=1):
            track_rows.append({
                "track": track_id,
                "rank": rank,
                "prompt": pid,
                "score": score,
                "prompt_text": ptext,
            })
    save_csv(out_dir / "track_prompt_candidates.csv", track_rows)

    lyric_rows = []
    for lid, rows in lyric_prompt.items():
        for rank, (pid, score, ptext) in enumerate(rows, start=1):
            lyric_rows.append({
                "lyric_id": lid,
                "lyric": lyrics[lid],
                "rank": rank,
                "prompt": pid,
                "score": score,
                "prompt_text": ptext,
            })
    save_csv(out_dir / "lyric_prompt_candidates.csv", lyric_rows)

    lt_rows = []
    for lid, rows in lyric_tracks.items():
        if not rows:
            lt_rows.append({
                "lyric_id": lid,
                "lyric": lyrics[lid],
                "rank": "",
                "track": "NONE",
                "score": 0,
                "via_prompt": "",
            })
            continue

        for rank, (track_id, score, pid) in enumerate(rows, start=1):
            lt_rows.append({
                "lyric_id": lid,
                "lyric": lyrics[lid],
                "rank": rank,
                "track": track_id,
                "score": score,
                "via_prompt": pid,
            })
    save_csv(out_dir / "lyric_track_candidates.csv", lt_rows)

    md = []
    md.append("# Campus Sound Log 분석 결과\n")
    md.append("## 1) track -> prompt 후보\n")
    for track_id, rows in track_prompt.items():
        md.append(f"\n### {track_id}")
        meta = tracks[track_id]
        md.append(
            f"- metadata: genre={meta.reported_genre}, tempo={meta.reported_tempo}, "
            f"key={meta.reported_key}, vocal={meta.reported_vocal}, meter={meta.reported_meter}"
        )
        for pid, score, ptext in rows[:3]:
            md.append(f"- {pid} / score={score}: {ptext}")

    md.append("\n\n## 2) lyric -> track 후보\n")
    for lid, rows in lyric_tracks.items():
        md.append(f"\n### {lid}. {lyrics[lid]}")
        if not rows:
            md.append("- 후보 없음")
        else:
            for track_id, score, pid in rows[:3]:
                md.append(f"- {track_id} / score={score} / via {pid}")

    (out_dir / "report.md").write_text("\n".join(md), encoding="utf-8")


def solve_q1_candidates(
    lyrics: dict[str, str],
    lyric_tracks: dict[str, list[tuple[str, int, str]]],
    candidates: list[tuple[str, str]],
) -> list[dict[str, Any]]:
    rows = []

    for lid, target_track in candidates:
        ranked = lyric_tracks.get(lid, [])
        top_track = ranked[0][0] if ranked else "NONE"
        top_score = ranked[0][1] if ranked else 0
        top_prompt = ranked[0][2] if ranked else ""

        # L08은 "도서관 옥상/별"이지만, 제공 prompt에서 도서관 트랙 P06은 instrumental이다.
        # 따라서 가사 조각이 붙을 수 없으므로 NONE 가능성을 강하게 본다.
        if lid == "L08":
            predicted = "NONE"
        else:
            predicted = top_track if top_score >= 10 else "NONE"

        is_checked = predicted == target_track

        rows.append({
            "candidate": f"{lid} = {target_track if target_track != 'NONE' else '일치하는 트랙 없음'}",
            "lyric": lyrics.get(lid, ""),
            "predicted": predicted,
            "top_score": top_score,
            "via_prompt": top_prompt,
            "submit_check": "YES" if is_checked else "NO",
            "top5": ranked,
        })

    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ICAC 2026 4번 campus_sound_log 전용 분석기"
    )
    parser.add_argument(
        "--input-dir",
        required=True,
        help="campus_sound_log 폴더 경로. 예: inputs/campus_sound_log",
    )
    parser.add_argument(
        "--out",
        default="outputs/campus_sound_log",
        help="결과 저장 폴더",
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    out_dir = Path(args.out)

    lyrics_path = input_dir / "lyrics_fragments.txt"
    prompts_path = input_dir / "prompt_candidates.txt"
    metadata_path = input_dir / "metadata.json"

    if not lyrics_path.exists():
        raise FileNotFoundError(f"lyrics_fragments.txt 없음: {lyrics_path}")
    if not prompts_path.exists():
        raise FileNotFoundError(f"prompt_candidates.txt 없음: {prompts_path}")
    if not metadata_path.exists():
        raise FileNotFoundError(f"metadata.json 없음: {metadata_path}")

    lyrics = parse_lyrics(read_text(lyrics_path))
    prompts = parse_prompts(read_text(prompts_path))
    tracks = load_metadata(metadata_path)

    track_prompt = build_track_prompt_candidates(tracks, prompts)
    lyric_prompt = build_lyric_prompt_candidates(lyrics, prompts)
    prompt_to_tracks = invert_track_prompt_candidates(track_prompt)
    lyric_tracks = infer_lyric_to_tracks(lyric_prompt, prompt_to_tracks)

    write_report(
        out_dir=out_dir,
        lyrics=lyrics,
        prompts=prompts,
        tracks=tracks,
        track_prompt=track_prompt,
        lyric_prompt=lyric_prompt,
        lyric_tracks=lyric_tracks,
    )

    q1_rows = solve_q1_candidates(
        lyrics=lyrics,
        lyric_tracks=lyric_tracks,
        candidates=DEFAULT_Q1_CANDIDATES,
    )

    q2_rows = solve_q2_metadata_errors(
        tracks=tracks,
        prompts=prompts,
    )

    save_csv(out_dir / "q2_metadata_error_judgement.csv", q2_rows)

    save_csv(out_dir / "q1_candidate_judgement.csv", q1_rows)

    print("\n[ICAC 4번 campus_sound_log 분석 완료]")
    print(f"- 결과 폴더: {out_dir}")
    print(f"- track->prompt 후보: {out_dir / 'track_prompt_candidates.csv'}")
    print(f"- lyric->prompt 후보: {out_dir / 'lyric_prompt_candidates.csv'}")
    print(f"- lyric->track 후보: {out_dir / 'lyric_track_candidates.csv'}")
    print(f"- 1번 후보 판단: {out_dir / 'q1_candidate_judgement.csv'}")
    print(f"- 보고서: {out_dir / 'report.md'}")

    print("\n[1번 후보 체크 판단]")
    for row in q1_rows:
        print(
            f"- {row['candidate']}: {row['submit_check']} "
            f"(pred={row['predicted']}, score={row['top_score']}, via={row['via_prompt']})"
        )

    print("\n[주의]")
    print("- 이 코드는 metadata/prompt/lyrics 기반 1차 분석기다.")
    print("- 문제 설명상 metadata에 오류가 섞여 있으므로, 최종 제출 전 오디오와 앨범 커버 후보를 반드시 같이 확인해야 한다.")
    print("- 특히 track_01, track_04, track_06, track_08은 track_cover_candidate 이미지가 강한 단서다.")

    print(f"- 2번 metadata 오류 판단: {out_dir / 'q2_metadata_error_judgement.csv'}")

    print("\n[2번 metadata 오류 체크 판단]")
    for row in q2_rows:
        print(
            f"- {row['candidate']}: {row['submit_check']} "
            f"(current={row['metadata_current']}, expected={row['expected_from_prompt']}, via={row['via_prompt']})"
        )


if __name__ == "__main__":
    main()