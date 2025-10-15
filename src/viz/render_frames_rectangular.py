"""Render PNG frames for the prefix trie timelapse."""

from __future__ import annotations

import argparse
import json
import math
import string
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def load_prefix_counts(path: Path) -> tuple[dict[int, dict[str, int]], dict[str, int], int]:
    timeline: dict[int, dict[str, int]] = {}
    max_prefix_counts: dict[str, int] = {}
    global_max = 0
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            year = record["year"]
            prefix = record["prefix"]
            count = record["cumulative_count"]
            timeline.setdefault(year, {})[prefix] = count
            existing = max_prefix_counts.get(prefix, 0)
            if count > existing:
                max_prefix_counts[prefix] = count
            if count > global_max:
                global_max = count
    return timeline, max_prefix_counts, global_max or 1


def load_positions(path: Path) -> dict[str, tuple[float, float]]:
    with open(path, "r", encoding="utf-8") as handle:
        raw = json.load(handle)
    return {prefix: (value["x"], value["y"]) for prefix, value in raw.items()}


def project_positions(
    positions: dict[str, tuple[float, float]],
    width: int,
    height: int,
    padding: int,
) -> dict[str, tuple[float, float]]:
    if not positions:
        return {}
    x_values = [point[0] for point in positions.values()]
    y_values = [point[1] for point in positions.values()]
    x_min = min(x_values)
    x_max = max(x_values)
    y_min = min(y_values)
    y_max = max(y_values)
    x_span = x_max - x_min if x_max > x_min else 1.0
    y_span = y_max - y_min if y_max > y_min else 1.0
    x_scale = (width - 2 * padding) / x_span
    y_scale = (height - 2 * padding) / y_span
    mapped: dict[str, tuple[float, float]] = {}
    for prefix, (x, y) in positions.items():
        scaled_x = padding + (x - x_min) * x_scale
        scaled_y = height - (padding + (y - y_min) * y_scale)
        mapped[prefix] = (scaled_x, scaled_y)
    return mapped


def build_parent_map(prefixes: set[str]) -> dict[str, str]:
    parents: dict[str, str] = {}
    for prefix in prefixes:
        if len(prefix) > 1:
            parent = prefix[:-1]
            parents[prefix] = parent
    return parents


