#!/usr/bin/env python3
"""Build character-v9 from approved v8 endpoints plus right-turn in-betweens."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps


ROOT = Path(__file__).resolve().parents[1]
CANVAS = (1086, 1448)
V8_ROOT = ROOT / "assets/character-v8"
V9_ROOT = ROOT / "assets/character-v9"
RAW_ROOT = V9_ROOT / "raw/imagegen"
WORK_ROOT = V9_ROOT / "work"
PARTS_ROOT = V9_ROOT / "parts/aligned-v1"
GUIDES_ROOT = V9_ROOT / "guides"
POSES_ROOT = V9_ROOT / "poses"
PREVIEWS_ROOT = V9_ROOT / "previews"
REVIEW_ROOT = ROOT / "output/review"
CHROMA_SCRIPT = (
    Path.home() / ".codex/skills/.system/imagegen/scripts/remove_chroma_key.py"
)

MOUTH_I_TARGET = (512, 592, 574, 621)
RIGHT_STEPS = {
    "25": {
        "eyes": (406, 417, 735, 529),
        "mouth": (527, 565, 631, 636),
    },
    "50": {
        "eyes": (443, 414, 754, 527),
        "mouth": (568, 566, 663, 632),
    },
    "80": {
        "eyes": (467, 406, 766, 527),
        "mouth": (607, 571, 695, 628),
    },
}


def copy_file(source: Path, target: Path) -> None:
    if not source.exists():
        raise FileNotFoundError(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def copy_approved_v8_assets() -> None:
    for folder in ("master", "parts/aligned-v1", "guides", "poses", "previews"):
        for path in sorted((V8_ROOT / folder).glob("*.png")):
            copy_file(path, V9_ROOT / folder / path.name)
    for path in sorted(V8_ROOT.glob("manifest-*.json")):
        copy_file(path, V9_ROOT / path.name)


def normalize_full_canvas(source: Path, target: Path) -> None:
    with Image.open(source) as image:
        registered = image.convert("RGB").resize(CANVAS, Image.Resampling.LANCZOS)
    target.parent.mkdir(parents=True, exist_ok=True)
    registered.save(target)


def remove_chroma(source: Path, target: Path) -> None:
    if not CHROMA_SCRIPT.exists():
        raise FileNotFoundError(CHROMA_SCRIPT)
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


def alpha_bbox(image: Image.Image, threshold: int = 20) -> tuple[int, int, int, int]:
    bbox = image.getchannel("A").point(
        lambda value: 255 if value > threshold else 0
    ).getbbox()
    if bbox is None:
        raise ValueError("Layer has no visible alpha")
    return bbox


def soft_region_mask(size: tuple[int, int], feather: int = 8) -> Image.Image:
    width, height = size
    mask = Image.new("L", size, 0)
    inset = max(1, min(feather, width // 4, height // 4))
    ImageDraw.Draw(mask).rectangle(
        (inset, inset, width - inset - 1, height - inset - 1),
        fill=255,
    )
    return mask.filter(ImageFilter.GaussianBlur(max(1, inset / 2)))


def replace_regions(
    base: Image.Image,
    generated: Image.Image,
    regions: list[tuple[int, int, int, int]],
) -> Image.Image:
    result = base.convert("RGBA").copy()
    generated_rgba = generated.convert("RGBA")
    for region in regions:
        original_crop = result.crop(region)
        generated_crop = generated_rgba.crop(region)
        replacement = Image.composite(
            generated_crop,
            original_crop,
            soft_region_mask(original_crop.size),
        )
        result.paste(replacement, region)
    return result


def assert_regions_are_local(
    base: Image.Image,
    variant: Image.Image,
    regions: list[tuple[int, int, int, int]],
) -> None:
    difference = ImageChops.difference(base.convert("RGBA"), variant.convert("RGBA"))
    allowed = Image.new("L", CANVAS, 0)
    draw = ImageDraw.Draw(allowed)
    for region in regions:
        draw.rectangle(region, fill=255)
    outside = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    outside.paste(difference, (0, 0), ImageOps.invert(allowed))
    if any(channel.getbbox() is not None for channel in outside.split()):
        raise AssertionError("Intermediate expression changed pixels outside its ROI")


def build_i_mouth() -> Image.Image:
    registered = WORK_ROOT / "mouth-vowel-i-teeth-chroma-normalized-v1.png"
    alpha_path = WORK_ROOT / "mouth-vowel-i-teeth-alpha-v1.png"
    normalize_full_canvas(
        RAW_ROOT / "mouth-vowel-i-teeth-chroma-v1.png",
        registered,
    )
    remove_chroma(registered, alpha_path)
    with Image.open(alpha_path) as image:
        source = image.convert("RGBA")
    crop = source.crop(alpha_bbox(source))
    width = MOUTH_I_TARGET[2] - MOUTH_I_TARGET[0]
    height = MOUTH_I_TARGET[3] - MOUTH_I_TARGET[1]
    crop = crop.resize((width, height), Image.Resampling.LANCZOS)
    aligned = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    aligned.alpha_composite(crop, MOUTH_I_TARGET[:2])
    if alpha_bbox(aligned) != MOUTH_I_TARGET:
        raise AssertionError(f"I mouth is not aligned to {MOUTH_I_TARGET}")

    visible = aligned.crop(MOUTH_I_TARGET).convert("RGB")
    white_pixels = sum(
        1 for red, green, blue in visible.get_flattened_data()
        if red > 210 and green > 205 and blue > 205
    )
    if white_pixels < 80:
        raise AssertionError("I mouth needs a clearly visible upper-teeth strip")

    PARTS_ROOT.mkdir(parents=True, exist_ok=True)
    GUIDES_ROOT.mkdir(parents=True, exist_ok=True)
    aligned.save(PARTS_ROOT / "mouth_vowel_i.png")
    guide = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    guide.paste((255, 255, 255, 255), (0, 0), aligned.getchannel("A"))
    guide.save(GUIDES_ROOT / "mouth_vowel_i-guide.png")
    return aligned


def build_intermediate_poses() -> dict[str, Image.Image]:
    rendered: dict[str, Image.Image] = {}
    POSES_ROOT.mkdir(parents=True, exist_ok=True)
    for step, rois in RIGHT_STEPS.items():
        alpha_paths = {}
        for state in ("neutral", "blink-mouth-small"):
            source = RAW_ROOT / f"view-right-step-{step}-{state}-chroma-v1.png"
            registered = WORK_ROOT / f"view-right-step-{step}-{state}-chroma-normalized-v1.png"
            alpha = WORK_ROOT / f"view-right-step-{step}-{state}-alpha-v1.png"
            normalize_full_canvas(source, registered)
            remove_chroma(registered, alpha)
            alpha_paths[state] = alpha

        with Image.open(alpha_paths["neutral"]) as image:
            neutral = image.convert("RGBA")
        with Image.open(alpha_paths["blink-mouth-small"]) as image:
            combined_source = image.convert("RGBA")
        blink = replace_regions(neutral, combined_source, [rois["eyes"]])
        mouth = replace_regions(neutral, combined_source, [rois["mouth"]])
        combined = replace_regions(
            neutral,
            combined_source,
            [rois["eyes"], rois["mouth"]],
        )
        states = {
            "neutral": neutral,
            "blink": blink,
            "mouth-small": mouth,
            "blink-mouth-small": combined,
        }
        for state, frame in states.items():
            suffix = "" if state == "neutral" else f"-{state}"
            path = POSES_ROOT / f"view-right-step-{step}{suffix}-v1.png"
            frame.save(path)
            rendered[f"{step}_{state}"] = frame
        assert_regions_are_local(neutral, blink, [rois["eyes"]])
        assert_regions_are_local(neutral, mouth, [rois["mouth"]])
        assert_regions_are_local(
            neutral,
            combined,
            [rois["eyes"], rois["mouth"]],
        )
    return rendered


def composite_front(mouth: Image.Image) -> Image.Image:
    frame = Image.open(V9_ROOT / "master/front-faceless-v1.png").convert("RGBA")
    for name in ("eye_base_open", "irises", "brows_neutral"):
        frame.alpha_composite(Image.open(PARTS_ROOT / f"{name}.png").convert("RGBA"))
    frame.alpha_composite(mouth)
    return frame


def on_background(frame: Image.Image) -> Image.Image:
    background = Image.new("RGBA", CANVAS, (15, 19, 40, 255))
    background.alpha_composite(frame)
    return background


def render_reviews(i_mouth: Image.Image, poses: dict[str, Image.Image]) -> None:
    PREVIEWS_ROOT.mkdir(parents=True, exist_ok=True)
    REVIEW_ROOT.mkdir(parents=True, exist_ok=True)

    old_i = Image.open(V8_ROOT / "parts/aligned-v1/mouth_vowel_i.png").convert("RGBA")
    mouth_sheet = Image.new("RGBA", (532, 190), (15, 19, 40, 255))
    mouth_draw = ImageDraw.Draw(mouth_sheet)
    crop_box = (410, 500, 676, 690)
    mouth_sheet.alpha_composite(on_background(composite_front(old_i)).crop(crop_box), (0, 0))
    mouth_sheet.alpha_composite(on_background(composite_front(i_mouth)).crop(crop_box), (266, 0))
    mouth_draw.text((12, 10), "v8 I / before", fill="white")
    mouth_draw.text((278, 10), "v9 I / narrower + teeth", fill="white")
    mouth_sheet.save(PREVIEWS_ROOT / "mouth-i-before-after-v1.png")
    mouth_sheet.save(REVIEW_ROOT / "tsukuyomi-v9-mouth-i-before-after.png")

    sequence = [
        ("front", Image.open(V8_ROOT / "previews/live2d-neutral-v1.png").convert("RGBA")),
        ("right 25", poses["25_neutral"]),
        ("right 50", poses["50_neutral"]),
        ("natural right", Image.open(V8_ROOT / "poses/view-right-natural-v1.png").convert("RGBA")),
        ("right 80", poses["80_neutral"]),
        ("full right", Image.open(V8_ROOT / "poses/view-right-3q-v1.png").convert("RGBA")),
    ]
    panel = (271, 362)
    sheet = Image.new("RGBA", (panel[0] * len(sequence), panel[1]), (15, 19, 40, 255))
    draw = ImageDraw.Draw(sheet)
    for index, (label, frame) in enumerate(sequence):
        resized = on_background(frame).resize(panel, Image.Resampling.LANCZOS)
        sheet.alpha_composite(resized, (panel[0] * index, 0))
        draw.text((panel[0] * index + 10, 10), label, fill="white")
    sheet.save(PREVIEWS_ROOT / "right-turn-inbetweens-v1.png")
    sheet.save(REVIEW_ROOT / "tsukuyomi-v9-right-turn-inbetweens.png")


def update_manifest_notes() -> None:
    path = V9_ROOT / "manifest-live2d-poc-v1.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["notes"] = [
        "character-v9 preserves every approved character-v8 endpoint and front layer except the I vowel mouth.",
        "The front-only Japanese I vowel is narrower than E and includes a visible upper-teeth strip.",
        "Three completed right-turn in-between rasters bridge front, natural-right, and full-right endpoints.",
        "Intermediate expression edits are restricted to fixed eye and mouth ROIs.",
        "Left-side interpolation remains an explicit future extension; approved left endpoints are preserved.",
        "This PSD is layered animation material and has not been imported in Live2D Cubism.",
    ]
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    copy_approved_v8_assets()
    i_mouth = build_i_mouth()
    poses = build_intermediate_poses()
    update_manifest_notes()
    render_reviews(i_mouth, poses)
    print(f"Built character-v9 assets under {V9_ROOT}")


if __name__ == "__main__":
    main()
