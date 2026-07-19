#!/usr/bin/env python3
"""Build character-v6 without overwriting the approved v5 assets.

v6 keeps the existing full 3/4 poses, adds moderate head-led poses whose
shoulders remain mostly frontal, and replaces only the front closed-mouth
layer with a shorter centered lip line.
"""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps


ROOT = Path(__file__).resolve().parents[1]
CANVAS = (1086, 1448)
V5_ROOT = ROOT / "assets/character-v5"
V6_ROOT = ROOT / "assets/character-v6"
RAW_ROOT = V6_ROOT / "raw/imagegen"
WORK_ROOT = V6_ROOT / "work"
PARTS_ROOT = V6_ROOT / "parts/aligned-v1"
CROPS_ROOT = V6_ROOT / "parts/source-crops"
GUIDES_ROOT = V6_ROOT / "guides"
POSES_ROOT = V6_ROOT / "poses"
PREVIEWS_ROOT = V6_ROOT / "previews"
REVIEW_ROOT = ROOT / "output/review"

CHROMA_SCRIPT = (
    Path.home()
    / ".codex/skills/.system/imagegen/scripts/remove_chroma_key.py"
)

NATURAL_SOURCES = {
    "left_neutral": RAW_ROOT / "natural-left-neutral-chroma-v1.png",
    "left_blink": RAW_ROOT / "natural-left-blink-chroma-v1.png",
    "left_mouth_small": RAW_ROOT / "natural-left-mouth-small-chroma-v1.png",
    "right_neutral": RAW_ROOT / "natural-right-neutral-chroma-v1.png",
    "right_blink": RAW_ROOT / "natural-right-blink-chroma-v1.png",
    "right_mouth_small": RAW_ROOT / "natural-right-mouth-small-chroma-v1.png",
}

# Fixed eye and mouth regions measured from the generated moderate poses.
# Generated expression frames are allowed to contribute only inside these
# rectangles so hair, accessories, clothing, and silhouette stay pixel-exact.
NATURAL_ROIS = {
    "left": {
        "eyes": (330, 412, 620, 526),
        "mouth": (414, 560, 500, 620),
    },
    "right": {
        "eyes": (474, 412, 770, 526),
        "mouth": (604, 566, 690, 628),
    },
}

MOUTH_TARGET = (513, 599, 573, 606)