def rects_intersect(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    return not (ax1 < bx0 or ax0 > bx1 or ay1 < by0 or ay0 > by1)


def select_labels_for_year(
    counts: dict[str, int],
    positions: dict[str, tuple[float, float]],
    font: ImageFont.ImageFont,
    limit: int,
    max_depth: int,
    min_spacing: int,
) -> list[tuple[str, int, int, int, str]]:
    candidates = [
        (prefix, value)
        for prefix, value in counts.items()
        if value > 0 and len(prefix) <= max_depth and prefix in positions
    ]
    candidates.sort(key=lambda pair: pair[1], reverse=True)
    selected: list[tuple[str, int, int, int, str]] = []
    boxes: list[tuple[int, int, int, int]] = []
    padding = 6
    for prefix, value in candidates:
        if len(selected) >= limit:
            break
        cx, cy = positions[prefix]
        text = f"{prefix} · {value:,}"
        try:
            bbox = font.getbbox(text)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
        except AttributeError:
            text_width, text_height = font.getsize(text)  # type: ignore[attr-defined]
        tx = int(cx + 10)
        ty = int(cy - text_height / 2)
        rect = (
            tx - padding - min_spacing,
            ty - padding - min_spacing,
            tx + text_width + padding + min_spacing,
            ty + text_height + padding + min_spacing,
        )
        if any(rects_intersect(rect, existing) for existing in boxes):
            continue
        boxes.append(rect)
        selected.append((prefix, value, tx, ty, text))
    return selected


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


def depth_palette() -> dict[int, tuple[int, int, int, int]]:
    return {
        1: (255, 207, 120, 220),
        2: (255, 168, 88, 220),
        3: (243, 112, 85, 220),
        4: (181, 90, 164, 220),
        5: (95, 132, 232, 220),
        6: (90, 196, 226, 220),
        "default": (160, 210, 250, 220),
    }


def draw_edges(
    draw: ImageDraw.ImageDraw,
    positions: dict[str, tuple[float, float]],
    counts: dict[str, int],
    parents: dict[str, str],
    palette: dict[int, tuple[int, int, int, int]],
    inactive_alpha: int,
) -> None:
    for prefix, child_pos in positions.items():
        parent = parents.get(prefix)
        if parent is None:
            continue
        parent_pos = positions.get(parent)
        if parent_pos is None:
            continue
        depth = len(prefix)
        color = palette.get(depth, palette["default"])
        active = counts.get(prefix, 0) > 0 or counts.get(parent, 0) > 0
        alpha = max(80, color[3] // 3) if active else inactive_alpha
        draw.line([parent_pos, child_pos], fill=(color[0], color[1], color[2], alpha), width=2)


def draw_labels(
    draw: ImageDraw.ImageDraw,
    labels: list[tuple[str, int, int, int, str]],
    font: ImageFont.ImageFont,
) -> None:
    for prefix, value, tx, ty, text in labels:
        bbox = draw.textbbox((tx, ty), text, font=font)
        background = [
            (bbox[0] - 4, bbox[1] - 2),
            (bbox[2] + 4, bbox[3] + 2),
        ]
        draw.rectangle(background, fill=(10, 10, 20, 200))
        draw.text((tx, ty), text, font=font, fill=(236, 241, 255, 255))


def draw_hud(
    draw: ImageDraw.ImageDraw,
    year: int,
    total_words: int,
    new_words: int,
    width: int,
    title_font: ImageFont.ImageFont,
    detail_font: ImageFont.ImageFont,
) -> None:
    title_text = str(year)
    title_pos = (60, 60)
    draw.text(title_pos, title_text, font=title_font, fill=(255, 255, 255, 255))
    details = [
        f"cumulative words: {total_words:,}",
        f"new words this year: {max(new_words, 0):,}",
    ]
    line_y = title_pos[1] + title_font.size + 20
    for line in details:
        draw.text((60, line_y), line, font=detail_font, fill=(210, 220, 235, 255))
        line_y += detail_font.size + 8


def render_frame(
    index: int,
    total_frames: int,
    year: int,
    counts: dict[str, int],
    positions: dict[str, tuple[float, float]],
    parents: dict[str, str],
    labels: list[tuple[str, int, int, int, str]],
    palette: dict[int, tuple[int, int, int, int]],
    output_path: Path,
    width: int,
    height: int,
    max_global_count: int,
    min_radius: float,
    max_radius: float,
    total_words: int,
    new_words: int,
    title_font: ImageFont.ImageFont,
    detail_font: ImageFont.ImageFont,
    growth_curve: float,
    inactive_alpha: int,
) -> None:
    image = Image.new("RGB", (width, height), color=(6, 9, 16))
    draw = ImageDraw.Draw(image, "RGBA")

    draw_edges(draw, positions, counts, parents, palette, inactive_alpha)

    eased = math.sin(growth_curve * math.pi / 2)
    current_max = max(counts.values()) if counts else 1
    normalized_max = max(current_max, max_global_count * eased)

    for prefix, (cx, cy) in positions.items():
        count = counts.get(prefix, 0)
        depth = len(prefix)
        color = palette.get(depth, palette["default"])
        if count > 0:
            normalized = math.sqrt(count / normalized_max) if normalized_max else 0.0
            radius = min_radius + (max_radius - min_radius) * normalized
        else:
            radius = min_radius * 0.6
        radius = max(min_radius * 0.6, radius)
        draw.ellipse(
            [
                (cx - radius, cy - radius),
                (cx + radius, cy + radius),
            ],
            fill=color if count > 0 else (32, 44, 62, 160),
            outline=(18, 22, 34, 255),
            width=1,
        )

    draw_labels(draw, labels, detail_font)
    draw_hud(draw, year, total_words, new_words, width, title_font, detail_font)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)


def timeline_totals(timeline: dict[int, dict[str, int]]) -> tuple[dict[int, int], dict[int, int]]:
    total_counts: dict[int, int] = {}
    new_counts: dict[int, int] = {}
    previous: dict[str, int] = {}
    for year in sorted(timeline.keys()):
        counts = timeline[year]
        total_counts[year] = sum(counts.values())
        new_words = 0
        for prefix, count in counts.items():
            prev = previous.get(prefix, 0)
            if count > prev:
                new_words += count - prev
            previous[prefix] = count
        new_counts[year] = new_words
    return total_counts, new_counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prefix_counts", type=Path)
    parser.add_argument("positions", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--padding", type=int, default=120)
    parser.add_argument("--min-radius", type=float, default=5.0)
    parser.add_argument("--max-radius", type=float, default=64.0)
    parser.add_argument("--label-limit", type=int, default=8)
    parser.add_argument("--label-depth", type=int, default=4)
    parser.add_argument("--label-spacing", type=int, default=20)
    parser.add_argument("--title-font-size", type=int, default=108)
    parser.add_argument("--detail-font-size", type=int, default=40)
    parser.add_argument("--inactive-edge-alpha", type=int, default=40)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    timeline, max_counts, max_global = load_prefix_counts(args.prefix_counts)
    positions = load_positions(args.positions)
    projected_positions = project_positions(positions, args.width, args.height, args.padding)
    parents = build_parent_map(set(positions.keys()))
    totals, new_counts = timeline_totals(timeline)
    palette = depth_palette()

    title_font = load_font(args.title_font_size)
    detail_font = load_font(args.detail_font_size)

    years = sorted(timeline.keys())
    total_frames = len(years)
    for index, year in enumerate(years):
        output_path = args.output / f"frame-{index:04d}.png"
        counts = timeline[year]
        labels = select_labels_for_year(
            counts,
            projected_positions,
            detail_font,
            args.label_limit,
            args.label_depth,
            args.label_spacing,
        )
        growth_curve = (index + 1) / total_frames
        render_frame(
            index,
            total_frames,
            year,
            counts,
            projected_positions,
            parents,
            labels,
            palette,
            output_path,
            args.width,
            args.height,
            max_global,
            args.min_radius,
            args.max_radius,
            totals.get(year, 0),
            new_counts.get(year, 0),
            title_font,
            detail_font,
            growth_curve,
            args.inactive_edge_alpha,
        )


if __name__ == "__main__":
    main()
