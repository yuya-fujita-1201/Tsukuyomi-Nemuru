#!/usr/bin/env python3
"""Reopen the v12 PSD and verify its neutral composite and I-vowel layer."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageChops, ImageStat
from psd_tools import PSDImage


ROOT = Path(__file__).resolve().parents[1]
V12_ROOT = ROOT / "assets/character-v12"
PSD_PATH = V12_ROOT / "exports/tsukuyomi-nemuri-faceless-poc-v12.psd"
EXPECTED_PATH = V12_ROOT / "previews/live2d-neutral-v1.png"
I_MOUTH_PATH = V12_ROOT / "parts/aligned-v1/mouth_vowel_i.png"
OUTPUT_PATH = V12_ROOT / "previews/psd-reopen-composite-v1.png"
EXPECTED_I_BBOX = (517, 598, 569, 613)


def flatten_names(nodes) -> list[str]:
    names: list[str] = []
    for node in nodes:
        names.append(node.name)
        if node.is_group():
            names.extend(flatten_names(node))
    return names


def find_layer(nodes, name: str):
    for node in nodes:
        if node.name == name:
            return node
        if node.is_group():
            found = find_layer(node, name)
            if found is not None:
                return found
    return None


def alpha_bbox(image: Image.Image, threshold: int = 20):
    return image.convert("RGBA").getchannel("A").point(
        lambda value: 255 if value > threshold else 0
    ).getbbox()


def main() -> None:
    psd = PSDImage.open(PSD_PATH)
    composite = psd.composite().convert("RGBA")
    with Image.open(EXPECTED_PATH) as image:
        expected = image.convert("RGBA")
    with Image.open(I_MOUTH_PATH) as image:
        expected_i = image.convert("RGBA")
    i_bbox = alpha_bbox(expected_i)

    i_layer = find_layer(psd, "mouth_vowel_i")
    if i_layer is None:
        raise ValueError("PSD has no mouth_vowel_i layer")
    embedded_i = i_layer.topil().convert("RGBA")
    if i_layer.has_mask():
        embedded_i.putalpha(i_layer.mask.topil())
    embedded_i_bbox = alpha_bbox(embedded_i)
    embedded_i_difference = ImageChops.difference(embedded_i, expected_i)
    embedded_i_matches = embedded_i_difference.getbbox() is None

    if composite.size != expected.size:
        raise ValueError(f"Composite size mismatch: {composite.size} != {expected.size}")
    if i_bbox != EXPECTED_I_BBOX:
        raise ValueError(f"I-vowel bbox mismatch: {i_bbox} != {EXPECTED_I_BBOX}")
    if embedded_i_bbox != EXPECTED_I_BBOX:
        raise ValueError(
            f"Embedded I-vowel bbox mismatch: {embedded_i_bbox} != {EXPECTED_I_BBOX}"
        )
    if not embedded_i_matches:
        raise ValueError("PSD mouth_vowel_i pixels differ from the standalone PNG")

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
    layer_names = flatten_names(psd)
    result = {
        "psd": str(PSD_PATH.relative_to(ROOT)),
        "canvas": list(psd.size),
        "i_vowel_bbox": list(i_bbox),
        "embedded_i_vowel_bbox": list(embedded_i_bbox),
        "embedded_i_pixels_match_png": embedded_i_matches,
        "max_channel_difference": max_channel,
        "max_mean_channel_difference": round(mean_channel, 8),
        "pixels_above_25": pixels_above_25,
        "high_difference_ratio": round(high_difference_ratio, 8),
        "output": str(OUTPUT_PATH.relative_to(ROOT)),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    required = {
        "front_faceless_base",
        "eye_base_open",
        "irises",
        "eyes_closed",
        "brows_neutral",
        "mouth_closed",
        "mouth_open_micro",
        "mouth_open_small",
        "mouth_open_wide",
        "mouth_vowel_a",
        "mouth_vowel_i",
        "mouth_vowel_u",
        "mouth_vowel_e",
        "mouth_vowel_o",
    }
    if not required.issubset(set(layer_names)):
        raise SystemExit("PSD is missing one or more required v12 layers")
    if mean_channel > 0.2 or high_difference_ratio > 0.002:
        raise SystemExit("PSD visible composite does not match the neutral PNG preview")


if __name__ == "__main__":
    main()
