#!/usr/bin/env python3
"""Reopen the character-v5 PSD and compare its visible composite to PNG."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageChops, ImageStat
from psd_tools import PSDImage


ROOT = Path(__file__).resolve().parents[1]
PSD_PATH = ROOT / "assets/character-v5/exports/tsukuyomi-nemuri-faceless-poc-v5.psd"
EXPECTED_PATH = ROOT / "assets/character-v5/previews/live2d-neutral-v1.png"
OUTPUT_PATH = ROOT / "assets/character-v5/previews/psd-reopen-composite-v1.png"


def flatten_names(nodes) -> list[str]:
    names: list[str] = []
    for node in nodes:
        names.append(node.name)
        if node.is_group():
            names.extend(flatten_names(node))
    return names


def main() -> None:
    psd = PSDImage.open(PSD_PATH)
    composite = psd.composite().convert("RGBA")
    with Image.open(EXPECTED_PATH) as image:
        expected = image.convert("RGBA")

    if composite.size != expected.size:
        raise ValueError(f"Composite size mismatch: {composite.size} != {expected.size}")

    # psd-tools returns the PSD canvas flattened against black, while the PNG
    # preview keeps transparent pixels.  Compare the same visible RGB result by
    # flattening the expected PNG against black as well.
    matte = Image.new("RGBA", composite.size, (0, 0, 0, 255))
    composite_matted = composite.convert("RGB")
    expected_matted = Image.alpha_composite(matte, expected).convert("RGB")
    difference = ImageChops.difference(composite_matted, expected_matted)
    stats = ImageStat.Stat(difference)
    max_channel = max(channel_range[1] for channel_range in difference.getextrema())
    mean_channel = max(stats.mean)
    pixels_above_25 = sum(
        1 for pixel in difference.get_flattened_data() if max(pixel) > 25
    )
    high_difference_ratio = pixels_above_25 / (difference.width * difference.height)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    composite.save(OUTPUT_PATH)

    result = {
        "psd": str(PSD_PATH.relative_to(ROOT)),
        "canvas": list(psd.size),
        "layer_names": flatten_names(psd),
        "max_channel_difference": max_channel,
        "max_mean_channel_difference": round(mean_channel, 8),
        "pixels_above_25": pixels_above_25,
        "high_difference_ratio": round(high_difference_ratio, 8),
        "output": str(OUTPUT_PATH.relative_to(ROOT)),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if mean_channel > 0.2 or high_difference_ratio > 0.002:
        raise SystemExit("PSD visible composite does not match the neutral PNG preview")


if __name__ == "__main__":
    main()
