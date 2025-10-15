"""Render PNG frames for the prefix trie timelapse with radial growth."""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def load_prefix_counts(path: Path) -> tuple[dict[int, dict[str, int]], int]:
    timeline: dict[int, dict[str, int]] = {}
    global_max = 0
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            year = record["year"]
            prefix = record["prefix"]
            count = record["cumulative_count"]
            timeline.setdefault(year, {})[prefix] = count
            if count > global_max:
                global_max = count
    return timeline, global_max or 1


def collect_prefixes(timeline: dict[int, dict[str, int]]) -> set[str]:
    prefixes: set[str] = set()
    for year_counts in timeline.values():
        for prefix in year_counts.keys():
            for depth in range(1, len(prefix) + 1):
                prefixes.add(prefix[:depth])
    return prefixes


def build_tree(prefixes: set[str]) -> tuple[dict[str, list[str]], dict[str, str]]:
    children: dict[str, list[str]] = defaultdict(list)
    parent: dict[str, str] = {}
    for prefix in sorted(prefixes):
        if not prefix:
            continue
        if len(prefix) == 1:
            children[""] .append(prefix)
            parent[prefix] = ""
        else:
            ancestor = prefix[:-1]
            children[ancestor].append(prefix)
            parent[prefix] = ancestor
    for child_list in children.values():
        child_list.sort()
    return children, parent


def prefix_fraction(prefix: str) -> float:
    fraction = 0.0
    for index, ch in enumerate(prefix):
        offset = ord(ch) - 97
        if offset < 0:
            offset = 0
        fraction += offset / (26 ** (index + 1))
    return fraction + 0.5 / (26 ** max(len(prefix), 1))


def generate_layout(children: dict[str, list[str]]) -> dict[str, tuple[float, float]]:
    positions: dict[str, tuple[float, float]] = {}

    def recurse(prefix: str, angle_start: float, angle_end: float, depth: int) -> None:
        descendants = children.get(prefix, [])
        if not descendants:
            return
        span = angle_end - angle_start
        count = len(descendants)
        for index, child in enumerate(descendants):
            local_start = angle_start + span * index / count
            local_end = angle_start + span * (index + 1) / count
            center_angle = (local_start + local_end) / 2
            radius = depth
            x = radius * math.cos(center_angle)
            y = radius * math.sin(center_angle)
            positions[child] = (x, y)
            recurse(child, local_start, local_end, depth + 1)

    recurse("", 0.0, 2 * math.pi, 1)
    return positions


def scale_positions(
    positions: dict[str, tuple[float, float]],
    width: int,
    height: int,
    progress: float,
) -> dict[str, tuple[float, float]]:
    if not positions:
        return {}
    max_radius = max(math.hypot(x, y) for x, y in positions.values())
    if max_radius == 0:
        max_radius = 1.0
    canvas_scale = min(width, height) / 2
    eased = math.sin(progress * math.pi / 2)
    growth_scale = (0.25 + 0.75 * eased) * (canvas_scale / max_radius) * 0.95
    cx = width / 2
    cy = height / 2
    scaled: dict[str, tuple[float, float]] = {}
    for prefix, (x, y) in positions.items():
        sx = cx + x * growth_scale
        sy = cy + y * growth_scale
        scaled[prefix] = (sx, sy)
    return scaled


def depth_palette() -> dict[int, tuple[int, int, int, int]]:
    return {
        1: (255, 204, 92, 240),
        2: (255, 163, 84, 220),
        3: (244, 121, 97, 200),
        4: (188, 94, 171, 190),
        5: (108, 138, 232, 180),
        6: (96, 198, 233, 170),
        "default": (170, 215, 255, 160),
    }


def draw_edges(
    draw: ImageDraw.ImageDraw,
    positions: dict[str, tuple[float, float]],
    counts: dict[str, int],
    parents: dict[str, str],
    palette: dict[int, tuple[int, int, int, int]],
    global_max: int,
    base_alpha: int,
    max_depth: int,
) -> None:
    for prefix in sorted(positions.keys(), key=len, reverse=True):
        parent = parents.get(prefix)
        if parent is None:
            continue
        parent_pos = positions.get(parent)
        child_pos = positions.get(prefix)
        if parent_pos is None or child_pos is None:
            continue
        depth = len(prefix)
        if depth > max_depth:
            continue
        color = palette.get(depth, palette["default"])
        ratio = math.sqrt(counts.get(prefix, 0) / global_max) if global_max else 0.0
        alpha = min(140, base_alpha + int(140 * ratio))
        line_color = (color[0], color[1], color[2], alpha)
        width = 2 if depth <= 2 else 1
        draw.line([parent_pos, child_pos], fill=line_color, width=width)


