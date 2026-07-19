#!/usr/bin/env python3
"""Build character-v7 tracking eyes without overwriting character-v6."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
CANVAS = (1086, 1448)
V6_ROOT = ROOT / "assets/character-v6"
V7_ROOT = ROOT / "assets/character-v7"
RAW_ROOT = V7_ROOT / "raw/imagegen"
WORK_ROOT = V7_ROOT / "work"
PARTS_ROOT = V7_ROOT / "parts/aligned-v1"
PREVIEWS_ROOT = V7_ROOT / "previews"
REVIEW_ROOT = ROOT / "output/review"
CHROMA_SCRIPT = Path.home() / ".codex/skills/.system/imagegen/scripts/remove_chroma_key.py"

EYE_BOXES = {
    "screen_left": (388, 446, 498, 507),
    "screen_right": (588, 446, 698, 507),
}
IRIS_BOXES = {
    "screen_left": (422, 454, 464, 502),
    "screen_right": (622, 454, 664, 502),
}
IRIS_CENTERS = {
    "screen_left": (443, 478),
    "screen_right": (643, 478),
}


def copy_file(source: Path, target: Path) -> None:
    if not source.exists():
        raise FileNotFoundError(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def copy_v6_assets() -> None:
    copy_file(
        V6_ROOT / "master/front-faceless-v1.png",
        V7_ROOT / "master/front-faceless-v1.png",
    )
    for path in sorted((V6_ROOT / "poses").glob("*.png")):
        copy_file(path, V7_ROOT / "poses" / path.name)
    for path in sorted((V6_ROOT / "parts/aligned-v1").glob("*.png")):
        if path.name not in {"eye_base_open.png", "irises.png"}:
            copy_file(path, PARTS_ROOT / path.name)
    for path in sorted((V6_ROOT / "guides").glob("*.png")):
        if path.name not in {"eye_base_open-guide.png", "irises-guide.png"}:
            copy_file(path, V7_ROOT / "guides" / path.name)


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


def component_bbox(image: Image.Image, side: str) -> tuple[int, int, int, int]:
    half = CANVAS[0] // 2
    region = (0, 0, half, CANVAS[1]) if side == "screen_left" else (half, 0, CANVAS[0], CANVAS[1])
    local = image.crop(region).getchannel("A").point(lambda value: 255 if value > 20 else 0).getbbox()
    if local is None:
        raise ValueError(f"Missing generated component: {side}")
    return (local[0] + region[0], local[1], local[2] + region[0], local[3])


def align_components(source: Image.Image, targets: dict[str, tuple[int, int, int, int]]) -> Image.Image:
    result = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    for side, target in targets.items():
        crop = source.crop(component_bbox(source, side))
        target_size = (target[2] - target[0], target[3] - target[1])
        aligned = crop.resize(target_size, Image.Resampling.LANCZOS)
        result.alpha_composite(aligned, target[:2])
    return result


def build_tracking_eyes() -> tuple[Image.Image, Image.Image]:
    sclera_alpha = WORK_ROOT / "eye-base-no-irises-alpha-v1.png"
    irises_alpha = WORK_ROOT / "irises-tracking-alpha-v1.png"
    remove_chroma(RAW_ROOT / "eye-base-no-irises-chroma-v2-clean.png", sclera_alpha)
    remove_chroma(RAW_ROOT / "irises-tracking-chroma-v1.png", irises_alpha)

    generated_sclera = align_components(
        Image.open(sclera_alpha).convert("RGBA"),
        EYE_BOXES,
    )
    generated_irises = align_components(
        Image.open(irises_alpha).convert("RGBA"),
        IRIS_BOXES,
    )
    original = Image.open(V6_ROOT / "parts/aligned-v1/eye_base_open.png").convert("RGBA")

    # Keep the approved eyelashes and eye silhouettes pixel-exact. Replace only
    # the iris-bearing interior with the generated clean sclera under-paint.
    interior_mask = Image.new("L", CANVAS, 0)
    draw = ImageDraw.Draw(interior_mask)
    for center in IRIS_CENTERS.values():
        draw.ellipse(
            (center[0] - 29, center[1] - 25, center[0] + 29, center[1] + 25),
            fill=255,
        )
    interior_mask = interior_mask.filter(ImageFilter.GaussianBlur(1.2))
    eye_base = Image.composite(generated_sclera, original, interior_mask)

    PARTS_ROOT.mkdir(parents=True, exist_ok=True)
    eye_base.save(PARTS_ROOT / "eye_base_open.png")
    generated_irises.save(PARTS_ROOT / "irises.png")

    guide_root = V7_ROOT / "guides"
    guide_root.mkdir(parents=True, exist_ok=True)
    for name, image in (("eye_base_open", eye_base), ("irises", generated_irises)):
        guide = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
        guide.paste((255, 255, 255, 255), (0, 0), image.getchannel("A"))
        guide.save(guide_root / f"{name}-guide.png")

    if generated_irises.getchannel("A").getbbox() != (422, 454, 664, 502):
        raise AssertionError("Tracking irises are not aligned to the fixed target boxes")
    return eye_base, generated_irises


def composite_front(eye_base: Image.Image, irises: Image.Image, gaze=(0, 0)) -> Image.Image:
    frame = Image.open(V7_ROOT / "master/front-faceless-v1.png").convert("RGBA")
    frame.alpha_composite(eye_base)
    shifted = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    shifted.alpha_composite(irises, gaze)
    frame.alpha_composite(shifted)
    for name in ("brows_neutral", "mouth_closed"):
        frame.alpha_composite(Image.open(PARTS_ROOT / f"{name}.png").convert("RGBA"))
    return frame


def write_manifests() -> None:
    manifest = json.loads((V6_ROOT / "manifest-live2d-poc-v1.json").read_text(encoding="utf-8"))
    manifest["notes"] = [
        "character-v7 preserves all approved character-v6 natural and full 3/4 poses.",
        "The front open eyes are separated into eye_base_open and movable irises for two-axis gaze tracking.",
        "The PixiJS review rig links neck turn to bilateral long-hair deformation; Cubism rigging remains unimplemented.",
        "This PSD is layered animation material and has not been imported in Live2D Cubism.",
    ]
    (V7_ROOT / "manifest-live2d-poc-v1.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    for filename in (
        "manifest-state-blink-v1.json",
        "manifest-state-mouth-small-v1.json",
        "manifest-state-mouth-wide-v1.json",
    ):
        source = json.loads((V6_ROOT / filename).read_text(encoding="utf-8"))
        if filename != "manifest-state-blink-v1.json":
            iris_layer = next(layer for layer in manifest["layers"] if layer["name"] == "irises")
            if not any(layer["name"] == "irises" for layer in source["layers"]):
                source["layers"].append({**iris_layer, "visible": True})
        source["layers"].sort(key=lambda layer: layer["order"])
        (V7_ROOT / filename).write_text(
            json.dumps(source, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def render_reviews(eye_base: Image.Image, irises: Image.Image) -> None:
    PREVIEWS_ROOT.mkdir(parents=True, exist_ok=True)
    REVIEW_ROOT.mkdir(parents=True, exist_ok=True)
    neutral = composite_front(eye_base, irises)
    neutral.save(PREVIEWS_ROOT / "live2d-neutral-v1.png")

    background = (15, 19, 40, 255)
    states = [
        ("LEFT", (-12, 0)),
        ("CENTER", (0, 0)),
        ("RIGHT", (12, 0)),
        ("UP", (0, -7)),
        ("DOWN", (0, 7)),
    ]
    crop_box = (330, 370, 756, 650)
    sheet = Image.new("RGBA", (426 * len(states), 280), background)
    draw = ImageDraw.Draw(sheet)
    for index, (label, offset) in enumerate(states):
        frame = Image.new("RGBA", CANVAS, background)
        frame.alpha_composite(composite_front(eye_base, irises, offset))
        sheet.alpha_composite(frame.crop(crop_box), (index * 426, 0))
        draw.text((index * 426 + 14, 14), f"GAZE {label} {offset}", fill="white")
    sheet.save(PREVIEWS_ROOT / "gaze-range-v1.png")
    sheet.save(REVIEW_ROOT / "tsukuyomi-v7-gaze-range.png")

    previous = Image.open(V6_ROOT / "previews/live2d-neutral-v1.png").convert("RGBA")
    comparison = Image.new("RGBA", (852, 500), background)
    comparison.alpha_composite(previous.crop((330, 330, 756, 830)), (0, 0))
    comparison.alpha_composite(neutral.crop((330, 330, 756, 830)), (426, 0))
    compare_draw = ImageDraw.Draw(comparison)
    compare_draw.text((14, 14), "v6 baked irises", fill="white")
    compare_draw.text((440, 14), "v7 tracking layers", fill="white")
    comparison.save(REVIEW_ROOT / "tsukuyomi-v7-eye-split-before-after.png")

    diff = ImageChops.difference(previous.convert("RGB"), neutral.convert("RGB"))
    print(f"Neutral tracking-eye difference bbox: {diff.getbbox()}")


def main() -> None:
    copy_v6_assets()
    eye_base, irises = build_tracking_eyes()
    write_manifests()
    render_reviews(eye_base, irises)
    print(f"Built character-v7 assets under {V7_ROOT}")


if __name__ == "__main__":
    main()
