#!/usr/bin/env python3
"""Build character-v10 with cached neck keyframes and a micro-open mouth."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
CANVAS = (1086, 1448)
FRAME_SIZE = (768, 1024)
ATLAS_COLUMNS = 4
ATLAS_ROWS = 4
FRAME_COUNT = ATLAS_COLUMNS * ATLAS_ROWS
V9_ROOT = ROOT / "assets/character-v9"
V10_ROOT = ROOT / "assets/character-v10"
RAW_ROOT = V10_ROOT / "raw/imagegen"
WORK_ROOT = V10_ROOT / "work"
PARTS_ROOT = V10_ROOT / "parts/aligned-v1"
GUIDES_ROOT = V10_ROOT / "guides"
POSES_ROOT = V10_ROOT / "poses"
PREVIEWS_ROOT = V10_ROOT / "previews"
ATLAS_ROOT = V10_ROOT / "neck-atlases"
REVIEW_ROOT = ROOT / "output/review"
CHROMA_SCRIPT = (
    Path.home() / ".codex/skills/.system/imagegen/scripts/remove_chroma_key.py"
)

MOUTH_MICRO_TARGET = (512, 596, 574, 614)
MOUTH_I_TARGET = (514, 596, 572, 616)
STATES = ("neutral", "blink", "mouth-small")
MATTE_RGB = np.array([15, 19, 40], dtype=np.float32) / 255
PATCH_ROIS = {
    "left": {
        "blink": (320, 400, 710, 540),
        "mouth-small": (400, 550, 600, 640),
    },
    "right": {
        "blink": (390, 400, 780, 540),
        "mouth-small": (500, 550, 710, 645),
    },
}


def copy_file(source: Path, target: Path) -> None:
    if not source.exists():
        raise FileNotFoundError(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def copy_v9_assets() -> None:
    for folder in ("master", "parts/aligned-v1", "guides", "poses", "previews"):
        for path in sorted((V9_ROOT / folder).glob("*.png")):
            copy_file(path, V10_ROOT / folder / path.name)
    for path in sorted(V9_ROOT.glob("manifest-*.json")):
        copy_file(path, V10_ROOT / path.name)


def alpha_bbox(image: Image.Image, threshold: int = 20) -> tuple[int, int, int, int]:
    bbox = image.getchannel("A").point(
        lambda value: 255 if value > threshold else 0
    ).getbbox()
    if bbox is None:
        raise ValueError("Layer has no visible alpha")
    return bbox


def full_canvas_part(crop: Image.Image, target: tuple[int, int, int, int]) -> Image.Image:
    width = target[2] - target[0]
    height = target[3] - target[1]
    resized = crop.resize((width, height), Image.Resampling.LANCZOS)
    aligned = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    aligned.alpha_composite(resized, target[:2])
    if alpha_bbox(aligned) != target:
        raise AssertionError(f"Part did not align to {target}: {alpha_bbox(aligned)}")
    return aligned


def save_guide(layer: Image.Image, name: str) -> None:
    guide = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    guide.paste((255, 255, 255, 255), (0, 0), layer.getchannel("A"))
    guide.save(GUIDES_ROOT / f"{name}-guide.png")


def build_micro_mouth() -> Image.Image:
    source = Image.open(PARTS_ROOT / "mouth_open_small.png").convert("RGBA")
    micro = full_canvas_part(source.crop(alpha_bbox(source)), MOUTH_MICRO_TARGET)
    micro.save(PARTS_ROOT / "mouth_open_micro.png")
    save_guide(micro, "mouth_open_micro")
    return micro


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


def restrain_teeth(crop: Image.Image) -> Image.Image:
    """Remove the generated white plane and leave only a tiny central glint."""
    rgba = np.array(crop.convert("RGBA"))
    rgb = rgba[..., :3]
    alpha = rgba[..., 3]
    near_white = (
        (rgb[..., 0] > 205)
        & (rgb[..., 1] > 190)
        & (rgb[..., 2] > 190)
        & (alpha > 20)
    )
    rgba[near_white, 0] = 218
    rgba[near_white, 1] = 139
    rgba[near_white, 2] = 158
    result = Image.fromarray(rgba, "RGBA")
    draw = ImageDraw.Draw(result, "RGBA")
    center_x = result.width // 2
    glint_y = max(2, result.height // 3)
    draw.rounded_rectangle(
        (center_x - 6, glint_y, center_x + 6, glint_y + 1),
        radius=1,
        fill=(246, 218, 218, 150),
    )
    return result


def build_i_mouth() -> Image.Image:
    raw = RAW_ROOT / "mouth-vowel-i-subtle-teeth-chroma-v1.png"
    normalized = WORK_ROOT / "mouth-vowel-i-subtle-teeth-normalized-v1.png"
    alpha_path = WORK_ROOT / "mouth-vowel-i-subtle-teeth-alpha-v1.png"
    image = Image.open(raw).convert("RGB").resize(CANVAS, Image.Resampling.LANCZOS)
    normalized.parent.mkdir(parents=True, exist_ok=True)
    image.save(normalized)
    remove_chroma(normalized, alpha_path)
    source = Image.open(alpha_path).convert("RGBA")
    crop = restrain_teeth(source.crop(alpha_bbox(source)))
    aligned = full_canvas_part(crop, MOUTH_I_TARGET)
    aligned.save(PARTS_ROOT / "mouth_vowel_i.png")
    save_guide(aligned, "mouth_vowel_i")
    return aligned


def composite_front(state: str) -> Image.Image:
    frame = Image.open(V10_ROOT / "master/front-faceless-v1.png").convert("RGBA")
    if state in {"neutral", "mouth-small"}:
        for name in ("eye_base_open", "irises"):
            frame.alpha_composite(Image.open(PARTS_ROOT / f"{name}.png").convert("RGBA"))
    else:
        frame.alpha_composite(Image.open(PARTS_ROOT / "eyes_closed.png").convert("RGBA"))
    frame.alpha_composite(Image.open(PARTS_ROOT / "brows_neutral.png").convert("RGBA"))
    mouth_name = "mouth_open_small" if "mouth-small" in state else "mouth_closed"
    frame.alpha_composite(Image.open(PARTS_ROOT / f"{mouth_name}.png").convert("RGBA"))
    return frame


def side_pose(direction: str, state: str, step: str | None = None) -> Image.Image:
    if step is None:
        stem = f"view-{direction}-natural"
    else:
        stem = f"view-{direction}-step-{step}"
    suffix = "" if state == "neutral" else f"-{state}"
    return Image.open(POSES_ROOT / f"{stem}{suffix}-v1.png").convert("RGBA")


def load_small_rgba(image: Image.Image) -> np.ndarray:
    return np.asarray(
        image.resize(FRAME_SIZE, Image.Resampling.LANCZOS),
        dtype=np.float32,
    ) / 255


def matted_gray(rgba: np.ndarray) -> np.ndarray:
    alpha = rgba[..., 3:4]
    rgb = rgba[..., :3] * alpha + MATTE_RGB * (1 - alpha)
    return cv2.cvtColor((rgb * 255).astype(np.uint8), cv2.COLOR_RGB2GRAY)


def optical_flow(first: np.ndarray, second: np.ndarray) -> np.ndarray:
    estimator = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    estimator.setFinestScale(0)
    return estimator.calc(first, second, None)


def warp_rgba(image: np.ndarray, flow: np.ndarray, amount: float) -> np.ndarray:
    width, height = FRAME_SIZE
    grid_x, grid_y = np.meshgrid(
        np.arange(width, dtype=np.float32),
        np.arange(height, dtype=np.float32),
    )
    return cv2.remap(
        image,
        grid_x - amount * flow[..., 0],
        grid_y - amount * flow[..., 1],
        cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    )


def morph_rgba(
    first: np.ndarray,
    second: np.ndarray,
    forward: np.ndarray,
    backward: np.ndarray,
    amount: float,
) -> np.ndarray:
    if amount <= 0:
        return first
    if amount >= 1:
        return second
    warped_first = warp_rgba(first, forward, amount)
    warped_second = warp_rgba(second, backward, 1 - amount)
    mix = amount * amount * (3 - 2 * amount)
    first_pm = warped_first.copy()
    second_pm = warped_second.copy()
    first_pm[..., :3] *= first_pm[..., 3:4]
    second_pm[..., :3] *= second_pm[..., 3:4]
    blended = first_pm * (1 - mix) + second_pm * mix
    alpha = np.clip(blended[..., 3:4], 0, 1)
    rgb = np.where(
        alpha > 1e-5,
        blended[..., :3] / np.maximum(alpha, 1e-5),
        0,
    )
    return np.concatenate([np.clip(rgb, 0, 1), alpha], axis=2)


def direction_anchors(direction: str) -> dict[str, list[Image.Image]]:
    anchors: dict[str, list[Image.Image]] = {}
    for state in STATES:
        if direction == "right":
            anchors[state] = [
                composite_front(state),
                side_pose(direction, state, "25"),
                side_pose(direction, state, "50"),
                side_pose(direction, state),
            ]
        else:
            anchors[state] = [composite_front(state), side_pose(direction, state)]
    return anchors


def create_direction_frames(direction: str) -> dict[str, list[Image.Image]]:
    anchors = direction_anchors(direction)
    neutral = [load_small_rgba(image) for image in anchors["neutral"]]
    flows = []
    for first, second in zip(neutral, neutral[1:]):
        first_gray = matted_gray(first)
        second_gray = matted_gray(second)
        flows.append(
            (
                optical_flow(first_gray, second_gray),
                optical_flow(second_gray, first_gray),
            )
        )

    result: dict[str, list[Image.Image]] = {}
    for state in STATES:
        state_anchors = [load_small_rgba(image) for image in anchors[state]]
        arrays: list[np.ndarray] = []
        if direction == "right":
            for segment, (first, second) in enumerate(
                zip(state_anchors, state_anchors[1:])
            ):
                forward, backward = flows[segment]
                for substep in range(5):
                    arrays.append(
                        morph_rgba(
                            first,
                            second,
                            forward,
                            backward,
                            substep / 5,
                        )
                    )
            arrays.append(state_anchors[-1])
        else:
            forward, backward = flows[0]
            arrays = [
                morph_rgba(
                    state_anchors[0],
                    state_anchors[1],
                    forward,
                    backward,
                    index / (FRAME_COUNT - 1),
                )
                for index in range(FRAME_COUNT)
            ]
        if len(arrays) != FRAME_COUNT:
            raise AssertionError(f"{direction}/{state} built {len(arrays)} frames")
        result[state] = [
            Image.fromarray(
                (np.clip(frame, 0, 1) * 255 + 0.5).astype(np.uint8),
                "RGBA",
            )
            for frame in arrays
        ]
    return result


def scaled_roi(roi: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    scale_x = FRAME_SIZE[0] / CANVAS[0]
    scale_y = FRAME_SIZE[1] / CANVAS[1]
    left, top, right, bottom = roi
    return (
        round(left * scale_x),
        round(top * scale_y),
        round(right * scale_x),
        round(bottom * scale_y),
    )


def expression_patch(
    frame: Image.Image,
    neutral: Image.Image,
    roi: tuple[int, int, int, int],
) -> Image.Image:
    variant_crop = np.asarray(frame.crop(roi).convert("RGBA"), dtype=np.uint8)
    neutral_crop = np.asarray(neutral.crop(roi).convert("RGBA"), dtype=np.uint8)
    difference = np.max(
        np.abs(variant_crop.astype(np.int16) - neutral_crop.astype(np.int16)),
        axis=2,
    )
    mask = np.where(difference > 3, 255, 0).astype(np.uint8)
    mask = cv2.dilate(mask, np.ones((3, 3), dtype=np.uint8), iterations=2)
    mask = cv2.GaussianBlur(mask, (5, 5), 0.8)
    patch = variant_crop.copy()
    patch[..., 3] = np.minimum(patch[..., 3], mask)
    return Image.fromarray(patch, "RGBA")


def save_atlas(
    direction: str,
    state: str,
    frames: list[Image.Image],
    neutral_frames: list[Image.Image],
) -> Path:
    if state == "neutral":
        packed_frames = frames
    else:
        roi = scaled_roi(PATCH_ROIS[direction][state])
        packed_frames = [
            expression_patch(frame, neutral, roi)
            for frame, neutral in zip(frames, neutral_frames)
        ]
    width, height = packed_frames[0].size
    atlas = Image.new(
        "RGBA",
        (width * ATLAS_COLUMNS, height * ATLAS_ROWS),
        (0, 0, 0, 0),
    )
    for index, frame in enumerate(packed_frames):
        x = (index % ATLAS_COLUMNS) * width
        y = (index // ATLAS_COLUMNS) * height
        atlas.alpha_composite(frame, (x, y))
    path = ATLAS_ROOT / f"{direction}-{state}-v1.webp"
    path.parent.mkdir(parents=True, exist_ok=True)
    atlas.save(path, "WEBP", quality=94, method=6, exact=True)
    return path


def build_neck_atlases() -> dict[str, dict[str, list[Image.Image]]]:
    built = {}
    for direction in ("left", "right"):
        frames_by_state = create_direction_frames(direction)
        for state, frames in frames_by_state.items():
            save_atlas(
                direction,
                state,
                frames,
                frames_by_state["neutral"],
            )
        built[direction] = frames_by_state
    for direction in ("left", "right"):
        (ATLAS_ROOT / f"{direction}-blink-mouth-small-v1.webp").unlink(
            missing_ok=True
        )
    return built


def layer_spec(name: str, filename: str, order: int, visible: bool = False) -> dict:
    return {
        "name": name,
        "file": filename,
        "group": "30_mouth",
        "left": 0,
        "top": 0,
        "opacity": 255,
        "visible": visible,
        "order": order,
    }


def update_manifests() -> None:
    path = V10_ROOT / "manifest-live2d-poc-v1.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    layers = [layer for layer in manifest["layers"] if layer["name"] != "mouth_open_micro"]
    for layer in layers:
        if layer["name"] == "mouth_open_small":
            layer["order"] = 32
        elif layer["name"] == "mouth_open_wide":
            layer["order"] = 33
        elif layer["name"].startswith("mouth_vowel_"):
            layer["order"] += 1
    layers.append(
        layer_spec(
            "mouth_open_micro",
            "parts/aligned-v1/mouth_open_micro.png",
            31,
        )
    )
    manifest["layers"] = sorted(layers, key=lambda layer: layer["order"])
    manifest["notes"] = [
        "character-v10 preserves the approved v9 front, natural, and full-turn artwork.",
        "A 62x18 micro-open mouth keyform bridges the closed and small-open mouth drawings.",
        "The I vowel has no broad white teeth plane; only a tiny central pale glint remains.",
        "Head turn review uses sixteen cached keyframes per direction and adjacent-frame interpolation.",
        "Neutral neck atlases use 768x1024 frames; blink and mouth atlases contain cropped face patches only.",
        "Right keyframes use v9 25 and 50 percent anchors; left keyframes interpolate to the approved natural-left endpoint.",
        "The cached neck atlases are a web-review approximation, not Cubism ArtMeshes or deformers.",
        "This PSD is layered animation material and has not been imported in Live2D Cubism.",
    ]
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    base_layers = [
        layer
        for layer in manifest["layers"]
        if layer["name"]
        in {"front_faceless_base", "eye_base_open", "irises", "brows_neutral"}
    ]
    micro_layer = next(
        layer for layer in manifest["layers"] if layer["name"] == "mouth_open_micro"
    )
    micro_state = {
        "canvas": manifest["canvas"],
        "layers": [*base_layers, {**micro_layer, "visible": True}],
    }
    (V10_ROOT / "manifest-state-mouth-micro-v1.json").write_text(
        json.dumps(micro_state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def on_background(frame: Image.Image) -> Image.Image:
    background = Image.new("RGBA", CANVAS, (15, 19, 40, 255))
    background.alpha_composite(frame)
    return background


def render_reviews(
    micro: Image.Image,
    i_mouth: Image.Image,
    neck: dict[str, dict[str, list[Image.Image]]],
) -> None:
    PREVIEWS_ROOT.mkdir(parents=True, exist_ok=True)
    REVIEW_ROOT.mkdir(parents=True, exist_ok=True)

    closed = Image.open(PARTS_ROOT / "mouth_closed.png").convert("RGBA")
    small = Image.open(PARTS_ROOT / "mouth_open_small.png").convert("RGBA")
    mouth_items = [
        ("closed", closed),
        ("micro", micro),
        ("small", small),
        ("I / subtle", i_mouth),
    ]
    crop_box = (410, 500, 676, 690)
    tile = (266, 190)
    mouth_sheet = Image.new("RGBA", (tile[0] * 4, tile[1]), (15, 19, 40, 255))
    draw = ImageDraw.Draw(mouth_sheet)
    for index, (label, mouth) in enumerate(mouth_items):
        mouth_sheet.alpha_composite(
            on_background(composite_front("neutral").copy()).crop(crop_box),
            (index * tile[0], 0),
        )
        # Replace the neutral mouth by compositing the requested layer over the faceless front.
        frame = Image.open(V10_ROOT / "master/front-faceless-v1.png").convert("RGBA")
        for name in ("eye_base_open", "irises", "brows_neutral"):
            frame.alpha_composite(Image.open(PARTS_ROOT / f"{name}.png").convert("RGBA"))
        frame.alpha_composite(mouth)
        mouth_sheet.alpha_composite(on_background(frame).crop(crop_box), (index * tile[0], 0))
        draw.text((index * tile[0] + 12, 10), label, fill="white")
    mouth_path = PREVIEWS_ROOT / "mouth-closed-micro-small-i-v1.png"
    mouth_sheet.save(mouth_path)
    copy_file(mouth_path, REVIEW_ROOT / "tsukuyomi-v10-mouth-keys.png")

    selected = (0, 2, 4, 6, 8, 10, 12, 15)
    panel = (181, 241)
    neck_sheet = Image.new("RGBA", (panel[0] * len(selected), panel[1] * 2), (15, 19, 40, 255))
    neck_draw = ImageDraw.Draw(neck_sheet)
    for row, direction in enumerate(("left", "right")):
        frames = neck[direction]["neutral"]
        for column, index in enumerate(selected):
            background = Image.new("RGBA", FRAME_SIZE, (15, 19, 40, 255))
            background.alpha_composite(frames[index])
            tile_image = background.resize(panel, Image.Resampling.LANCZOS)
            neck_sheet.alpha_composite(tile_image, (column * panel[0], row * panel[1]))
            neck_draw.text(
                (column * panel[0] + 7, row * panel[1] + 7),
                f"{direction} {index}/15",
                fill="white",
            )
    neck_path = PREVIEWS_ROOT / "neck-keyframes-v1.png"
    neck_sheet.save(neck_path)
    copy_file(neck_path, REVIEW_ROOT / "tsukuyomi-v10-neck-keyframes.png")


def main() -> None:
    copy_v9_assets()
    micro = build_micro_mouth()
    i_mouth = build_i_mouth()
    neck = build_neck_atlases()
    update_manifests()
    render_reviews(micro, i_mouth, neck)
    print(f"Built character-v10 assets under {V10_ROOT}")


if __name__ == "__main__":
    main()
