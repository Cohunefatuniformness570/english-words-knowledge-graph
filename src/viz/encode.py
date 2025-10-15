"""Encode MP4 and GIF from rendered frames using ffmpeg."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def run_ffmpeg(args: list[str]) -> None:
    subprocess.run(args, check=True)


def encode_video(frames: Path, output: Path, fps: float) -> None:
    pattern = frames / "frame-%04d.png"
    run_ffmpeg([
        "ffmpeg",
        "-y",
        "-framerate",
        f"{fps:.3f}",
        "-i",
        str(pattern),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(output),
    ])


def encode_gif(video: Path, output: Path, fps: int, width: int) -> None:
    palette = output.with_suffix(".palette.png")
    run_ffmpeg([
        "ffmpeg",
        "-y",
        "-i",
        str(video),
        "-vf",
        f"fps={fps},scale={width}:-1:flags=lanczos,palettegen",
        str(palette),
    ])
    run_ffmpeg([
        "ffmpeg",
        "-y",
        "-i",
        str(video),
        "-i",
        str(palette),
        "-lavfi",
        f"fps={fps},scale={width}:-1:flags=lanczos[x];[x][1:v]paletteuse",
        str(output),
    ])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("frames", type=Path)
    parser.add_argument("mp4", type=Path)
    parser.add_argument("gif", type=Path)
    parser.add_argument("--fps", type=float, default=7.333)
    parser.add_argument("--gif-fps", type=int, default=12)
    parser.add_argument("--gif-width", type=int, default=1280)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    encode_video(args.frames, args.mp4, args.fps)
    encode_gif(args.mp4, args.gif, args.gif_fps, args.gif_width)


if __name__ == "__main__":
    main()
