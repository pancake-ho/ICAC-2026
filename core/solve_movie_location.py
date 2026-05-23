from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests


ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


from core.config import load_config
from core.solar import call_solar
from core.upstage_client import UpstageClients
from core.utils import save_text


ENWIKI_API = "https://en.wikipedia.org/w/api.php"


@dataclass
class PhotoEvidence:
    photo_no: int
    caption: str
    visual_description: str
    visible_text: list[str]
    place_hint: str
    candidate_movies: list[str]


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def normalize_photo_items(raw: Any) -> list[PhotoEvidence]:
    if isinstance(raw, dict):
        items = raw.get("photos", [])
    elif isinstance(raw, list):
        items = raw
    else:
        raise ValueError("입력 JSON은 list 또는 {'photos': [...]} 형식이어야 합니다.")

    photos: list[PhotoEvidence] = []
    for item in items:
        photos.append(
            PhotoEvidence(
                photo_no=int(item["photo_no"]),
                caption=str(item.get("caption", "")),
                visual_description=str(item.get("visual_description", "")),
                visible_text=[str(x) for x in item.get("visible_text", [])],
                place_hint=str(item.get("place_hint", "")),
                candidate_movies=[str(x) for x in item.get("candidate_movies", [])],
            )
        )

    return sorted(photos, key=lambda x: x.photo_no)


def wiki_search_titles(query: str, limit: int = 5) -> list[str]:
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": str(limit),
        "format": "json",
        "utf8": "1",
    }
    res = requests.get(ENWIKI_API, params=params, timeout=20)
    res.raise_for_status()
    data = res.json()

    titles: list[str] = []
    for item in data.get("query", {}).get("search", []):
        title = item.get("title")
        if title:
            titles.append(title)

    return titles


def wiki_page_extract(title: str) -> dict[str, str]:
    params = {
        "action": "query",
        "prop": "extracts|pageprops",
        "exintro": "0",
        "explaintext": "1",
        "titles": title,
        "format": "json",
        "utf8": "1",
        "redirects": "1",
    }
    res = requests.get(ENWIKI_API, params=params, timeout=20)
    res.raise_for_status()
    data = res.json()

    pages = data.get("query", {}).get("pages", {})
    if not pages:
        return {"title": title, "extract": ""}

    page = next(iter(pages.values()))
    return {
        "title": page.get("title", title),
        "extract": page.get("extract", "")[:6000],
    }


def build_candidate_queries(photo: PhotoEvidence) -> list[str]:
    queries: list[str] = []

    for movie in photo.candidate_movies:
        queries.append(f"{movie} film")

    # 캡션/장소 힌트 기반 보조 검색
    if photo.place_hint:
        queries.append(f"{photo.place_hint} film location")
    if photo.caption:
        queries.append(f"{photo.caption} film")

    # 보이는 텍스트가 실제 영화 촬영지 단서일 수 있음
    for text in photo.visible_text[:5]:
        if len(text.strip()) >= 3:
            queries.append(f"{text} film location")

    # 중복 제거
    deduped: list[str] = []
    seen: set[str] = set()
    for q in queries:
        q = q.strip()
        if q and q.lower() not in seen:
            seen.add(q.lower())
            deduped.append(q)

    return deduped[:8]


def collect_wikipedia_evidence(
    photos: list[PhotoEvidence],
    sleep_sec: float = 0.15,
) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "source": "en.wikipedia.org",
        "photos": [],
    }

    fetched_titles: dict[str, dict[str, str]] = {}

    for photo in photos:
        queries = build_candidate_queries(photo)
        title_hits: list[str] = []

        for query in queries:
            try:
                hits = wiki_search_titles(query, limit=4)
                title_hits.extend(hits)
                time.sleep(sleep_sec)
            except Exception as exc:
                title_hits.append(f"[SEARCH_ERROR] {query}: {exc}")

        # 후보 영화명을 우선 보존
        for movie in photo.candidate_movies:
            if movie not in title_hits:
                title_hits.insert(0, movie)

        # 중복 제거
        unique_titles: list[str] = []
        seen: set[str] = set()
        for title in title_hits:
            key = title.lower()
            if key not in seen and not title.startswith("[SEARCH_ERROR]"):
                seen.add(key)
                unique_titles.append(title)

        page_evidence: list[dict[str, str]] = []
        for title in unique_titles[:8]:
            if title not in fetched_titles:
                try:
                    fetched_titles[title] = wiki_page_extract(title)
                    time.sleep(sleep_sec)
                except Exception as exc:
                    fetched_titles[title] = {
                        "title": title,
                        "extract": f"[FETCH_ERROR] {exc}",
                    }

            page_evidence.append(fetched_titles[title])

        evidence["photos"].append(
            {
                "photo_no": photo.photo_no,
                "caption": photo.caption,
                "visual_description": photo.visual_description,
                "visible_text": photo.visible_text,
                "place_hint": photo.place_hint,
                "candidate_movies": photo.candidate_movies,
                "wiki_queries": queries,
                "wiki_pages": page_evidence,
            }
        )

    return evidence


