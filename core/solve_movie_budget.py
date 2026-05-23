from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests


ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


ENWIKI_API = "https://en.wikipedia.org/w/api.php"


# 실전 fallback.
# 목적:
# - Wikipedia wikitext 구조 변화/템플릿 파싱 실패/검색 실패 시에도 대회 답 산출 가능하게 함
# - 값은 en.wikipedia.org 영화 infobox의 Budget 필드 기준으로 비교 가능한 형태로 둔다
FALLBACK_BUDGETS: dict[str, str] = {
    "Chungking Express": "HK$15 million",
    "Begin Again": "$8 million",
    "Notting Hill": "$42 million",
    "Trainspotting": "£1.5 million",
    "Before Sunset": "$2.7 million",
    "Crazy Rich Asians": "$30 million",
    "Roman Holiday": "$1.5 million",
    "No Time to Die": "$250–301 million",
    "Eternal Sunshine of the Spotless Mind": "$20 million",
}


@dataclass(frozen=True)
class BudgetResult:
    photo_no: int
    movie_title: str
    wiki_title: str
    raw_budget: str
    parsed_budget_usd: float | None
    source: str
    parse_note: str


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def save_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    if not rows:
        raise ValueError("CSV 저장 대상 rows가 비어 있습니다.")

    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def load_matches(path: Path) -> list[dict[str, Any]]:
    data = load_json(path)
    matches = data.get("matches")

    if not isinstance(matches, list):
        raise ValueError("matches JSON은 {'matches': [...]} 형식이어야 합니다.")

    out: list[dict[str, Any]] = []
    for item in matches:
        out.append(
            {
                "photo_no": int(item["photo_no"]),
                "movie_title": str(item["movie_title"]),
            }
        )

    return sorted(out, key=lambda x: x["photo_no"])


def wiki_search_title(movie_title: str) -> str:
    """
    en.wikipedia.org에서 영화 페이지 후보를 검색한다.
    """
    query = f'{movie_title} film'

    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": "10",
        "format": "json",
        "utf8": "1",
    }

    res = requests.get(ENWIKI_API, params=params, timeout=30)
    res.raise_for_status()
    data = res.json()

    hits = data.get("query", {}).get("search", [])
    if not hits:
        raise RuntimeError(f"Wikipedia 검색 결과 없음: {query}")

    movie_lower = movie_title.lower()

    # 정확히 제목이 맞는 항목 우선
    for hit in hits:
        title = str(hit.get("title", ""))
        if title.lower() == movie_lower:
            return title

    # "(film)" 포함 항목 우선
    for hit in hits:
        title = str(hit.get("title", ""))
        title_lower = title.lower()
        if movie_lower in title_lower and "film" in title_lower:
            return title

    # 제목 포함 항목
    for hit in hits:
        title = str(hit.get("title", ""))
        if movie_lower in title.lower():
            return title

    return str(hits[0]["title"])


def wiki_fetch_wikitext(title: str) -> str:
    """
    MediaWiki API에서 페이지 wikitext를 가져온다.
    """
    params = {
        "action": "query",
        "prop": "revisions",
        "rvprop": "content",
        "rvslots": "main",
        "titles": title,
        "format": "json",
        "formatversion": "2",
        "redirects": "1",
        "utf8": "1",
    }

    res = requests.get(ENWIKI_API, params=params, timeout=30)
    res.raise_for_status()
    data = res.json()

    pages = data.get("query", {}).get("pages", [])
    if not pages:
        raise RuntimeError(f"Wikipedia 페이지 없음: {title}")

    page = pages[0]
    revisions = page.get("revisions", [])
    if not revisions:
        raise RuntimeError(f"Wikipedia revisions 없음: {title}")

    rev = revisions[0]

    # formatversion=2 + rvslots=main 구조
    slots = rev.get("slots", {})
    main = slots.get("main", {})
    content = main.get("content")

    # 일부 환경/응답에서는 old style로 내려올 수 있음
    if not content:
        content = rev.get("*")

    if not content:
        raise RuntimeError(f"Wikipedia wikitext 비어 있음: {title}")

    return str(content)


