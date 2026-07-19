#!/usr/bin/env python3
"""Build character-v5 from the refreshed user-authored model samples.

The generated facial sprites intentionally arrive on approximate full-canvas
coordinates.  This builder removes chroma, splits paired parts, then registers
every part to measured face coordinates so expression changes never drift.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps


ROOT = Path(__file__).resolve().parents[1]
CANVAS = (1086, 1448)
KEY_COLOR = (0, 255, 0)
ASSET_ROOT = ROOT / "assets/character-v5"
RAW_IMAGEGEN = ASSET_ROOT / "raw/imagegen"
RAW_SOURCE = ASSET_ROOT / "raw/source"
WORK_ROOT = ASSET_ROOT / "work"
PARTS_ROOT = ASSET_ROOT / "parts/aligned-v1"
CROPS_ROOT = ASSET_ROOT / "parts/source-crops"
GUIDES_ROOT = ASSET_ROOT / "guides"
PREVIEWS_ROOT = ASSET_ROOT / "previews"
REVIEW_ROOT = ROOT / "output/review"

CHROMA_SCRIPT = (
    Path.home()
    / ".codex/skills/.system/imagegen/scripts/remove_chroma_key.py"
)

SOURCES = {
    "front": RAW_IMAGEGEN / "front-faceless-chroma-v1.png",
    "eye_base_open": RAW_IMAGEGEN / "eyes-open-chroma-v6-awake-calm.png",
    "eyes_closed": RAW_IMAGEGEN / "eyes-closed-chroma-v1.png",
    "brows_neutral": RAW_IMAGEGEN / "brows-neutral-chroma-v1.png",
    "mouth_closed": RAW_IMAGEGEN / "mouth-closed-chroma-v1.png",
    "mouth_open_small": RAW_IMAGEGEN / "mouth-open-small-chroma-v1.png",
    "mouth_open_wide": RAW_IMAGEGEN / "mouth-open-wide-chroma-v1.png",
    "left": RAW_SOURCE / "view-left-reference.png",
    "right": RAW_SOURCE / "view-right-reference.png",
    "side_left_blink": RAW_IMAGEGEN / "side-left-blink-chroma-v1.png",
    "side_left_mouth_small": RAW_IMAGEGEN / "side-left-mouth-small-chroma-v1.png",
    "side_left_blink_mouth_small": RAW_IMAGEGEN / "side-left-blink-mouth-small-chroma-v1.png",
    "side_right_blink": RAW_IMAGEGEN / "side-right-blink-chroma-v1.png",
    "side_right_mouth_small": RAW_IMAGEGEN / "side-right-mouth-small-chroma-v1.png",
    "side_right_blink_mouth_small": RAW_IMAGEGEN / "side-right-blink-mouth-small-chroma-v1.png",
}

SIDE_ROIS = {
    "left": {
        "eyes": (312, 402, 620, 527),
        "mouth": (392, 570, 469, 620),
    },
    "right": {
        "eyes": (462, 402, 763, 527),
        "mouth": (610, 575, 699, 628),
    },
}

# Registration measured from the refreshed front reference.  The open eyes use
# the calmer adult proportions from the sample.  The final micro-tune opens the
# upper lid by about five percent without changing width or eye spacing.
TARGETS = {
    "eye_open_l": (388, 446, 498, 507),
    "eye_open_r": (588, 446, 698, 507),
    "eye_closed_l": (391, 478, 495, 498),
    "eye_closed_r": (591, 478, 695, 498),
    "brow_l": (403, 400, 483, 413),
    "brow_r": (603, 400, 683, 413),
    "mouth_closed": (505, 598, 581, 609),
    "mouth_open_small": (508, 586, 578, 627),
    "mouth_open_wide": (494, 569, 592, 644),
}


def normalize_on_green(source: Path, out: Path) -> None:
    """Center a source on the exact runtime canvas without cropping it."""
    with Image.open(source) as image:
        rgb = image.convert("RGB")
    scale = min(CANVAS[0] / rgb.width, CANVAS[1] / rgb.height)
    size = (max(1, round(rgb.width * scale)), max(1, round(rgb.height * scale)))
    resized = rgb.resize(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", CANVAS, KEY_COLOR)
    canvas.paste(
        resized,
        ((CANVAS[0] - size[0]) // 2, (CANVAS[1] - size[1]) // 2),
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)


def normalize_side_expression_on_green(source: Path, out: Path) -> None:
    """Register ImageGen side-expression edits to the fixed 1086x1448 canvas.

    ImageGen occasionally returns 1085x1450 even when the supplied side-pose
    reference is 1086x1448.  These files are already full-canvas edits, so a
    direct sub-percent resize preserves their landmark coordinates more
    accurately than fitting and letterboxing them.
    """
    with Image.open(source) as image:
        rgb = image.convert("RGB")
    registered = rgb.resize(CANVAS, Image.Resampling.LANCZOS)
    out.parent.mkdir(parents=True, exist_ok=True)
    registered.save(out)


def remove_chroma(source: Path, out: Path) -> None:
    if not CHROMA_SCRIPT.exists():
        raise FileNotFoundError(f"Missing chroma-key helper: {CHROMA_SCRIPT}")
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            sys.executable,
            str(CHROMA_SCRIPT),
            "--input",
            str(source),
            "--out",
            str(out),
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


def threshold_bbox(image: Image.Image, threshold: int = 24):
    return image.getchannel("A").point(
        lambda value: 255 if value > threshold else 0
    ).getbbox()


def crop_region(image: Image.Image, region: tuple[int, int, int, int]) -> Image.Image:
    candidate = image.crop(region)
    bbox = threshold_bbox(candidate)
    if bbox is None:
        raise ValueError(f"No visible pixels in region {region}")
    return candidate.crop(bbox)


def crop_all(image: Image.Image) -> Image.Image:
    bbox = threshold_bbox(image)
    if bbox is None:
        raise ValueError("No visible pixels in source layer")
    return image.crop(bbox)


def recolor_line(image: Image.Image, color: tuple[int, int, int]) -> Image.Image:
    """Apply a stable line color while preserving the generated antialiasing."""
    rgba = image.convert("RGBA")
    solid = Image.new("RGBA", rgba.size, (*color, 255))
    solid.putalpha(rgba.getchannel("A"))
    return solid


def place_exact(
    crop: Image.Image,
    target: tuple[int, int, int, int],
) -> tuple[Image.Image, Image.Image]:
    left, top, right, bottom = target
    resized = crop.resize((right - left, bottom - top), Image.Resampling.LANCZOS)
    layer = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    layer.alpha_composite(resized, (left, top))
    return layer, resized


def save_guide(name: str, layer: Image.Image) -> None:
    guide = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    mask = layer.getchannel("A").point(lambda value: 255 if value > 12 else 0)
    guide.paste((255, 255, 255, 255), (0, 0), mask)
    GUIDES_ROOT.mkdir(parents=True, exist_ok=True)
    guide.save(GUIDES_ROOT / f"{name}-guide.png")


def save_layer(name: str, components: list[tuple[Image.Image, tuple[int, int, int, int]]]) -> None:
    layer = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    CROPS_ROOT.mkdir(parents=True, exist_ok=True)
    for index, (crop, target) in enumerate(components):
        component_layer, resized = place_exact(crop, target)
        layer.alpha_composite(component_layer)
        suffix = "" if len(components) == 1 else f"-{index + 1}"
        resized.save(CROPS_ROOT / f"{name}{suffix}.png")
    PARTS_ROOT.mkdir(parents=True, exist_ok=True)
    layer.save(PARTS_ROOT / f"{name}.png")
    save_guide(name, layer)


def soft_region_mask(
    size: tuple[int, int],
    feather: int = 8,
) -> Image.Image:
    """Make a mask that returns to the approved pose before the ROI boundary."""
    width, height = size
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    inset = max(1, min(feather, width // 4, height // 4))
    draw.rectangle(
        (inset, inset, width - inset - 1, height - inset - 1),
        fill=255,
    )
    return mask.filter(ImageFilter.GaussianBlur(max(1, inset / 2)))


def replace_side_regions(
    base: Image.Image,
    generated: Image.Image,
    regions: list[tuple[int, int, int, int]],
) -> Image.Image:
    """Keep the approved side pose pixel-exact outside facial edit regions."""
    result = base.convert("RGBA").copy()
    generated_rgba = generated.convert("RGBA")
    for region in regions:
        original_crop = result.crop(region)
        generated_crop = generated_rgba.crop(region)
        mask = soft_region_mask(original_crop.size)
        replacement = Image.composite(generated_crop, original_crop, mask)
        result.paste(replacement, region)
    return result


def assert_regions_are_local(
    base: Image.Image,
    variant: Image.Image,
    regions: list[tuple[int, int, int, int]],
) -> None:
    """Fail the build if an expression variant changes pixels outside its ROIs."""
    difference = ImageChops.difference(base.convert("RGBA"), variant.convert("RGBA"))
    allowed = Image.new("L", CANVAS, 0)
    draw = ImageDraw.Draw(allowed)
    for region in regions:
        draw.rectangle(region, fill=255)
    outside = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    outside.paste(difference, (0, 0), ImageOps.invert(allowed))
    # RGBA Image.getbbox() can return None when RGB changed but alpha stayed 0.
    # Check every channel independently so the guard also catches RGB-only leaks.
    if any(channel.getbbox() is not None for channel in outside.split()):
        raise AssertionError("Side expression changed pixels outside its fixed facial ROIs")


def build_side_expression_poses(alpha: dict[str, Path]) -> dict[str, Image.Image]:
    poses_root = ASSET_ROOT / "poses"
    poses_root.mkdir(parents=True, exist_ok=True)
    rendered: dict[str, Image.Image] = {}

    for direction in ("left", "right"):
        base = Image.open(alpha[direction]).convert("RGBA")
        rendered[f"{direction}_neutral"] = base
        rois = SIDE_ROIS[direction]
        variants = {
            "blink": ([rois["eyes"]], f"side_{direction}_blink"),
            "mouth_small": ([rois["mouth"]], f"side_{direction}_mouth_small"),
            "blink_mouth_small": (
                [rois["eyes"], rois["mouth"]],
                f"side_{direction}_blink_mouth_small",
            ),
        }
        for state, (regions, source_key) in variants.items():
            generated = Image.open(alpha[source_key]).convert("RGBA")
            composed = replace_side_regions(base, generated, regions)
            assert_regions_are_local(base, composed, regions)
            composed.save(poses_root / f"view-{direction}-3q-{state.replace('_', '-')}-v1.png")
            rendered[f"{direction}_{state}"] = composed

    return rendered


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
    all_layers = [
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
        "layers": all_layers,
        "notes": [
            "models/ refreshed samples are the character identity source of truth.",
            "23_03_43 (1) is the front registration reference; 3/4 samples provide side poses.",
            "Open eyes use calm adult 110x61 almond proportions, with 200px center spacing and thin dark-violet linework.",
            "The open-eye irises are intentionally asymmetric: screen-left/character-right is dark, while screen-right/character-left has the pale moon ring.",
            "The revised source lifts the upper lids and softens the outer corners; 61px registration adds about five percent eye height while keeping a calm direct gaze.",
            "Mouth states retain the approved source art; the speaking states are 7-9 percent less open for quiet narration.",
            "Complete eyes are one layer; irises is a one-pixel compatibility placeholder and gaze translation is visually inactive in v5.",
            "This PSD is layered animation material and has not been rigged or imported in Live2D Cubism.",
        ],
    }
    (ASSET_ROOT / "manifest-live2d-poc-v1.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    state_layers = {
        "manifest-state-blink-v1.json": [all_layers[0], all_layers[3], all_layers[4], all_layers[5]],
        "manifest-state-mouth-small-v1.json": [all_layers[0], all_layers[1], all_layers[4], all_layers[6]],
        "manifest-state-mouth-wide-v1.json": [all_layers[0], all_layers[1], all_layers[4], all_layers[7]],
    }
    for filename, layers in state_layers.items():
        visible_layers = [{**layer, "visible": True} for layer in layers]
        (ASSET_ROOT / filename).write_text(
            json.dumps({"canvas": canvas, "layers": visible_layers}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def render_state(name: str, layers: list[str]) -> Image.Image:
    frame = Image.open(ASSET_ROOT / "master/front-faceless-v1.png").convert("RGBA")
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


def render_previews() -> None:
    states = [
        ("live2d-neutral", ["eye_base_open", "brows_neutral", "mouth_closed"]),
        ("blink", ["eyes_closed", "brows_neutral", "mouth_closed"]),
        ("mouth-small", ["eye_base_open", "brows_neutral", "mouth_open_small"]),
        ("mouth-wide", ["eye_base_open", "brows_neutral", "mouth_open_wide"]),
    ]
    rendered = [(name, render_state(name, layers)) for name, layers in states]

    panel_size = (543, 724)
    sheet = Image.new("RGBA", (panel_size[0] * len(rendered), panel_size[1]), (15, 19, 40, 255))
    draw = ImageDraw.Draw(sheet)
    for index, (name, frame) in enumerate(rendered):
        panel = on_background(frame).resize(panel_size, Image.Resampling.LANCZOS)
        sheet.alpha_composite(panel, (panel_size[0] * index, 0))
        draw.text((panel_size[0] * index + 16, 16), name, fill=(255, 255, 255, 255))
    sheet.save(PREVIEWS_ROOT / "expression-contact-sheet-v1.png")

    face_box = (260, 300, 826, 760)
    face_size = (566, 460)
    face_sheet = Image.new("RGBA", (face_size[0] * 2, face_size[1] * 2), (15, 19, 40, 255))
    face_draw = ImageDraw.Draw(face_sheet)
    for index, (name, frame) in enumerate(rendered):
        face = on_background(frame).crop(face_box)
        x = (index % 2) * face_size[0]
        y = (index // 2) * face_size[1]
        face_sheet.alpha_composite(face, (x, y))
        face_draw.text((x + 14, y + 14), name, fill=(255, 255, 255, 255))
    face_sheet.save(PREVIEWS_ROOT / "face-expression-contact-sheet-v1.png")

    REVIEW_ROOT.mkdir(parents=True, exist_ok=True)
    on_background(rendered[0][1]).save(REVIEW_ROOT / "tsukuyomi-character-v5-front.png")
    face_sheet.save(REVIEW_ROOT / "tsukuyomi-character-v5-face-expressions.png")


def render_side_previews(side_poses: dict[str, Image.Image]) -> None:
    """Render both side directions and all ASMR-safe expression states."""
    states = ("neutral", "blink", "mouth_small", "blink_mouth_small")
    panel_size = (362, 483)
    sheet = Image.new(
        "RGBA",
        (panel_size[0] * len(states), panel_size[1] * 2),
        (15, 19, 40, 255),
    )
    draw = ImageDraw.Draw(sheet)
    for row, direction in enumerate(("left", "right")):
        for column, state in enumerate(states):
            frame = side_poses[f"{direction}_{state}"]
            panel = on_background(frame).resize(panel_size, Image.Resampling.LANCZOS)
            x = column * panel_size[0]
            y = row * panel_size[1]
            sheet.alpha_composite(panel, (x, y))
            draw.text(
                (x + 14, y + 14),
                f"{direction} / {state.replace('_', ' ')}",
                fill=(255, 255, 255, 255),
            )

    PREVIEWS_ROOT.mkdir(parents=True, exist_ok=True)
    REVIEW_ROOT.mkdir(parents=True, exist_ok=True)
    sheet.save(PREVIEWS_ROOT / "side-expression-contact-sheet-v1.png")
    sheet.save(REVIEW_ROOT / "tsukuyomi-character-v5-side-expressions.png")


def main() -> None:
    for name, source in SOURCES.items():
        if not source.exists():
            raise FileNotFoundError(f"Missing v5 source {name}: {source}")

    normalized: dict[str, Path] = {}
    alpha: dict[str, Path] = {}
    for name, source in SOURCES.items():
        normalized_path = WORK_ROOT / f"{name}-chroma-normalized.png"
        alpha_path = WORK_ROOT / f"{name}-alpha.png"
        if name.startswith("side_"):
            normalize_side_expression_on_green(source, normalized_path)
        else:
            normalize_on_green(source, normalized_path)
        remove_chroma(normalized_path, alpha_path)
        normalized[name] = normalized_path
        alpha[name] = alpha_path

    (ASSET_ROOT / "master").mkdir(parents=True, exist_ok=True)
    (ASSET_ROOT / "poses").mkdir(parents=True, exist_ok=True)
    Image.open(alpha["front"]).convert("RGBA").save(ASSET_ROOT / "master/front-faceless-v1.png")
    Image.open(alpha["left"]).convert("RGBA").save(ASSET_ROOT / "poses/view-left-3q-v1.png")
    Image.open(alpha["right"]).convert("RGBA").save(ASSET_ROOT / "poses/view-right-3q-v1.png")
    side_poses = build_side_expression_poses(alpha)

    open_eyes = Image.open(alpha["eye_base_open"]).convert("RGBA")
    closed_eyes = Image.open(alpha["eyes_closed"]).convert("RGBA")
    brows = Image.open(alpha["brows_neutral"]).convert("RGBA")
    mouth_closed = Image.open(alpha["mouth_closed"]).convert("RGBA")
    mouth_small = Image.open(alpha["mouth_open_small"]).convert("RGBA")
    mouth_wide = Image.open(alpha["mouth_open_wide"]).convert("RGBA")

    left_half = (0, 0, CANVAS[0] // 2, CANVAS[1])
    right_half = (CANVAS[0] // 2, 0, CANVAS[0], CANVAS[1])
    # Keep the generated outer shapes registered symmetrically, but preserve the
    # reference's intentional iris asymmetry: screen-left is the character's
    # dark right eye, screen-right is the luminous moon-ring left eye.
    dark_right_eye = crop_region(open_eyes, left_half)
    luminous_left_eye = crop_region(open_eyes, right_half)
    save_layer(
        "eye_base_open",
        [
            (dark_right_eye, TARGETS["eye_open_l"]),
            (luminous_left_eye, TARGETS["eye_open_r"]),
        ],
    )
    approved_closed_eye = crop_region(closed_eyes, right_half)
    save_layer(
        "eyes_closed",
        [
            (ImageOps.mirror(approved_closed_eye), TARGETS["eye_closed_l"]),
            (approved_closed_eye, TARGETS["eye_closed_r"]),
        ],
    )
    approved_brow = crop_region(brows, right_half)
    save_layer(
        "brows_neutral",
        [
            (ImageOps.mirror(approved_brow), TARGETS["brow_l"]),
            (approved_brow, TARGETS["brow_r"]),
        ],
    )
    closed_crop = recolor_line(crop_all(mouth_closed), (116, 62, 88))
    save_layer("mouth_closed", [(closed_crop, TARGETS["mouth_closed"])])
    save_layer("mouth_open_small", [(crop_all(mouth_small), TARGETS["mouth_open_small"])])
    save_layer("mouth_open_wide", [(crop_all(mouth_wide), TARGETS["mouth_open_wide"])])

    # Compatibility with the existing runtime interface.  The eye sprite is a
    # complete eye pair, so separate gaze translation remains intentionally off.
    irises = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    irises.putpixel((543, 478), (255, 255, 255, 1))
    PARTS_ROOT.mkdir(parents=True, exist_ok=True)
    irises.save(PARTS_ROOT / "irises.png")
    iris_guide = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    iris_guide.putpixel((543, 478), (255, 255, 255, 255))
    GUIDES_ROOT.mkdir(parents=True, exist_ok=True)
    iris_guide.save(GUIDES_ROOT / "irises-guide.png")

    write_manifests()
    render_previews()
    render_side_previews(side_poses)
    print(f"Built character-v5 assets under {ASSET_ROOT}")


if __name__ == "__main__":
    main()
