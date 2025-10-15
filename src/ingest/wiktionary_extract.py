"""Extract English lemmas from a Wiktionary XML dump."""

from __future__ import annotations

import argparse
import bz2
import logging
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from lxml import etree


LOGGER = logging.getLogger(__name__)

TITLE_RE = re.compile(r"^[a-z]+$")


@dataclass(slots=True)
class Config:
    dump_path: Path
    output_path: Path


def iter_pages(dump_path: Path) -> Iterator[etree._Element]:
    if dump_path.suffix == ".bz2":
        opener = bz2.open
        mode = "rb"
    else:
        opener = open
        mode = "rb"
    with opener(dump_path, mode) as stream:
        context = etree.iterparse(stream, events=("end",), tag="{*}page")
        for _, elem in context:
            yield elem
            elem.clear()
            while elem.getprevious() is not None:
                del elem.getparent()[0]


def is_english_lemma(page: etree._Element) -> bool:
    title = page.findtext("{*}title") or ""
    lower = title.lower()
    if not TITLE_RE.match(lower):
        return False
    ns = page.findtext("{*}ns")
    if ns != "0":
        return False
    revision = page.find("{*}revision")
    if revision is None:
        return False
    text_elem = revision.find("{*}text")
    if text_elem is None or text_elem.text is None:
        return False
    if "==English==" not in text_elem.text:
        return False
    return True


def extract_lemmas(config: Config) -> None:
    config.output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config.output_path, "w", encoding="utf-8") as out_f:
        for page in iter_pages(config.dump_path):
            if is_english_lemma(page):
                title = page.findtext("{*}title")
                out_f.write(f"{title.lower()}\n")


def parse_args() -> Config:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dump", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()
    logging.basicConfig(level=args.log_level.upper())
    return Config(dump_path=args.dump, output_path=args.output)


def main() -> None:
    config = parse_args()
    LOGGER.info("Extracting lemmas from %s", config.dump_path)
    extract_lemmas(config)


if __name__ == "__main__":
    main()
