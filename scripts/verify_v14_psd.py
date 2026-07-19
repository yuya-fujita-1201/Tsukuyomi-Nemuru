#!/usr/bin/env python3
"""Reopen the v14 PSD and verify every current front raster layer."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageChops, ImageStat
from psd_tools import PSDImage


ROOT = Path(__file__).resolve().parents[1]
V14_ROOT = ROOT / "assets/character-v14"
PSD_PATH = V14_ROOT / "exports/tsukuyomi-nemuri-faceless-poc-v14.psd"
EXPECTED_PATH = V14_ROOT / "previews/live2d-manifest-preview-v14.png"
OUTPUT_PATH = V14_ROOT / "previews/psd-reopen-composite-v14.png"
CANVAS = (1086, 1448)
LAYER_FILES = {
    "front_faceless_base": "master/front-faceless-v1.png",
    "eye_base_open": "parts/aligned-v1/eye_base_open.png",
    "irises": "parts/aligned-v1/irises.png",
    "eyes_half_closed": "parts/aligned-v1/eyes_half_closed.png",
    "eyes_closed": "parts/aligned-v1/eyes_closed.png",
    "brows_neutral": "parts/aligned-v1/brows_neutral.png",
    "mouth_closed": "parts/aligned-v1/mouth_closed.png",
    "mouth_open_micro": "parts/aligned-v1/mouth_open_micro.png",
    "mouth_open_small": "parts/aligned-v1/mouth_open_small.png",
    "mouth_open_wide": "parts/aligned-v1/mouth_open_wide.png",
    "mouth_vowel_a": "parts/aligned-v1/mouth_vowel_a.png",
    "mouth_vowel_i": "parts/aligned-v1/mouth_vowel_i.png",
    "mouth_vowel_u": "parts/aligned-v1/mouth_vowel_u.png",
    "mouth_vowel_e": "parts/aligned-v1/mouth_vowel_e.png",
    "mouth_vowel_o": "parts/aligned-v1/mouth_vowel_o.png",
}


def find_layer(nodes, name: str):
    for node in nodes:
        if node.name == name:
            return node
        if node.is_group():
            found = find_layer(node, name)
            if found is not None:
                return found
    return None


def layer_canvas(layer) -> Image.Image:
    image = layer.topil().convert("RGBA")
    if layer.has_mask():
        image.putalpha(layer.mask.topil())
    if image.size == CANVAS and layer.left == 0 and layer.top == 0:
        return image
    canvas = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    canvas.alpha_composite(image, (layer.left, layer.top))
    return canvas


def main() -> None:
    psd = PSDImage.open(PSD_PATH)
    if psd.size != CANVAS:
        raise ValueError(f"PSD canvas mismatch: {psd.size} != {CANVAS}")

    embedded_matches = {}
    for name, relative_path in LAYER_FILES.items():
        layer = find_layer(psd, name)
        if layer is None:
            raise ValueError(f"PSD is missing layer: {name}")
        embedded = layer_canvas(layer)
        expected = Image.open(V14_ROOT / relative_path).convert("RGBA")
        difference = ImageChops.difference(embedded, expected)
        embedded_matches[name] = difference.getbbox() is None
        if not embedded_matches[name]:
            raise ValueError(f"PSD layer differs from standalone PNG: {name}")

    composite = psd.composite().convert("RGBA")
    expected_composite = Image.open(EXPECTED_PATH).convert("RGBA")
    if composite.size != expected_composite.size:
        raise ValueError("PSD neutral composite size changed")
    matte = Image.new("RGBA", CANVAS, (0, 0, 0, 255))
    actual_rgb = Image.alpha_composite(matte, composite).convert("RGB")
    expected_rgb = Image.alpha_composite(matte, expected_composite).convert("RGB")
    difference = ImageChops.difference(actual_rgb, expected_rgb)
    stats = ImageStat.Stat(difference)
    mean_channel = max(stats.mean)
    pixels_above_25 = sum(
        1 for pixel in difference.get_flattened_data() if max(pixel) > 25
    )
    high_difference_ratio = pixels_above_25 / (CANVAS[0] * CANVAS[1])
    if mean_channel > 0.2 or high_difference_ratio > 0.002:
        raise ValueError(
            "PSD neutral composite differs from manifest preview: "
            f"mean={mean_channel:.6f}, high-ratio={high_difference_ratio:.6f}"
        )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    composite.save(OUTPUT_PATH)
    print(
        json.dumps(
            {
                "psd": str(PSD_PATH.relative_to(ROOT)),
                "canvas": list(psd.size),
                "layer_count": len(LAYER_FILES),
                "embedded_png_matches": embedded_matches,
                "max_mean_channel_difference": round(mean_channel, 8),
                "high_difference_ratio": round(high_difference_ratio, 8),
                "output": str(OUTPUT_PATH.relative_to(ROOT)),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
