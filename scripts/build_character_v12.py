#!/usr/bin/env python3
"""Build character-v12 with the user-reference I-vowel mouth artwork."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

import build_character_v10 as v10


ROOT = Path(__file__).resolve().parents[1]
CANVAS = v10.CANVAS
V11_ROOT = ROOT / "assets/character-v11"
V12_ROOT = ROOT / "assets/character-v12"
RAW_ROOT = V12_ROOT / "raw/imagegen"
WORK_ROOT = V12_ROOT / "work"
PARTS_ROOT = V12_ROOT / "parts/aligned-v1"
GUIDES_ROOT = V12_ROOT / "guides"
PREVIEWS_ROOT = V12_ROOT / "previews"

RAW_I_PATH = RAW_ROOT / "mouth-vowel-i-user-reference-chroma-v1.png"
MOUTH_I_TARGET = (517, 598, 569, 613)
BACKGROUND = (15, 19, 40, 255)
MOUTH_CROP = (410, 500, 676, 690)


def copy_v11_assets() -> None:
    """Copy v11 into v12 without changing or deleting the v11 source tree."""
    if not V11_ROOT.exists():
        raise FileNotFoundError(V11_ROOT)
    V12_ROOT.mkdir(parents=True, exist_ok=True)
    for path in sorted(V11_ROOT.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(V11_ROOT)
        # The v11 folder carries the inherited v10 PSD. v12 receives a newly
        # assembled export instead of copying that misleading filename.
        if relative.parts[0] == "exports":
            continue
        destination = V12_ROOT / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)


def soften_white_highlights(crop: Image.Image) -> Image.Image:
    """Keep the mouth pink while preventing any highlight from reading as teeth."""
    rgba = np.array(crop.convert("RGBA"))
    rgb = rgba[..., :3]
    alpha = rgba[..., 3]
    near_white = (
        (rgb[..., 0] > 222)
        & (rgb[..., 1] > 208)
        & (rgb[..., 2] > 208)
        & (alpha > 20)
    )
    rgba[near_white, 0] = 244
    rgba[near_white, 1] = 184
    rgba[near_white, 2] = 199
    return Image.fromarray(rgba, "RGBA")


def save_guide(layer: Image.Image, name: str) -> None:
    guide = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    guide.paste((255, 255, 255, 255), (0, 0), layer.getchannel("A"))
    guide.save(GUIDES_ROOT / f"{name}-guide.png")


def build_i_mouth() -> Image.Image:
    if not RAW_I_PATH.exists():
        raise FileNotFoundError(
            f"Missing generated I-vowel source: {RAW_I_PATH}"
        )
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    alpha_path = WORK_ROOT / "mouth-vowel-i-user-reference-alpha-v1.png"
    v10.remove_chroma(RAW_I_PATH, alpha_path)

    with Image.open(alpha_path) as image:
        source = image.convert("RGBA")
    source_bbox = v10.alpha_bbox(source)
    crop = soften_white_highlights(source.crop(source_bbox))
    aligned = v10.full_canvas_part(crop, MOUTH_I_TARGET)

    PARTS_ROOT.mkdir(parents=True, exist_ok=True)
    GUIDES_ROOT.mkdir(parents=True, exist_ok=True)
    aligned.save(PARTS_ROOT / "mouth_vowel_i.png")
    save_guide(aligned, "mouth_vowel_i")
    return aligned


def update_manifests() -> None:
    path = V12_ROOT / "manifest-live2d-poc-v1.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["notes"] = [
        "character-v12 preserves the v11 motion atlases, approved side poses, and all non-I front artwork.",
        "The I vowel was rebuilt from the supplied three-mouth visual reference and its chroma-key source is archived under raw/imagegen.",
        "The I keyform is a centered 52x15 shallow pink opening with no broad white teeth plane or individual tooth shapes.",
        "The I layer remains hidden in the neutral stack and becomes visible only when that mouth key is selected.",
        "Head and body motion assets remain the sixteen-key cached raster sequences introduced in character-v11.",
        "The v12 PSD can be assembled from this manifest with the updated I layer.",
        "This material has not been imported into Live2D Cubism and contains no Cubism ArtMeshes or deformers.",
    ]
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    base_names = {
        "front_faceless_base",
        "eye_base_open",
        "irises",
        "brows_neutral",
    }
    base_layers = [
        layer for layer in manifest["layers"] if layer["name"] in base_names
    ]
    i_layer = next(
        layer for layer in manifest["layers"] if layer["name"] == "mouth_vowel_i"
    )
    state = {
        "canvas": manifest["canvas"],
        "layers": [*base_layers, {**i_layer, "visible": True}],
    }
    (V12_ROOT / "manifest-state-mouth-vowel-i-v1.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def composite_front(mouth: Image.Image, *, root: Path = V12_ROOT) -> Image.Image:
    frame = Image.open(root / "master/front-faceless-v1.png").convert("RGBA")
    parts_root = root / "parts/aligned-v1"
    for name in ("eye_base_open", "irises", "brows_neutral"):
        with Image.open(parts_root / f"{name}.png") as layer:
            frame.alpha_composite(layer.convert("RGBA"))
    frame.alpha_composite(mouth)
    return frame


def on_background(frame: Image.Image) -> Image.Image:
    background = Image.new("RGBA", CANVAS, BACKGROUND)
    background.alpha_composite(frame)
    return background


def render_labeled_sheet(
    items: list[tuple[str, Image.Image]],
    path: Path,
) -> None:
    tile_size = (MOUTH_CROP[2] - MOUTH_CROP[0], MOUTH_CROP[3] - MOUTH_CROP[1])
    sheet = Image.new(
        "RGBA",
        (tile_size[0] * len(items), tile_size[1]),
        BACKGROUND,
    )
    draw = ImageDraw.Draw(sheet)
    for index, (label, mouth) in enumerate(items):
        frame = on_background(composite_front(mouth)).crop(MOUTH_CROP)
        sheet.alpha_composite(frame, (index * tile_size[0], 0))
        draw.text((index * tile_size[0] + 12, 10), label, fill="white")
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path)


def render_reviews(i_mouth: Image.Image) -> None:
    PREVIEWS_ROOT.mkdir(parents=True, exist_ok=True)

    with Image.open(V11_ROOT / "parts/aligned-v1/mouth_vowel_i.png") as image:
        old_i = image.convert("RGBA")
    comparison_path = PREVIEWS_ROOT / "mouth-i-user-reference-v11-v12.png"
    render_labeled_sheet(
        [
            ("v11 I / before", old_i),
            ("v12 I / user reference", i_mouth),
        ],
        comparison_path,
    )
    shutil.copy2(comparison_path, PREVIEWS_ROOT / "mouth-i-before-after-v1.png")

    vowels = []
    labels = {
        "a": "A / あ",
        "i": "I / い / new",
        "u": "U / う",
        "e": "E / え",
        "o": "O / お",
    }
    for vowel in ("a", "i", "u", "e", "o"):
        mouth = i_mouth
        if vowel != "i":
            mouth = Image.open(PARTS_ROOT / f"mouth_vowel_{vowel}.png").convert(
                "RGBA"
            )
        vowels.append((labels[vowel], mouth))
    render_labeled_sheet(
        vowels,
        PREVIEWS_ROOT / "mouth-vowels-medium-v1.png",
    )

    mouth_keys = []
    for label, filename in (
        ("closed", "mouth_closed.png"),
        ("micro", "mouth_open_micro.png"),
        ("small", "mouth_open_small.png"),
    ):
        mouth_keys.append(
            (label, Image.open(PARTS_ROOT / filename).convert("RGBA"))
        )
    mouth_keys.append(("I / い / new", i_mouth))
    render_labeled_sheet(
        mouth_keys,
        PREVIEWS_ROOT / "mouth-closed-micro-small-i-v1.png",
    )

    full = on_background(composite_front(i_mouth))
    full.save(PREVIEWS_ROOT / "live2d-vowel-i-v1.png")


def mouth_stats(i_mouth: Image.Image) -> dict[str, object]:
    rgba = np.asarray(i_mouth.convert("RGBA"))
    alpha = rgba[..., 3]
    visible = alpha > 20
    near_white = (
        (rgba[..., 0] > 222)
        & (rgba[..., 1] > 208)
        & (rgba[..., 2] > 208)
        & visible
    )
    green_dominant = (
        (rgba[..., 1].astype(np.int16) > rgba[..., 0].astype(np.int16) + 30)
        & (rgba[..., 1].astype(np.int16) > rgba[..., 2].astype(np.int16) + 30)
        & visible
    )
    return {
        "target_bbox": list(MOUTH_I_TARGET),
        "measured_bbox": list(v10.alpha_bbox(i_mouth)),
        "visible_pixels": int(np.count_nonzero(visible)),
        "near_white_pixels": int(np.count_nonzero(near_white)),
        "green_dominant_pixels": int(np.count_nonzero(green_dominant)),
    }


def main() -> None:
    copy_v11_assets()
    i_mouth = build_i_mouth()
    update_manifests()
    render_reviews(i_mouth)
    stats = mouth_stats(i_mouth)
    if stats["measured_bbox"] != list(MOUTH_I_TARGET):
        raise AssertionError(f"I-vowel bounds mismatch: {stats}")
    if stats["green_dominant_pixels"]:
        raise AssertionError(f"I-vowel still contains chroma spill: {stats}")
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print(f"Built character-v12 assets under {V12_ROOT}")


if __name__ == "__main__":
    main()
