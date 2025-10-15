"""Compute deterministic layout for prefix trie nodes."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class Node:
    prefix: str
    depth: int
    weight: int
    children: list[str]


def load_weights(path: Path) -> dict[str, int]:
    weights: dict[str, int] = defaultdict(int)
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            prefix = record["prefix"]
            weights[prefix] = max(weights[prefix], record["cumulative_count"])
    return dict(weights)


def build_tree(weights: dict[str, int]) -> dict[str, Node]:
    nodes: dict[str, Node] = {}
    for prefix, weight in weights.items():
        depth = len(prefix)
        nodes[prefix] = Node(prefix=prefix, depth=depth, weight=weight, children=[])
    for prefix in list(nodes.keys()):
        if not prefix:
            continue
        parent = prefix[:-1]
        if parent in nodes:
            nodes[parent].children.append(prefix)
    return nodes


def assign_positions(
    nodes: dict[str, Node], vertical_spacing: float, total_width: float
) -> dict[str, tuple[float, float]]:
    positions: dict[str, tuple[float, float]] = {}

    def helper(prefix: str, x_min: float, x_max: float) -> None:
        node = nodes[prefix]
        x = (x_min + x_max) / 2
        y = node.depth * vertical_spacing
        positions[prefix] = (x, y)
        total = sum(nodes[child].weight for child in node.children)
        cursor = x_min
        for child in sorted(node.children):
            child_weight = nodes[child].weight
            span = (x_max - x_min) if total == 0 else (x_max - x_min) * (child_weight / total)
            child_max = cursor + span
            helper(child, cursor, child_max)
            cursor = child_max

    roots = [prefix for prefix, node in nodes.items() if node.depth == 1]
    segment_width = total_width / max(1, len(roots))
    for idx, prefix in enumerate(sorted(roots)):
        x_min = idx * segment_width
        x_max = (idx + 1) * segment_width
        helper(prefix, x_min, x_max)
    return positions


def write_positions(data: dict[str, tuple[float, float]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = {prefix: {"x": x, "y": y} for prefix, (x, y) in data.items()}
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(serialized, handle, indent=2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prefix_counts", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--vertical-spacing", type=float, default=1.0)
    parser.add_argument("--width", type=float, default=1000.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    weights = load_weights(args.prefix_counts)
    nodes = build_tree(weights)
    positions = assign_positions(nodes, args.vertical_spacing, args.width)
    write_positions(positions, args.output)


if __name__ == "__main__":
    main()