def extract_json_block(text: str) -> dict[str, Any]:
    stripped = text.strip()

    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"JSON 블록을 찾지 못했습니다.\n{text}")

    return json.loads(stripped[start : end + 1])


def build_solver_prompt(evidence: dict[str, Any], expected_count: int) -> str:
    return f"""
너는 영화 촬영지 단서 판별기다.

목표:
- 입력된 사진 evidence를 보고 각 사진이 어떤 영화의 촬영지를 담고 있는지 매칭한다.
- 영화 제목은 반드시 원어 제목으로 작성한다.
- 한국어 번역명, 국내 개봉명은 쓰지 않는다.
- 결과는 반드시 JSON 하나만 출력한다.
- photo_no는 오름차순으로 정렬한다.
- matches 배열 길이는 반드시 {expected_count}개다.

중요 규칙:
1. en.wikipedia.org 근거를 우선한다.
2. 사진 속 캡션, 보이는 간판, 장소 힌트, Wikipedia의 plot/filming/location 단서를 함께 비교한다.
3. 단순 분위기만으로 확정하지 말고, 직접 단서가 있는 후보를 우선한다.
4. 확실도가 낮아도 가장 가능성 높은 원어 영화 제목을 선택한다.
5. 출력 JSON 외의 설명 문장은 쓰지 않는다.

출력 형식:
{{
  "matches": [
    {{ "photo_no": 0, "movie_title": "" }}
  ]
}}

입력 evidence:
{json.dumps(evidence, ensure_ascii=False, indent=2)}
""".strip()


def build_review_prompt(evidence: dict[str, Any], matches: dict[str, Any]) -> str:
    return f"""
아래 영화 촬영지 매칭 결과를 심사위원 관점에서 재검토하라.

검토 기준:
- photo_no 오름차순 여부
- 원어 영화 제목 여부
- 사진 캡션/간판/장소 힌트와 영화 줄거리·촬영지의 정합성
- 위험한 매칭과 대체 후보
- 최종 제출 JSON

입력 evidence:
{json.dumps(evidence, ensure_ascii=False, indent=2)}

1차 matches:
{json.dumps(matches, ensure_ascii=False, indent=2)}

출력:
1. 최종 제출 JSON
2. 사진별 근거 2~3줄
3. 불안한 항목과 대체 후보
""".strip()


def solve_movie_locations(
    input_json: Path,
    out_dir: Path,
    expected_count: int,
) -> None:
    config = load_config()
    clients = UpstageClients(config)

    raw = load_json(input_json)
    photos = normalize_photo_items(raw)

    out_dir.mkdir(parents=True, exist_ok=True)

    evidence = collect_wikipedia_evidence(photos)
    evidence_path = out_dir / "01_wikipedia_evidence.json"
    save_json(evidence_path, evidence)

    system_prompt = (
        "You are a careful film-location matching assistant. "
        "Use only the given evidence and return strict JSON when requested."
    )

    solver_prompt = build_solver_prompt(evidence, expected_count)
    raw_answer = call_solar(
        config=config,
        clients=clients,
        system_prompt=system_prompt,
        user_prompt=solver_prompt,
        temperature=0.05,
    )

    raw_answer_path = out_dir / "02_raw_matches.txt"
    save_text(raw_answer_path, raw_answer)

    try:
        matches = extract_json_block(raw_answer)
    except Exception as exc:
        raise RuntimeError(
            f"Solar 응답 JSON 파싱 실패: {exc}\n원본 응답은 {raw_answer_path} 확인"
        ) from exc

    # photo_no 오름차순 강제
    if "matches" in matches and isinstance(matches["matches"], list):
        matches["matches"] = sorted(
            matches["matches"],
            key=lambda x: int(x.get("photo_no", 999999)),
        )

    final_json_path = out_dir / "03_matches.json"
    save_json(final_json_path, matches)

    review_prompt = build_review_prompt(evidence, matches)
    review = call_solar(
        config=config,
        clients=clients,
        system_prompt=system_prompt,
        user_prompt=review_prompt,
        temperature=0.1,
    )

    review_path = out_dir / "04_evidence_review.md"
    save_text(review_path, review)

    print("\n[3-2 영화 촬영지 매칭 완료]")
    print(f"- Wikipedia evidence: {evidence_path}")
    print(f"- Raw Solar answer: {raw_answer_path}")
    print(f"- Final JSON: {final_json_path}")
    print(f"- Evidence review: {review_path}")
    print("\n[제출 후보]")
    print(json.dumps(matches, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="ICAC 2026 3-2 영화 촬영지 매칭 보조 풀이기"
    )
    parser.add_argument(
        "--input",
        required=True,
        help="사진별 캡션/시각 단서 JSON 경로",
    )
    parser.add_argument(
        "--out",
        default="outputs/problem3_movie",
        help="결과 저장 폴더",
    )
    parser.add_argument(
        "--expected-count",
        type=int,
        default=10,
        help="3-1에서 식별한 실제 사진 개수. 기본 10",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    solve_movie_locations(
        input_json=Path(args.input),
        out_dir=Path(args.out),
        expected_count=args.expected_count,
    )


if __name__ == "__main__":
    main()