def draw_nodes(
    draw: ImageDraw.ImageDraw,
    positions: dict[str, tuple[float, float]],
    counts: dict[str, int],
    palette: dict[int, tuple[int, int, int, int]],
    global_max: int,
    min_radius: float,
    max_radius: float,
) -> dict[str, float]:
    radii: dict[str, float] = {}
    for prefix in sorted(positions.keys(), key=len):
        count = counts.get(prefix, 0)
        depth = len(prefix)
        color = palette.get(depth, palette["default"])
        if count > 0 and global_max:
            normalized = math.sqrt(count / global_max)
        else:
            normalized = 0.0
        depth_factor = 1.0 / (1.2 ** (depth - 1))
        base_radius = min_radius + (max_radius - min_radius) * normalized
        radius = max(min_radius * 0.25, base_radius * depth_factor)
        if count <= 0 and depth > 1:
            radius = min_radius * 0.2
        radii[prefix] = radius
        fill_alpha = color[3] if count > 0 else int(color[3] * 0.4)
        fill_color = (color[0], color[1], color[2], fill_alpha)
        cx, cy = positions[prefix]
        draw.ellipse(
            [
                (cx - radius, cy - radius),
                (cx + radius, cy + radius),
            ],
            fill=fill_color,
            outline=(24, 28, 40, 180),
            width=max(1, int(3 / depth)) if depth > 0 else 1,
        )
    return radii


def select_letter_labels(
    positions: dict[str, tuple[float, float]],
    radii: dict[str, float],
    counts: dict[str, int],
    font: ImageFont.ImageFont,
    width: int,
    height: int,
    padding: int = 12,
) -> list[tuple[str, float, float, str]]:
    labels: list[tuple[str, float, float, str]] = []
    occupied: list[tuple[float, float, float, float]] = []
    cx = width / 2
    cy = height / 2
    base_prefixes = sorted(prefix for prefix in positions if len(prefix) == 1)
    for prefix in base_prefixes:
        count = counts.get(prefix, 0)
        px, py = positions[prefix]
        radius = radii.get(prefix, 0.0)
        angle = math.atan2(py - cy, px - cx)
        label = f"{prefix} · {count:,}"
        try:
            bbox = font.getbbox(label)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
        except AttributeError:
            text_width, text_height = font.getsize(label)  # type: ignore[attr-defined]
        offset = max(radius + 20, 80)
        tx = px + math.cos(angle) * offset - text_width / 2
        ty = py + math.sin(angle) * offset - text_height / 2
        rect = (tx - padding, ty - padding, tx + text_width + padding, ty + text_height + padding)
        if any(
            not (rect[2] < other[0] or rect[0] > other[2] or rect[3] < other[1] or rect[1] > other[3])
            for other in occupied
        ):
            continue
        occupied.append(rect)
        labels.append((tx, ty, label))
    return labels


def draw_letter_labels(
    draw: ImageDraw.ImageDraw,
    labels: list[tuple[str, float, float, str]],
    font: ImageFont.ImageFont,
) -> None:
    for tx, ty, text in labels:
        try:
            bbox = draw.textbbox((tx, ty), text, font=font)
        except TypeError:
            width, height = font.getsize(text)  # type: ignore[attr-defined]
            bbox = (tx, ty, tx + width, ty + height)
        background = [
            (bbox[0] - 8, bbox[1] - 4),
            (bbox[2] + 8, bbox[3] + 4),
        ]
        draw.rectangle(background, fill=(18, 22, 34, 200))
        draw.text((tx, ty), text, font=font, fill=(236, 241, 255, 255))


def draw_hud(
    draw: ImageDraw.ImageDraw,
    year: int,
    total_words: int,
    new_words: int,
    title_font: ImageFont.ImageFont,
    detail_font: ImageFont.ImageFont,
) -> None:
    draw.text((60, 70), str(year), font=title_font, fill=(255, 255, 255, 255))
    detail_lines = [
        f"cumulative words: {total_words:,}",
        f"new words this year: {max(new_words, 0):,}",
    ]
    baseline = 70 + title_font.size + 18
    for line in detail_lines:
        draw.text((60, baseline), line, font=detail_font, fill=(210, 220, 235, 255))
        baseline += detail_font.size + 10