def copy_file(source: Path, target: Path) -> None:
    if not source.exists():
        raise FileNotFoundError(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def copy_approved_v5_assets() -> None:
    copy_file(
        V5_ROOT / "master/front-faceless-v1.png",
        V6_ROOT / "master/front-faceless-v1.png",
    )
    for path in sorted((V5_ROOT / "parts/aligned-v1").glob("*.png")):
        copy_file(path, PARTS_ROOT / path.name)
    for path in sorted((V5_ROOT / "guides").glob("*.png")):
        copy_file(path, GUIDES_ROOT / path.name)
    for path in sorted((V5_ROOT / "poses").glob("*.png")):
        copy_file(path, POSES_ROOT / path.name)


def register_on_canvas(source: Path, target: Path) -> None:
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


def soft_region_mask(size: tuple[int, int], feather: int = 8) -> Image.Image:
    width, height = size
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    inset = max(1, min(feather, width // 4, height // 4))
    draw.rectangle((inset, inset, width - inset - 1, height - inset - 1), fill=255)
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
        mask = soft_region_mask(original_crop.size)
        result.paste(Image.composite(generated_crop, original_crop, mask), region)
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
        raise AssertionError("Natural expression changed pixels outside its ROI")


def build_natural_poses() -> dict[str, Image.Image]:
    alpha: dict[str, Path] = {}
    for name, source in NATURAL_SOURCES.items():
        if not source.exists():
            raise FileNotFoundError(source)
        registered = WORK_ROOT / f"{name}-chroma-normalized.png"
        target = WORK_ROOT / f"{name}-alpha.png"
        register_on_canvas(source, registered)
        remove_chroma(registered, target)
        alpha[name] = target

    rendered: dict[str, Image.Image] = {}
    POSES_ROOT.mkdir(parents=True, exist_ok=True)
    for direction in ("left", "right"):
        base = Image.open(alpha[f"{direction}_neutral"]).convert("RGBA")
        blink_source = Image.open(alpha[f"{direction}_blink"]).convert("RGBA")
        mouth_source = Image.open(alpha[f"{direction}_mouth_small"]).convert("RGBA")
        rois = NATURAL_ROIS[direction]

        blink = replace_regions(base, blink_source, [rois["eyes"]])
        mouth = replace_regions(base, mouth_source, [rois["mouth"]])
        combined = replace_regions(blink, mouth_source, [rois["mouth"]])
        assert_regions_are_local(base, blink, [rois["eyes"]])
        assert_regions_are_local(base, mouth, [rois["mouth"]])
        assert_regions_are_local(base, combined, [rois["eyes"], rois["mouth"]])

        states = {
            "neutral": base,
            "blink": blink,
            "mouth-small": mouth,
            "blink-mouth-small": combined,
        }
        for state, frame in states.items():
            suffix = "" if state == "neutral" else f"-{state}"
            frame.save(POSES_ROOT / f"view-{direction}-natural{suffix}-v1.png")
            rendered[f"{direction}_{state}"] = frame
    return rendered


def alpha_bbox(image: Image.Image, threshold: int = 12) -> tuple[int, int, int, int]:
    bbox = image.getchannel("A").point(
        lambda value: 255 if value > threshold else 0
    ).getbbox()
    if bbox is None:
        raise ValueError("Layer has no visible alpha")
    return bbox


def refine_closed_mouth() -> Image.Image:
    with Image.open(V5_ROOT / "parts/aligned-v1/mouth_closed.png") as image:
        source = image.convert("RGBA")
    crop = source.crop(alpha_bbox(source))
    width = MOUTH_TARGET[2] - MOUTH_TARGET[0]
    height = MOUTH_TARGET[3] - MOUTH_TARGET[1]
    resized_alpha = crop.getchannel("A").resize(
        (width, height),
        Image.Resampling.LANCZOS,
    ).point(lambda value: round(value * 0.72))

    base = Image.new("RGBA", (width, height), (122, 72, 101, 0))
    base.putalpha(resized_alpha)

    accent_alpha = Image.new("L", (width, height), 0)
    for y in range(height):
        lower_weight = max(0.0, min(1.0, (y - height * 0.25) / (height * 0.6)))
        for x in range(width):
            centered = (x - (width - 1) / 2) / (width * 0.24)
            center_weight = math.exp(-(centered * centered) * 1.8)
            alpha = resized_alpha.getpixel((x, y))
            accent_alpha.putpixel(
                (x, y),
                round(alpha * center_weight * lower_weight * 0.82),
            )
    accent = Image.new("RGBA", (width, height), (232, 138, 163, 0))
    accent.putalpha(accent_alpha)
    refined = Image.alpha_composite(base, accent)

    layer = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    layer.alpha_composite(refined, MOUTH_TARGET[:2])
    bbox = alpha_bbox(layer)
    center_x = (bbox[0] + bbox[2]) / 2
    if abs(center_x - CANVAS[0] / 2) > 0.5:
        raise AssertionError(f"Closed mouth is not centered: {bbox}")
    if bbox[2] - bbox[0] > 60 or bbox[3] - bbox[1] > 7:
        raise AssertionError(f"Closed mouth exceeds compact target: {bbox}")
    if accent_alpha.getbbox() is None or accent_alpha.getextrema()[1] < 12:
        raise AssertionError("Closed mouth is missing the central pink lip accent")

    PARTS_ROOT.mkdir(parents=True, exist_ok=True)
    CROPS_ROOT.mkdir(parents=True, exist_ok=True)
    GUIDES_ROOT.mkdir(parents=True, exist_ok=True)
    layer.save(PARTS_ROOT / "mouth_closed.png")
    refined.save(CROPS_ROOT / "mouth_closed.png")
    guide = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    guide.paste((255, 255, 255, 255), (0, 0), layer.getchannel("A"))
    guide.save(GUIDES_ROOT / "mouth_closed-guide.png")
    return layer


def layer_spec(
    name: str,
    file: str,
    group: str,
    order: int,
    visible: bool = True,
) -> dict:
    return {
        "name": name,
        "file": file,
        "group": group,
        "left": 0,
        "top": 0,
        "opacity": 255,
        "visible": visible,
        "order": order,
    }


def write_manifests() -> None:
    canvas = {"width": CANVAS[0], "height": CANVAS[1]}
    layers = [
        layer_spec("front_faceless_base", "master/front-faceless-v1.png", "10_base", 10),
        layer_spec("eye_base_open", "parts/aligned-v1/eye_base_open.png", "20_eyes", 20),
        layer_spec("irises", "parts/aligned-v1/irises.png", "20_eyes", 21),
        layer_spec("eyes_closed", "parts/aligned-v1/eyes_closed.png", "20_eyes", 22, False),
        layer_spec("brows_neutral", "parts/aligned-v1/brows_neutral.png", "25_brows", 25),
        layer_spec("mouth_closed", "parts/aligned-v1/mouth_closed.png", "30_mouth", 30),
        layer_spec("mouth_open_small", "parts/aligned-v1/mouth_open_small.png", "30_mouth", 31, False),
        layer_spec("mouth_open_wide", "parts/aligned-v1/mouth_open_wide.png", "30_mouth", 32, False),
    ]
    manifest = {
        "canvas": canvas,
        "layers": layers,
        "notes": [
            "character-v6 preserves all approved character-v5 full 3/4 poses.",
            "The front closed mouth is centered at x=543, shortened to at most 60x7px, and has a soft pink central lip accent.",
            "Natural left/right poses turn the head about 20-25 degrees while shoulders follow about 8-12 degrees.",
            "Natural and full side expression edits are clipped to fixed eye and mouth ROIs.",
            "This PSD is layered animation material and has not been rigged or imported in Live2D Cubism.",
        ],
    }
    (V6_ROOT / "manifest-live2d-poc-v1.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    state_layers = {
        "manifest-state-blink-v1.json": [layers[0], layers[3], layers[4], layers[5]],
        "manifest-state-mouth-small-v1.json": [layers[0], layers[1], layers[4], layers[6]],
        "manifest-state-mouth-wide-v1.json": [layers[0], layers[1], layers[4], layers[7]],
    }
    for filename, selected in state_layers.items():
        visible = [{**layer, "visible": True} for layer in selected]
        (V6_ROOT / filename).write_text(
            json.dumps({"canvas": canvas, "layers": visible}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def render_front_state(name: str, layers: list[str]) -> Image.Image:
    frame = Image.open(V6_ROOT / "master/front-faceless-v1.png").convert("RGBA")
    for layer_name in layers:
        with Image.open(PARTS_ROOT / f"{layer_name}.png") as image:
            frame.alpha_composite(image.convert("RGBA"))
    PREVIEWS_ROOT.mkdir(parents=True, exist_ok=True)
    frame.save(PREVIEWS_ROOT / f"{name}-v1.png")
    return frame


def on_background(frame: Image.Image) -> Image.Image:
    background = Image.new("RGBA", frame.size, (15, 19, 40, 255))
    background.alpha_composite(frame)
    return background


def render_reviews(natural: dict[str, Image.Image]) -> None:
    states = [
        ("live2d-neutral", ["eye_base_open", "brows_neutral", "mouth_closed"]),
        ("blink", ["eyes_closed", "brows_neutral", "mouth_closed"]),
        ("mouth-small", ["eye_base_open", "brows_neutral", "mouth_open_small"]),
        ("mouth-wide", ["eye_base_open", "brows_neutral", "mouth_open_wide"]),
    ]
    front = [(name, render_front_state(name, layers)) for name, layers in states]
    REVIEW_ROOT.mkdir(parents=True, exist_ok=True)
    on_background(front[0][1]).save(REVIEW_ROOT / "tsukuyomi-character-v6-front.png")

    face_box = (260, 300, 826, 760)
    face_size = (566, 460)
    face_sheet = Image.new("RGBA", (1132, 920), (15, 19, 40, 255))
    draw = ImageDraw.Draw(face_sheet)
    for index, (name, frame) in enumerate(front):
        x = (index % 2) * face_size[0]
        y = (index // 2) * face_size[1]
        face_sheet.alpha_composite(on_background(frame).crop(face_box), (x, y))
        draw.text((x + 14, y + 14), name, fill=(255, 255, 255, 255))
    face_sheet.save(PREVIEWS_ROOT / "face-expression-contact-sheet-v1.png")
    face_sheet.save(REVIEW_ROOT / "tsukuyomi-character-v6-face-expressions.png")

    pose_states = ("neutral", "blink", "mouth-small", "blink-mouth-small")
    panel_size = (362, 483)
    pose_sheet = Image.new("RGBA", (1448, 966), (15, 19, 40, 255))
    pose_draw = ImageDraw.Draw(pose_sheet)
    for row, direction in enumerate(("left", "right")):
        for column, state in enumerate(pose_states):
            panel = on_background(natural[f"{direction}_{state}"]).resize(
                panel_size,
                Image.Resampling.LANCZOS,
            )
            x = column * panel_size[0]
            y = row * panel_size[1]
            pose_sheet.alpha_composite(panel, (x, y))
            pose_draw.text((x + 14, y + 14), f"natural {direction} / {state}", fill="white")
    pose_sheet.save(PREVIEWS_ROOT / "natural-expression-contact-sheet-v1.png")
    pose_sheet.save(REVIEW_ROOT / "tsukuyomi-character-v6-natural-expressions.png")

    old_front = Image.open(V5_ROOT / "previews/live2d-neutral-v1.png").convert("RGBA")
    new_front = front[0][1]
    comparison = Image.new("RGBA", (900, 420), (15, 19, 40, 255))
    compare_draw = ImageDraw.Draw(comparison)
    crop_box = (318, 394, 768, 814)
    comparison.alpha_composite(on_background(old_front).crop(crop_box), (0, 0))
    comparison.alpha_composite(on_background(new_front).crop(crop_box), (450, 0))
    compare_draw.text((16, 16), "v5 mouth / before", fill="white")
    compare_draw.text((466, 16), "v6 mouth / centered + compact lip", fill="white")
    comparison.save(REVIEW_ROOT / "tsukuyomi-v6-mouth-before-after.png")


def main() -> None:
    copy_approved_v5_assets()
    natural = build_natural_poses()
    refine_closed_mouth()
    write_manifests()
    render_reviews(natural)
    print(f"Built character-v6 assets under {V6_ROOT}")


if __name__ == "__main__":
    main()