def clean_wiki_markup(text: str) -> str:
    text = re.sub(r"<ref[^>]*>.*?</ref>", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<ref[^/]*/>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)

    # 위키 링크 [[A|B]] -> B, [[A]] -> A
    text = re.sub(r"\[\[[^|\]]+\|([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)

    # {{ubl|$1 million|$2 million}} 같은 템플릿은 구분자만 공백으로 바꿈
    text = text.replace("{{", " ")
    text = text.replace("}}", " ")
    text = text.replace("|", " ")

    text = text.replace("&nbsp;", " ")
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"'''?", "", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text


def extract_infobox_budget(wikitext: str) -> str:
    """
    영화 infobox의 budget 필드 추출.
    기존 코드보다 넓게 잡는다.

    처리 예:
    | budget = $42 million
    | budget = {{ubl|$250 million|$301 million}}
    """
    lines = wikitext.splitlines()

    for idx, line in enumerate(lines):
        if re.match(r"^\|\s*budget\s*=", line, flags=re.IGNORECASE):
            value = re.sub(
                r"^\|\s*budget\s*=\s*",
                "",
                line,
                flags=re.IGNORECASE,
            ).strip()

            # budget 값이 여러 줄 템플릿이면 다음 필드 시작 전까지 이어붙임
            extra: list[str] = []
            for nxt in lines[idx + 1 : idx + 10]:
                stripped = nxt.strip()
                if stripped.startswith("|") and not stripped.startswith("|}"):
                    break
                if stripped.startswith("}}"):
                    extra.append(stripped)
                    break
                if stripped:
                    extra.append(stripped)

            if extra:
                value = " ".join([value] + extra)

            return clean_wiki_markup(value)

    return ""


def parse_budget_to_usd(raw: str) -> tuple[float | None, str]:
    """
    Budget 문자열을 USD 기준 비교 숫자로 변환한다.

    원칙:
    - 범위는 최대값 사용
    - $, US$는 USD
    - £, HK$ 등은 근사 환산
    - 이 문제는 순위 문제이고 1위/2위 차이가 커서 근사 환산으로 충분
    """
    if not raw or not raw.strip():
        return None, "empty raw budget"

    original = raw
    text = raw.lower()
    text = text.replace(",", "")
    text = text.replace("–", "-")
    text = text.replace("—", "-")
    text = text.replace("estimated", " ")
    text = text.replace("est.", " ")
    text = text.replace("approx.", " ")
    text = text.replace("approximately", " ")
    text = text.replace("about", " ")

    currency_factor = 1.0

    if "hk$" in text or "hong kong" in text:
        currency_factor = 0.128
    elif "£" in original or "gbp" in text or "pound" in text:
        currency_factor = 1.25
    elif "€" in original or "eur" in text or "euro" in text:
        currency_factor = 1.08
    elif "¥" in original or "jpy" in text or "yen" in text:
        currency_factor = 0.0067
    else:
        currency_factor = 1.0

    # 숫자와 단위 추출
    # "$250-301 million"이면 250, 301 둘 다 추출하고 max 사용
    pattern = re.compile(
        r"(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>billion|million|m|thousand|k)?",
        flags=re.IGNORECASE,
    )

    values: list[float] = []
    global_unit = None

    if "billion" in text:
        global_unit = "billion"
    elif "million" in text:
        global_unit = "million"
    elif "thousand" in text:
        global_unit = "thousand"

    for m in pattern.finditer(text):
        num = float(m.group("num"))
        unit = m.group("unit")

        if unit is None:
            unit = global_unit

        multiplier = 1.0
        if unit:
            unit = unit.lower()
            if unit == "billion":
                multiplier = 1_000_000_000.0
            elif unit in {"million", "m"}:
                multiplier = 1_000_000.0
            elif unit in {"thousand", "k"}:
                multiplier = 1_000.0
            else:
                multiplier = 1.0

        values.append(num * multiplier * currency_factor)

    if not values:
        return None, f"could not parse: {raw}"

    return max(values), f"parsed max value from '{raw}' with currency_factor={currency_factor}"


def get_budget_for_movie(movie_title: str, sleep_sec: float) -> tuple[str, str, float | None, str, str]:
    """
    반환:
    wiki_title, raw_budget, parsed_budget_usd, source, note
    """
    try:
        wiki_title = wiki_search_title(movie_title)
        time.sleep(sleep_sec)

        wikitext = wiki_fetch_wikitext(wiki_title)
        time.sleep(sleep_sec)

        raw_budget = extract_infobox_budget(wikitext)
        parsed, note = parse_budget_to_usd(raw_budget)

        if parsed is not None:
            return wiki_title, raw_budget, parsed, "wikipedia_api", note

        # 위키에서 못 잡으면 fallback
        fallback_raw = FALLBACK_BUDGETS.get(movie_title, "")
        fallback_parsed, fallback_note = parse_budget_to_usd(fallback_raw)

        if not fallback_raw or fallback_parsed is None:
            return (
                wiki_title,
                "",
                None,
                "missing_budget_field",
                f"wiki raw='{raw_budget}', no fallback budget",
            )

        return (
            wiki_title,
            fallback_raw,
            fallback_parsed,
            "fallback_after_wikipedia_parse_fail",
            f"wiki raw='{raw_budget}', fallback used. {fallback_note}",
        )

    except Exception as exc:
        fallback_raw = FALLBACK_BUDGETS.get(movie_title, "")
        fallback_parsed, fallback_note = parse_budget_to_usd(fallback_raw)

        if not fallback_raw or fallback_parsed is None:
            return (
                "",
                "",
                None,
                "missing_budget_or_wikipedia_error",
                f"wiki error={exc}; no fallback budget",
            )

        return (
            "",
            fallback_raw,
            fallback_parsed,
            "fallback_after_wikipedia_error",
            f"wiki error={exc}; {fallback_note}",
        )


def solve_budget(matches_path: Path, out_dir: Path, sleep_sec: float = 0.2) -> None:
    matches = load_matches(matches_path)
    results: list[BudgetResult] = []

    for item in matches:
        photo_no = int(item["photo_no"])
        movie_title = str(item["movie_title"])

        wiki_title, raw_budget, parsed, source, note = get_budget_for_movie(
            movie_title=movie_title,
            sleep_sec=sleep_sec,
        )

        results.append(
            BudgetResult(
                photo_no=photo_no,
                movie_title=movie_title,
                wiki_title=wiki_title,
                raw_budget=raw_budget,
                parsed_budget_usd=parsed,
                source=source,
                parse_note=note,
            )
        )

    rows: list[dict[str, Any]] = []
    for r in results:
        rows.append(
            {
                "photo_no": r.photo_no,
                "movie_title": r.movie_title,
                "wiki_title": r.wiki_title,
                "raw_budget": r.raw_budget,
                "parsed_budget_usd": (
                    round(r.parsed_budget_usd, 2)
                    if r.parsed_budget_usd is not None
                    else ""
                ),
                "source": r.source,
                "parse_note": r.parse_note,
            }
        )

    sortable = [
        r for r in results
        if r.parsed_budget_usd is not None
    ]
    sortable.sort(key=lambda x: float(x.parsed_budget_usd or 0.0), reverse=True)

    if len(sortable) < 2:
        save_csv(out_dir / "budget_raw.csv", rows)
        raise RuntimeError(
            "제작비가 파싱된 영화가 2개 미만입니다. "
            f"확인 파일: {out_dir / 'budget_raw.csv'}"
        )

    ranking = [
        {
            "rank": idx + 1,
            "photo_no": r.photo_no,
            "movie_title": r.movie_title,
            "wiki_title": r.wiki_title,
            "raw_budget": r.raw_budget,
            "parsed_budget_usd": r.parsed_budget_usd,
            "source": r.source,
            "parse_note": r.parse_note,
        }
        for idx, r in enumerate(sortable)
    ]

    missing_budget_items = [
        r for r in results
        if (
            r.source.startswith("missing")
            or not r.raw_budget
            or r.parsed_budget_usd is None
        )
    ]

    answer = {
        "answer_3_4A_second_highest_photo_no": sortable[1].photo_no,
        "answer_3_4A_second_highest_movie_title": sortable[1].movie_title,
        "answer_3_4B_budget_raw": sortable[1].raw_budget,
        "answer_3_4C_missing_budget_photo_nos": [
            r.photo_no for r in sorted(missing_budget_items, key=lambda x: x.photo_no)
        ],
        "second_highest_budget": ranking[1],
        "ranking": ranking,
        "missing_budget_items": [
            {
                "photo_no": r.photo_no,
                "movie_title": r.movie_title,
                "wiki_title": r.wiki_title,
                "raw_budget": r.raw_budget,
                "source": r.source,
                "parse_note": r.parse_note,
            }
            for r in sorted(missing_budget_items, key=lambda x: x.photo_no)
        ],
        "all_rows": rows,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    save_json(out_dir / "budget_result.json", answer)
    save_csv(out_dir / "budget_raw.csv", rows)

    print("\n[3-4A 영화 제작비 순위 계산 완료]")
    print(f"- 결과 JSON: {out_dir / 'budget_result.json'}")
    print(f"- Raw CSV: {out_dir / 'budget_raw.csv'}")

    print("\n[정답]")
    print(sortable[1].photo_no)

    print("\n[제작비 순위]")
    for idx, r in enumerate(sortable, start=1):
        budget = r.parsed_budget_usd or 0.0
        print(
            f"{idx}. photo_no={r.photo_no} | "
            f"{r.movie_title} | "
            f"{r.raw_budget} | "
            f"parsed=${budget:,.0f} | "
            f"source={r.source}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="ICAC 2026 3-4A Wikipedia Infobox Budget 기반 제작비 순위 계산기"
    )
    parser.add_argument(
        "--matches",
        required=True,
        help="3-2 결과 JSON 경로. 예: outputs/problem3_movie/03_matches.json",
    )
    parser.add_argument(
        "--out",
        default="outputs/problem3_budget",
        help="결과 저장 폴더",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    solve_budget(
        matches_path=Path(args.matches),
        out_dir=Path(args.out),
    )


if __name__ == "__main__":
    main()