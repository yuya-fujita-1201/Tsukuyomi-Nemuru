#!/usr/bin/env python3
"""Build character-v8 vowel mouths without overwriting character-v7."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
CANVAS = (1086, 1448)
V7_ROOT = ROOT / "assets/character-v7"
V8_ROOT = ROOT / "assets/character-v8"
RAW_ROOT = V8_ROOT / "raw/imagegen"
WORK_ROOT = V8_ROOT / "work"
PARTS_ROOT = V8_ROOT / "parts/aligned-v1"
PREVIEWS_ROOT = V8_ROOT / "previews"
REVIEW_ROOT = ROOT / "output/review"
CHROMA_SCRIPT = (
    Path.home() / ".codex/skills/.system/imagegen/scripts/remove_chroma_key.py"
)

VOWEL_TARGETS = {
    "a": (510, 585, 576, 629),
    "i": (505, 594, 581, 618),
    "u": (521, 592, 565, 622),
    "e": (508, 590, 578, 623),
    "o": (518, 587, 568, 627),
}


def copy_file(source: Path, target: Path) -> None:
    if not source.exists():
        raise FileNotFoundError(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def copy_v7_assets() -> None:
    copy_file(
        V7_ROOT / "master/front-faceless-v1.png",
        V8_ROOT / "master/front-faceless-v1.png",
    )
    for folder in ("poses", "parts/aligned-v1", "guides"):
        source_root = V7_ROOT / folder
        target_root = V8_ROOT / folder
        for path in sorted(source_root.glob("*.png")):
            copy_file(path, target_root / path.name)
    for filename in ("live2d-neutral-v1.png", "gaze-range-v1.png"):
        copy_file(V7_ROOT / "previews" / filename, PREVIEWS_ROOT / filename)


def remove_chroma(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            sys.executable,
            str(CHROMA_SCRIPT),
            "--input",
            str(source),
            "--out",
            str(target),
            "--auto-key",
            "corners",
            "--soft-matte",
            "--transparent-threshold",
            "18",
            "--opaque-threshold",
            "86",
            "--edge-feather",
            "0.35",
            "--despill",
            "--force",
        ],
        check=True,
    )


def build_vowels() -> dict[str, Image.Image]:
    PARTS_ROOT.mkdir(parents=True, exist_ok=True)
    guide_root = V8_ROOT / "guides"
    guide_root.mkdir(parents=True, exist_ok=True)
    results: dict[str, Image.Image] = {}

    for vowel, target in VOWEL_TARGETS.items():
        alpha_path = WORK_ROOT / f"mouth-vowel-{vowel}-alpha-v1.png"
        remove_chroma(
            RAW_ROOT / f"mouth-vowel-{vowel}-chroma-v1.png",
            alpha_path,
        )
        source = Image.open(alpha_path).convert("RGBA")
        bbox = source.getchannel("A").point(
            lambda value: 255 if value > 20 else 0,
        ).getbbox()
        if bbox is None:
            raise ValueError(f"Missing generated vowel mouth: {vowel}")
        crop = source.crop(bbox)
        target_size = (target[2] - target[0], target[3] - target[1])
        crop = crop.resize(target_size, Image.Resampling.LANCZOS)
        aligned = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
        aligned.alpha_composite(crop, target[:2])
        output_path = PARTS_ROOT / f"mouth_vowel_{vowel}.png"
        aligned.save(output_path)

        guide = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
        guide.paste((255, 255, 255, 255), (0, 0), aligned.getchannel("A"))
        guide.save(guide_root / f"mouth_vowel_{vowel}-guide.png")

        if aligned.getchannel("A").getbbox() != target:
            raise AssertionError(f"Vowel {vowel} is not aligned to {target}")
        results[vowel] = aligned
    return results


def layer_spec(vowel: str, order: int, visible: bool = False) -> dict:
    return {
        "name": f"mouth_vowel_{vowel}",
        "file": f"parts/aligned-v1/mouth_vowel_{vowel}.png",
        "group": "30_mouth",
        "left": 0,
        "top": 0,
        "opacity": 255,
        "visible": visible,
        "order": order,
    }


def write_manifests() -> None:
    manifest = json.loads(
        (V7_ROOT / "manifest-live2d-poc-v1.json").read_text(encoding="utf-8")
    )
    for order, vowel in enumerate(VOWEL_TARGETS, start=33):
        manifest["layers"].append(layer_spec(vowel, order))
    manifest["notes"] = [
        "character-v8 preserves every approved character-v7 completed pose and tracking-eye layer.",
        "Five front-only, medium-open Japanese vowel mouth layers are added for manual review.",
        "Parameter review selects completed natural neck cuts and full 3/4 body cuts instead of deforming the front raster.",
        "Hair mesh correction is intentionally held because the flattened source has no hidden clothing or body underpaint.",
        "This PSD is layered animation material and has not been imported in Live2D Cubism.",
    ]
    (V8_ROOT / "manifest-live2d-poc-v1.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    for filename in (
        "manifest-state-blink-v1.json",
        "manifest-state-mouth-small-v1.json",
        "manifest-state-mouth-wide-v1.json",
    ):
        copy_file(V7_ROOT / filename, V8_ROOT / filename)

    base_layers = [
        layer for layer in manifest["layers"]
        if layer["name"] in {
            "front_faceless_base",
            "eye_base_open",
            "irises",
            "brows_neutral",
        }
    ]
    for order, vowel in enumerate(VOWEL_TARGETS, start=33):
        state = {
            "canvas": manifest["canvas"],
            "layers": [*base_layers, layer_spec(vowel, order, True)],
        }
        (V8_ROOT / f"manifest-state-mouth-vowel-{vowel}-v1.json").write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def composite_front(mouth: Image.Image) -> Image.Image:
    frame = Image.open(V8_ROOT / "master/front-faceless-v1.png").convert("RGBA")
    for name in ("eye_base_open", "irises", "brows_neutral"):
        frame.alpha_composite(
            Image.open(PARTS_ROOT / f"{name}.png").convert("RGBA")
        )
    frame.alpha_composite(mouth)
    return frame


def render_reviews(vowels: dict[str, Image.Image]) -> None:
    PREVIEWS_ROOT.mkdir(parents=True, exist_ok=True)
    REVIEW_ROOT.mkdir(parents=True, exist_ok=True)
    background = (15, 19, 40, 255)
    crop_box = (410, 500, 676, 690)
    tile_size = (266, 190)
    sheet = Image.new("RGBA", (tile_size[0] * 5, tile_size[1]), background)
    draw = ImageDraw.Draw(sheet)
    labels = {"a": "A / あ", "i": "I / い", "u": "U / う", "e": "E / え", "o": "O / お"}
    for index, (vowel, image) in enumerate(vowels.items()):
        frame = Image.new("RGBA", CANVAS, background)
        frame.alpha_composite(composite_front(image))
        sheet.alpha_composite(frame.crop(crop_box), (index * tile_size[0], 0))
        draw.text((index * tile_size[0] + 12, 10), labels[vowel], fill="white")
    preview_path = PREVIEWS_ROOT / "mouth-vowels-medium-v1.png"
    sheet.save(preview_path)
    copy_file(preview_path, REVIEW_ROOT / "tsukuyomi-v8-mouth-vowels-medium.png")


def main() -> None:
    copy_v7_assets()
    vowels = build_vowels()
    write_manifests()
    render_reviews(vowels)
    print(f"Built character-v8 assets under {V8_ROOT}")


if __name__ == "__main__":
    main()
