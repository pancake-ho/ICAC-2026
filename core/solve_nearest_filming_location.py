from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests


ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


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
        raise ValueError("CSV로 저장할 rows가 비어 있습니다.")

    fieldnames = list(rows[0].keys())

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


@dataclass(frozen=True)
class Coordinate:
    lat: float
    lon: float


def haversine_km(a: Coordinate, b: Coordinate) -> float:
    """
    위도/경도 두 점 사이의 대권거리(km)를 계산한다.
    """
    radius_km = 6371.0088

    lat1 = math.radians(a.lat)
    lon1 = math.radians(a.lon)
    lat2 = math.radians(b.lat)
    lon2 = math.radians(b.lon)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    h = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2.0) ** 2
    )

    return 2.0 * radius_km * math.asin(math.sqrt(h))


def geocode_nominatim(query: str, sleep_sec: float = 1.0) -> Coordinate:
    """
    OpenStreetMap Nominatim으로 주소를 좌표화한다.

    실전 안정성:
    - Nominatim은 User-Agent가 필요하다.
    - 너무 빠른 연속 요청을 피하기 위해 sleep을 둔다.
    - 주소 좌표가 입력 JSON에 이미 있으면 이 함수는 쓰지 않는 것을 권장한다.
    """
    time.sleep(sleep_sec)

    url = "https://nominatim.openstreetmap.org/search"
    headers = {
        "User-Agent": "ICAC-2026-nearest-filming-location/1.0"
    }
    params = {
        "q": query,
        "format": "json",
        "limit": 1,
    }

    res = requests.get(url, params=params, headers=headers, timeout=30)
    res.raise_for_status()

    data = res.json()
    if not data:
        raise RuntimeError(f"주소를 좌표화하지 못했습니다: {query}")

    return Coordinate(
        lat=float(data[0]["lat"]),
        lon=float(data[0]["lon"]),
    )


def parse_coord(obj: dict[str, Any], *, name: str) -> Coordinate:
    try:
        return Coordinate(
            lat=float(obj["lat"]),
            lon=float(obj["lon"]),
        )
    except KeyError as exc:
        raise KeyError(f"{name}에 lat/lon 필드가 필요합니다: {obj}") from exc


def load_matches(path: Path) -> list[dict[str, Any]]:
    data = load_json(path)
    matches = data.get("matches")
    if not isinstance(matches, list):
        raise ValueError("matches JSON은 {'matches': [...]} 형식이어야 합니다.")

    normalized: list[dict[str, Any]] = []
    for item in matches:
        normalized.append(
            {
                "photo_no": int(item["photo_no"]),
                "movie_title": str(item["movie_title"]),
            }
        )

    return sorted(normalized, key=lambda x: x["photo_no"])


def load_location_map(path: Path) -> dict[int, dict[str, Any]]:
    data = load_json(path)

    if isinstance(data, dict):
        raw_locations = data.get("locations", [])
    elif isinstance(data, list):
        raw_locations = data
    else:
        raise ValueError("locations JSON은 list 또는 {'locations': [...]} 형식이어야 합니다.")

    location_map: dict[int, dict[str, Any]] = {}
    for loc in raw_locations:
        photo_no = int(loc["photo_no"])
        location_map[photo_no] = loc

    return location_map


def load_restaurant(path: Path) -> dict[str, Any]:
    data = load_json(path)
    if not isinstance(data, dict):
        raise ValueError("restaurant JSON은 object 형식이어야 합니다.")
    return data


def solve_nearest(
    matches_path: Path,
    locations_path: Path,
    restaurant_path: Path,
    out_dir: Path,
    allow_geocode: bool,
) -> None:
    matches = load_matches(matches_path)
    location_map = load_location_map(locations_path)
    restaurant = load_restaurant(restaurant_path)

    if "lat" in restaurant and "lon" in restaurant:
        restaurant_coord = parse_coord(restaurant, name="restaurant")
    else:
        if not allow_geocode:
            raise RuntimeError(
                "restaurant JSON에 lat/lon이 없습니다. "
                "--allow-geocode를 쓰거나 lat/lon을 직접 넣으세요."
            )
        restaurant_coord = geocode_nominatim(str(restaurant["address"]))

    rows: list[dict[str, Any]] = []

    for match in matches:
        photo_no = int(match["photo_no"])
        movie_title = str(match["movie_title"])

        if photo_no not in location_map:
            raise KeyError(f"photo_no={photo_no}에 대한 위치 정보가 없습니다.")

        loc = location_map[photo_no]
        coord = parse_coord(loc, name=f"photo_no={photo_no}")

        distance_km = haversine_km(restaurant_coord, coord)

        rows.append(
            {
                "photo_no": photo_no,
                "movie_title": movie_title,
                "location_name": loc.get("location_name", ""),
                "city": loc.get("city", ""),
                "country": loc.get("country", ""),
                "lat": coord.lat,
                "lon": coord.lon,
                "distance_km": round(distance_km, 3),
                "confidence": loc.get("confidence", ""),
                "note": loc.get("note", ""),
            }
        )

    rows.sort(key=lambda x: float(x["distance_km"]))

    answer = {
        "restaurant": {
            "name": restaurant.get("name", ""),
            "address": restaurant.get("address", ""),
            "lat": restaurant_coord.lat,
            "lon": restaurant_coord.lon,
        },
        "nearest": rows[0],
        "ranking": rows,
    }

    out_dir.mkdir(parents=True, exist_ok=True)

    save_json(out_dir / "nearest_result.json", answer)
    save_csv(out_dir / "distance_ranking.csv", rows)

    print("\n[3-3 가장 가까운 촬영지 계산 완료]")
    print(f"- 결과 JSON: {out_dir / 'nearest_result.json'}")
    print(f"- 거리 순위 CSV: {out_dir / 'distance_ranking.csv'}")
    print("\n[정답]")
    print(rows[0]["photo_no"])
    print("\n[가장 가까운 후보]")
    print(json.dumps(rows[0], ensure_ascii=False, indent=2))
    print("\n[거리 순위 Top 5]")
    for row in rows[:5]:
        print(
            f"- photo_no={row['photo_no']} | "
            f"{row['movie_title']} | "
            f"{row['location_name']} | "
            f"{row['distance_km']} km"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="ICAC 2026 3-3 식당 기준 가장 가까운 영화 촬영지 계산기"
    )
    parser.add_argument(
        "--matches",
        required=True,
        help="3-2 결과 JSON 경로. 예: outputs/problem3_movie/03_matches.json",
    )
    parser.add_argument(
        "--locations",
        required=True,
        help="사진별 대표 촬영지 좌표 JSON 경로",
    )
    parser.add_argument(
        "--restaurant",
        required=True,
        help="식당 주소/좌표 JSON 경로",
    )
    parser.add_argument(
        "--out",
        default="outputs/problem3_nearest",
        help="결과 저장 폴더",
    )
    parser.add_argument(
        "--allow-geocode",
        action="store_true",
        help="restaurant JSON에 lat/lon이 없을 때 Nominatim으로 주소 좌표화",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()

    solve_nearest(
        matches_path=Path(args.matches),
        locations_path=Path(args.locations),
        restaurant_path=Path(args.restaurant),
        out_dir=Path(args.out),
        allow_geocode=args.allow_geocode,
    )


if __name__ == "__main__":
    main()