def load_font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except OSError:
        try:
            return ImageFont.truetype("Arial.ttf", size)
        except OSError:
            fallback = ImageFont.load_default()
            try:
                return fallback.font_variant(size=size)
            except AttributeError:
                return fallback


def timeline_totals(timeline: dict[int, dict[str, int]]) -> tuple[dict[int, int], dict[int, int]]:
    totals: dict[int, int] = {}
    new_words: dict[int, int] = {}
    previous_prefix_counts: dict[str, int] = {}
    for year in sorted(timeline.keys()):
        counts = timeline[year]
        totals[year] = sum(counts.values())
        yearly_new = 0
        for prefix, count in counts.items():
            prev = previous_prefix_counts.get(prefix, 0)
            if count > prev:
                yearly_new += count - prev
            previous_prefix_counts[prefix] = count
        new_words[year] = yearly_new
    return totals, new_words


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prefix_counts", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--min-radius", type=float, default=10.0)
    parser.add_argument("--max-radius", type=float, default=120.0)
    parser.add_argument("--title-font-size", type=int, default=112)
    parser.add_argument("--detail-font-size", type=int, default=42)
    parser.add_argument("--base-edge-alpha", type=int, default=25)
    parser.add_argument("--edge-depth", type=int, default=6)
    parser.add_argument("--start-progress", type=float, default=0.25)
    parser.add_argument("--end-progress", type=float, default=1.0)
    return parser.parse_args()


def render_frame(
    index: int,
    total_frames: int,
    year: int,
    counts: dict[str, int],
    scaled_positions: dict[str, tuple[float, float]],
    parents: dict[str, str],
    palette: dict[int, tuple[int, int, int, int]],
    output_path: Path,
    width: int,
    height: int,
    max_global_count: int,
    min_radius: float,
    max_radius: float,
    totals: dict[int, int],
    new_words: dict[int, int],
    title_font: ImageFont.ImageFont,
    detail_font: ImageFont.ImageFont,
    base_edge_alpha: int,
    edge_depth: int,
) -> None:
    image = Image.new("RGB", (width, height), color=(6, 9, 16))
    draw = ImageDraw.Draw(image, "RGBA")

    draw_edges(
        draw,
        scaled_positions,
        counts,
        parents,
        palette,
        max_global_count,
        base_edge_alpha,
        edge_depth,
    )
    radii = draw_nodes(
        draw,
        scaled_positions,
        counts,
        palette,
        max_global_count,
        min_radius,
        max_radius,
    )
    labels = select_letter_labels(scaled_positions, radii, counts, detail_font, width, height)
    draw_letter_labels(draw, labels, detail_font)
    draw_hud(draw, year, totals.get(year, 0), new_words.get(year, 0), title_font, detail_font)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)


def main() -> None:
    args = parse_args()
    timeline, global_max = load_prefix_counts(args.prefix_counts)
    prefixes = collect_prefixes(timeline)
    children, parents = build_tree(prefixes)
    layout_positions = generate_layout(children)
    palette = depth_palette()
    totals, new_counts = timeline_totals(timeline)

    title_font = load_font(args.title_font_size)
    detail_font = load_font(args.detail_font_size)

    years = sorted(timeline.keys())
    total_frames = len(years)
    for index, year in enumerate(years):
        if total_frames:
            t = (index + 1) / total_frames
        else:
            t = 1.0
        progress = args.start_progress + (args.end_progress - args.start_progress) * t
        progress = max(0.0, min(1.2, progress))
        scaled_positions = scale_positions(layout_positions, args.width, args.height, progress)
        frame_path = args.output / f"frame-{index:04d}.png"
        counts = timeline[year]
        render_frame(
            index,
            total_frames,
            year,
            counts,
            scaled_positions,
            parents,
            palette,
            frame_path,
            args.width,
            args.height,
            global_max,
            args.min_radius,
            args.max_radius,
            totals,
            new_counts,
            title_font,
            detail_font,
            args.base_edge_alpha,
            args.edge_depth,
        )


if __name__ == "__main__":
    main()
