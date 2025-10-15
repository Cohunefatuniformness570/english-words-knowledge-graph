"""Infer first robust attestation year using Google 1-gram shards."""

from __future__ import annotations

import argparse
import csv
import gzip
import logging
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class Config:
    lemma_path: Path
    ngram_dir: Path
    output_path: Path
    tau: float = 1e-9
    window: int = 3
    guard: int = 3
    start_year: int = 1800
    end_year: int = 2019


def read_lemmas(path: Path) -> list[str]:
    with open(path, "r", encoding="utf-8") as handle:
        return [line.strip() for line in handle if line.strip()]


def moving_average(series: list[float], window: int) -> list[float]:
    radius = window // 2
    smoothed: list[float] = [0.0] * len(series)
    for idx, value in enumerate(series):
        total = value
        count = 1
        for offset in range(1, radius + 1):
            left = idx - offset
            right = idx + offset
            if left >= 0:
                total += series[left]
                count += 1
            if right < len(series):
                total += series[right]
                count += 1
        smoothed[idx] = total / count if count else 0.0
    return smoothed


def find_first_year(series: list[int], freqs: list[float], config: Config) -> int | None:
    smoothed = moving_average(freqs, config.window)
    guard_window = 5
    for idx, year in enumerate(series):
        if year < config.start_year:
            continue
        if smoothed[idx] < config.tau:
            continue
        non_zero = 0
        for ahead in range(idx, min(idx + guard_window, len(series))):
            if freqs[ahead] > 0:
                non_zero += 1
        if non_zero >= config.guard:
            return year
    return None


def lemma_variants(lemma: str) -> list[str]:
    variants = {lemma}
    variants.add(lemma.lower())
    variants.add(lemma.title())
    return list(variants)


def parse_ngram_rows(path: Path) -> Iterable[tuple[str, int, int, int]]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        reader = csv.reader(handle, delimiter="\t")
        for row in reader:
            if len(row) < 4:
                continue
            token = row[0]
            try:
                year = int(row[1])
                match_count = int(row[2])
                volume_count = int(row[3])
            except ValueError:
                continue
            yield token, year, match_count, volume_count


def collect_counts(lemmas: list[str], ngram_dir: Path) -> dict[str, dict[int, tuple[int, int]]]:
    targets = {lemma: {} for lemma in lemmas}
    alias: dict[str, str] = {}
    for lemma in lemmas:
        for variant in lemma_variants(lemma):
            alias[variant] = lemma
    shard_files = sorted(ngram_dir.glob("*.gz"))
    for shard_path in shard_files:
        LOGGER.info("Processing shard %s", shard_path.name)
        for token, year, match, volume in parse_ngram_rows(shard_path):
            key = alias.get(token)
            if key is None:
                key = alias.get(token.lower())
            if key is None:
                continue
            if volume == 0:
                continue
            bucket = targets[key]
            if year not in bucket:
                bucket[year] = (match, volume)
            else:
                prev_match, prev_volume = bucket[year]
                bucket[year] = (prev_match + match, prev_volume + volume)
    return targets


def compute_first_years(config: Config) -> None:
    lemmas = read_lemmas(config.lemma_path)
    counts = collect_counts(lemmas, config.ngram_dir)
    year_axis = list(range(config.start_year, config.end_year + 1))
    config.output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config.output_path, "w", encoding="utf-8") as out_f:
        for lemma in lemmas:
            bucket = counts.get(lemma, {})
            freq_series: list[float] = []
            for year in year_axis:
                match, volume = bucket.get(year, (0, 0))
                freq_series.append(match / volume if volume else 0.0)
            first_year = find_first_year(year_axis, freq_series, config)
            out_f.write(f"{lemma}\t{first_year or ''}\n")


def parse_args() -> Config:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lemmas", type=Path)
    parser.add_argument("ngrams", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--tau", type=float, default=1e-9)
    parser.add_argument("--window", type=int, default=3)
    parser.add_argument("--guard", type=int, default=3)
    parser.add_argument("--start-year", type=int, default=1800)
    parser.add_argument("--end-year", type=int, default=2019)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()
    logging.basicConfig(level=args.log_level.upper())
    return Config(
        lemma_path=args.lemmas,
        ngram_dir=args.ngrams,
        output_path=args.output,
        tau=args.tau,
        window=args.window,
        guard=args.guard,
        start_year=args.start_year,
        end_year=args.end_year,
    )


def main() -> None:
    config = parse_args()
    LOGGER.info("Computing first years for lemmas from %s", config.lemma_path)
    compute_first_years(config)


if __name__ == "__main__":
    main()
