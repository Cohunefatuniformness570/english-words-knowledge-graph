"""Build prefix counts per year up to depth 6."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class Config:
    first_years_path: Path
    output_path: Path
    depth: int = 6
    start_year: int = 1800
    end_year: int = 2019


def load_first_years(path: Path) -> list[tuple[str, int]]:
    results: list[tuple[str, int]] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            word, year_str = line.rstrip("\n").split("\t")
            if not year_str:
                continue
            year = int(year_str)
            results.append((word, year))
    return results


def build_counts(
    data: list[tuple[str, int]], config: Config
) -> dict[tuple[str, int], dict[int, int]]:
    counts: dict[tuple[str, int], dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for word, year in data:
        if year < config.start_year or year > config.end_year:
            continue
        for depth in range(1, min(len(word), config.depth) + 1):
            prefix = word[:depth]
            counts[(prefix, depth)][year] += 1
    return counts


def cumulative_counts(
    counts: dict[tuple[str, int], dict[int, int]], config: Config
) -> dict[tuple[str, int, int], int]:
    cumulative: dict[tuple[str, int, int], int] = {}
    for (prefix, depth), year_counts in counts.items():
        total = 0
        for year in range(config.start_year, config.end_year + 1):
            total += year_counts.get(year, 0)
            cumulative[(prefix, depth, year)] = total
    return cumulative


def write_jsonl(data: dict[tuple[str, int, int], int], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for (prefix, depth, year), count in sorted(data.items()):
            obj = {
                "prefix": prefix,
                "depth": depth,
                "year": year,
                "cumulative_count": count,
            }
            handle.write(json.dumps(obj) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("first_years", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--depth", type=int, default=6)
    parser.add_argument("--start", type=int, default=1800)
    parser.add_argument("--end", type=int, default=2019)
    args = parser.parse_args()
    config = Config(
        first_years_path=args.first_years,
        output_path=args.output,
        depth=args.depth,
        start_year=args.start,
        end_year=args.end,
    )
    data = load_first_years(config.first_years_path)
    counts = build_counts(data, config)
    cumulative = cumulative_counts(counts, config)
    write_jsonl(cumulative, config.output_path)


if __name__ == "__main__":
    main()
