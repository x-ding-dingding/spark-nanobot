"""Sprite-sheet utilities for desktop pet state assets."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

from PIL import Image


STATE_ORDER = ("idle", "working", "warning", "dragging")
STATE_BOXES = {
    "idle": (0, 0, 1, 1),
    "working": (1, 0, 2, 1),
    "warning": (0, 1, 1, 2),
    "dragging": (1, 1, 2, 2),
}


def _quadrant_box(width: int, height: int, state: str) -> tuple[int, int, int, int]:
    col_start, row_start, col_end, row_end = STATE_BOXES[state]
    half_width = width // 2
    half_height = height // 2
    return (
        col_start * half_width,
        row_start * half_height,
        col_end * half_width,
        row_end * half_height,
    )


def _make_background_transparent(image: Image.Image, threshold: int) -> Image.Image:
    rgba = image.convert("RGBA")
    pixels = []
    for red, green, blue, alpha in rgba.getdata():
        if red >= threshold and green >= threshold and blue >= threshold:
            pixels.append((red, green, blue, 0))
        else:
            pixels.append((red, green, blue, alpha))
    rgba.putdata(pixels)
    return rgba


def _trim_to_content(image: Image.Image, padding: int) -> Image.Image:
    alpha = image.getchannel("A")
    bbox = alpha.getbbox()
    if bbox is None:
        return image

    left, top, right, bottom = bbox
    left = max(0, left - padding)
    top = max(0, top - padding)
    right = min(image.width, right + padding)
    bottom = min(image.height, bottom + padding)
    return image.crop((left, top, right, bottom))


def _pad_square(image: Image.Image) -> Image.Image:
    size = max(image.width, image.height)
    square = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    square.paste(image, ((size - image.width) // 2, (size - image.height) // 2))
    return square


def _prepare_state_image(
    image: Image.Image,
    *,
    trim: bool,
    transparent_background: bool,
    background_threshold: int,
    padding: int,
    output_size: int | None,
) -> Image.Image:
    prepared = image.convert("RGBA")
    if transparent_background:
        prepared = _make_background_transparent(prepared, background_threshold)
    if trim:
        prepared = _trim_to_content(prepared, padding)
        prepared = _pad_square(prepared)
    if output_size is not None and prepared.size != (output_size, output_size):
        prepared = prepared.resize((output_size, output_size), Image.Resampling.LANCZOS)
    return prepared


def split_pet_sprite(
    source: str | Path,
    output_dir: str | Path,
    *,
    prefix: str = "spark",
    trim: bool = True,
    transparent_background: bool = True,
    background_threshold: int = 248,
    padding: int = 18,
    output_size: int | None = 512,
    states: Iterable[str] = STATE_ORDER,
) -> list[Path]:
    """Split a 2x2 pet sprite sheet into named state assets."""
    source_path = Path(source)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    sheet = Image.open(source_path).convert("RGBA")
    written: list[Path] = []
    for state in states:
        if state not in STATE_BOXES:
            raise ValueError(f"Unknown pet state: {state}")

        crop = sheet.crop(_quadrant_box(sheet.width, sheet.height, state))
        prepared = _prepare_state_image(
            crop,
            trim=trim,
            transparent_background=transparent_background,
            background_threshold=background_threshold,
            padding=padding,
            output_size=output_size,
        )
        target = output_path / f"{prefix}-{state}.png"
        prepared.save(target)
        written.append(target)

    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Split a 2x2 desktop pet sprite sheet into state PNG assets."
    )
    parser.add_argument("source", type=Path, help="Input 2x2 sprite sheet")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("nanobot/pet/web/assets"),
        help="Output asset directory",
    )
    parser.add_argument("--prefix", default="spark", help="Output filename prefix")
    parser.add_argument("--padding", type=int, default=18, help="Trim padding in pixels")
    parser.add_argument(
        "--output-size",
        type=int,
        default=512,
        help="Final square PNG size. Use 0 to keep natural size.",
    )
    parser.add_argument(
        "--background-threshold",
        type=int,
        default=248,
        help="RGB threshold for white background removal",
    )
    parser.add_argument("--no-trim", action="store_true", help="Keep full quadrants")
    parser.add_argument(
        "--keep-background",
        action="store_true",
        help="Keep white background instead of making it transparent",
    )
    args = parser.parse_args(argv)

    output_size = args.output_size if args.output_size > 0 else None
    written = split_pet_sprite(
        args.source,
        args.out,
        prefix=args.prefix,
        trim=not args.no_trim,
        transparent_background=not args.keep_background,
        background_threshold=args.background_threshold,
        padding=args.padding,
        output_size=output_size,
    )

    for path in written:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
