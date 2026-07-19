#!/usr/bin/env python3
"""Build character-v11 with continuous body turns and movable side irises."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

import build_character_v10 as v10


ROOT = Path(__file__).resolve().parents[1]
CANVAS = v10.CANVAS
FRAME_SIZE = v10.FRAME_SIZE
FRAME_COUNT = v10.FRAME_COUNT
ATLAS_COLUMNS = v10.ATLAS_COLUMNS
ATLAS_ROWS = v10.ATLAS_ROWS
V10_ROOT = ROOT / "assets/character-v10"
V11_ROOT = ROOT / "assets/character-v11"
RAW_ROOT = V11_ROOT / "raw/imagegen"
WORK_ROOT = V11_ROOT / "work"
POSES_ROOT = V11_ROOT / "poses"
NECK_ATLAS_ROOT = V11_ROOT / "neck-atlases"
BODY_ATLAS_ROOT = V11_ROOT / "body-atlases"
PREVIEWS_ROOT = V11_ROOT / "previews"
REVIEW_ROOT = ROOT / "output/review"

STATES = ("neutral", "blink", "mouth-small")
PATCH_ROIS = v10.PATCH_ROIS
BODY_INTERVALS = {
    "left": (5, 5, 5),
    "right": (4, 4, 4, 3),
}


def copy_tree(source: Path, target: Path) -> None:
    if not source.exists():
        return
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        destination = target / path.relative_to(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)


def copy_v10_assets() -> None:
    for folder in (
        "master",
        "parts",
        "guides",
        "poses",
        "previews",
        "exports",
    ):
        copy_tree(V10_ROOT / folder, V11_ROOT / folder)
    copy_tree(V10_ROOT / "raw", V11_ROOT / "raw")
    for manifest in sorted(V10_ROOT.glob("manifest-*.json")):
        destination = V11_ROOT / manifest.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(manifest, destination)


def normalize_generated_left_steps() -> None:
    for step in ("33", "66"):
        source = RAW_ROOT / f"body-left-step-{step}-chroma-v1.png"
        if not source.exists():
            raise FileNotFoundError(source)
        normalized = WORK_ROOT / f"body-left-step-{step}-normalized-v1.png"
        alpha = POSES_ROOT / f"view-left-body-step-{step}-v1.png"
        normalized.parent.mkdir(parents=True, exist_ok=True)
        POSES_ROOT.mkdir(parents=True, exist_ok=True)
        Image.open(source).convert("RGB").resize(
            CANVAS,
            Image.Resampling.LANCZOS,
        ).save(normalized)
        v10.remove_chroma(normalized, alpha)
        image = Image.open(alpha).convert("RGBA")
        bbox = v10.alpha_bbox(image)
        if bbox[0] > 140 or bbox[2] < 920 or bbox[3] < 1380:
            raise AssertionError(f"body-left-step-{step} has unexpected bbox {bbox}")


def front(state: str) -> Image.Image:
    return v10.composite_front(state)


def pose(stem: str, state: str) -> Image.Image:
    suffix = "" if state == "neutral" else f"-{state}"
    return Image.open(POSES_ROOT / f"{stem}{suffix}-v1.png").convert("RGBA")


def generated_left(step: str) -> Image.Image:
    return Image.open(
        POSES_ROOT / f"view-left-body-step-{step}-v1.png"
    ).convert("RGBA")


def sequence_neutral_anchors(kind: str, direction: str) -> list[Image.Image]:
    if kind == "neck":
        if direction == "right":
            return [
                front("neutral"),
                pose("view-right-step-25", "neutral"),
                pose("view-right-step-50", "neutral"),
                pose("view-right-natural", "neutral"),
            ]
        return [front("neutral"), pose("view-left-natural", "neutral")]

    if direction == "right":
        return [
            front("neutral"),
            pose("view-right-step-25", "neutral"),
            pose("view-right-step-50", "neutral"),
            pose("view-right-step-80", "neutral"),
            pose("view-right-3q", "neutral"),
        ]
    return [
        front("neutral"),
        generated_left("33"),
        generated_left("66"),
        pose("view-left-3q", "neutral"),
    ]


def sequence_intervals(kind: str, direction: str) -> tuple[int, ...]:
    if kind == "neck":
        return (5, 5, 5) if direction == "right" else (15,)
    return BODY_INTERVALS[direction]


def alpha_composite_arrays(base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
    base_pm = base.copy()
    overlay_pm = overlay.copy()
    base_pm[..., :3] *= base_pm[..., 3:4]
    overlay_pm[..., :3] *= overlay_pm[..., 3:4]
    out_alpha = overlay_pm[..., 3:4] + base_pm[..., 3:4] * (1 - overlay_pm[..., 3:4])
    out_rgb_pm = overlay_pm[..., :3] + base_pm[..., :3] * (1 - overlay_pm[..., 3:4])
    out_rgb = np.where(
        out_alpha > 1e-5,
        out_rgb_pm / np.maximum(out_alpha, 1e-5),
        0,
    )
    return np.concatenate([np.clip(out_rgb, 0, 1), np.clip(out_alpha, 0, 1)], axis=2)


def transfer_expression(
    source_neutral: Image.Image,
    source_variant: Image.Image,
    target_neutral: Image.Image,
    rois: list[tuple[int, int, int, int]],
) -> Image.Image:
    source = v10.load_small_rgba(source_neutral)
    variant = v10.load_small_rgba(source_variant)
    target = v10.load_small_rgba(target_neutral)
    flow = v10.optical_flow(v10.matted_gray(source), v10.matted_gray(target))
    warped_source = v10.warp_rgba(source, flow, 1)
    warped_variant = v10.warp_rgba(variant, flow, 1)
    difference = np.max(np.abs(warped_variant - warped_source), axis=2)
    allowed = np.zeros(difference.shape, dtype=np.uint8)
    for roi in rois:
        left, top, right, bottom = v10.scaled_roi(roi)
        allowed[top:bottom, left:right] = 255
    mask = np.where((difference > 3 / 255) & (allowed > 0), 255, 0).astype(np.uint8)
    mask = cv2.dilate(mask, np.ones((3, 3), dtype=np.uint8), iterations=2)
    mask = cv2.GaussianBlur(mask, (5, 5), 0.8).astype(np.float32) / 255
    overlay = warped_variant.copy()
    overlay[..., 3] *= mask
    result = alpha_composite_arrays(target, overlay)
    return Image.fromarray((np.clip(result, 0, 1) * 255 + 0.5).astype(np.uint8), "RGBA")


def sequence_state_anchors(
    kind: str,
    direction: str,
    state: str,
    neutral_anchors: list[Image.Image],
) -> list[Image.Image]:
    if state == "neutral":
        return neutral_anchors
    if kind == "neck" or direction == "right":
        if kind == "neck" and direction == "left":
            stems = (None, "view-left-natural")
        elif kind == "neck":
            stems = (
                None,
                "view-right-step-25",
                "view-right-step-50",
                "view-right-natural",
            )
        else:
            stems = (
                None,
                "view-right-step-25",
                "view-right-step-50",
                "view-right-step-80",
                "view-right-3q",
            )
        return [front(state) if stem is None else pose(stem, state) for stem in stems]

    source_rois = [PATCH_ROIS["left"]["blink" if state == "blink" else "mouth-small"]]
    natural_neutral = pose("view-left-natural", "neutral")
    natural_variant = pose("view-left-natural", state)
    full_neutral = pose("view-left-3q", "neutral")
    full_variant = pose("view-left-3q", state)
    return [
        front(state),
        transfer_expression(
            natural_neutral,
            natural_variant,
            neutral_anchors[1],
            source_rois,
        ),
        transfer_expression(
            full_neutral,
            full_variant,
            neutral_anchors[2],
            source_rois,
        ),
        full_variant,
    ]


def build_flows(neutral_arrays: list[np.ndarray]) -> list[tuple[np.ndarray, np.ndarray]]:
    result = []
    for first, second in zip(neutral_arrays, neutral_arrays[1:]):
        result.append(
            (
                v10.optical_flow(v10.matted_gray(first), v10.matted_gray(second)),
                v10.optical_flow(v10.matted_gray(second), v10.matted_gray(first)),
            )
        )
    return result


def interpolate_arrays(
    anchors: list[np.ndarray],
    flows: list[tuple[np.ndarray, np.ndarray]],
    intervals: tuple[int, ...],
) -> list[np.ndarray]:
    frames: list[np.ndarray] = []
    for segment, (first, second) in enumerate(zip(anchors, anchors[1:])):
        forward, backward = flows[segment]
        for substep in range(intervals[segment]):
            frames.append(
                v10.morph_rgba(
                    first,
                    second,
                    forward,
                    backward,
                    substep / intervals[segment],
                )
            )
    frames.append(anchors[-1])
    if len(frames) != FRAME_COUNT:
        raise AssertionError(f"sequence built {len(frames)} frames")
    return frames


def build_iris_mask_frames(
    flows: list[tuple[np.ndarray, np.ndarray]],
    intervals: tuple[int, ...],
) -> list[np.ndarray]:
    iris = np.asarray(
        Image.open(V11_ROOT / "parts/aligned-v1/irises.png")
        .convert("RGBA")
        .resize(FRAME_SIZE, Image.Resampling.LANCZOS),
        dtype=np.float32,
    )[..., 3] / 255
    current = iris
    masks: list[np.ndarray] = []
    for segment, (forward, _backward) in enumerate(flows):
        rgba = np.zeros((*current.shape, 4), dtype=np.float32)
        rgba[..., 3] = current
        for substep in range(intervals[segment]):
            amount = substep / intervals[segment]
            masks.append(v10.warp_rgba(rgba, forward, amount)[..., 3])
        current = v10.warp_rgba(rgba, forward, 1)[..., 3]
    masks.append(current)
    if len(masks) != FRAME_COUNT:
        raise AssertionError(f"iris sequence built {len(masks)} masks")
    return masks


def build_eye_patches(
    neutral_frames: list[Image.Image],
    iris_masks: list[np.ndarray],
    direction: str,
) -> tuple[list[Image.Image], list[Image.Image]]:
    roi = v10.scaled_roi(PATCH_ROIS[direction]["blink"])
    eye_bases = []
    irises = []
    for frame, raw_mask in zip(neutral_frames, iris_masks):
        rgba = np.asarray(frame.convert("RGBA"), dtype=np.uint8)
        core = np.where(raw_mask > 0.08, 255, 0).astype(np.uint8)
        core = cv2.morphologyEx(core, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
        cover = cv2.dilate(core, np.ones((3, 3), np.uint8), iterations=2)
        feather = cv2.GaussianBlur(cover, (5, 5), 0.8)
        rgb = cv2.inpaint(rgba[..., :3], cover, 4, cv2.INPAINT_TELEA)

        eye_base = np.dstack([rgb, np.minimum(rgba[..., 3], feather)])
        iris_layer = rgba.copy()
        iris_layer[..., 3] = np.minimum(rgba[..., 3], feather)
        eye_bases.append(Image.fromarray(eye_base, "RGBA").crop(roi))
        irises.append(Image.fromarray(iris_layer, "RGBA").crop(roi))
    return eye_bases, irises


def image_from_array(array: np.ndarray) -> Image.Image:
    return Image.fromarray(
        (np.clip(array, 0, 1) * 255 + 0.5).astype(np.uint8),
        "RGBA",
    )


def save_atlas(path: Path, frames: list[Image.Image]) -> None:
    width, height = frames[0].size
    atlas = Image.new(
        "RGBA",
        (width * ATLAS_COLUMNS, height * ATLAS_ROWS),
        (0, 0, 0, 0),
    )
    for index, frame in enumerate(frames):
        x = (index % ATLAS_COLUMNS) * width
        y = (index // ATLAS_COLUMNS) * height
        atlas.alpha_composite(frame, (x, y))
    path.parent.mkdir(parents=True, exist_ok=True)
    atlas.save(path, "WEBP", quality=94, method=6, exact=True)


def build_sequence(kind: str, direction: str) -> dict[str, list[Image.Image]]:
    neutral_anchors = sequence_neutral_anchors(kind, direction)
    intervals = sequence_intervals(kind, direction)
    neutral_arrays = [v10.load_small_rgba(image) for image in neutral_anchors]
    flows = build_flows(neutral_arrays)
    neutral_array_frames = interpolate_arrays(neutral_arrays, flows, intervals)
    neutral_frames = [image_from_array(array) for array in neutral_array_frames]

    state_frames = {"neutral": neutral_frames}
    for state in ("blink", "mouth-small"):
        anchors = sequence_state_anchors(
            kind,
            direction,
            state,
            neutral_anchors,
        )
        arrays = [v10.load_small_rgba(image) for image in anchors]
        state_frames[state] = [
            image_from_array(array)
            for array in interpolate_arrays(arrays, flows, intervals)
        ]

    atlas_root = NECK_ATLAS_ROOT if kind == "neck" else BODY_ATLAS_ROOT
    save_atlas(atlas_root / f"{direction}-neutral-v1.webp", neutral_frames)
    for state in ("blink", "mouth-small"):
        roi = v10.scaled_roi(PATCH_ROIS[direction][state])
        patches = [
            v10.expression_patch(frame, neutral, roi)
            for frame, neutral in zip(state_frames[state], neutral_frames)
        ]
        save_atlas(atlas_root / f"{direction}-{state}-v1.webp", patches)

    iris_masks = build_iris_mask_frames(flows, intervals)
    eye_bases, irises = build_eye_patches(neutral_frames, iris_masks, direction)
    save_atlas(atlas_root / f"{direction}-eye-base-v1.webp", eye_bases)
    save_atlas(atlas_root / f"{direction}-irises-v1.webp", irises)
    state_frames["eye-base"] = eye_bases
    state_frames["irises"] = irises
    return state_frames


def update_manifest() -> None:
    path = V11_ROOT / "manifest-live2d-poc-v1.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["notes"] = [
        "character-v11 preserves the approved v10 front face and mouth artwork, including the current I vowel pending a user sample.",
        "Head and body turns each use sixteen cached keyframes per direction with adjacent-frame interpolation.",
        "Two generated left body-turn anchors reduce long optical-flow spans before the approved full-left endpoint.",
        "Side eye patches separate an inpainted eye base and movable irises for gaze tracking during neck and body turns.",
        "Blink and small-mouth changes remain cropped face patches and can run with gaze tracking.",
        "The core Web rig no longer loads twenty-eight full-pose PNG variants at startup.",
        "This remains a cached raster review rig, not Cubism ArtMeshes or deformers.",
        "The layered PSD is unchanged from v10 and has not been imported in Live2D Cubism.",
    ]
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def render_reviews(sequences: dict[tuple[str, str], dict[str, list[Image.Image]]]) -> None:
    PREVIEWS_ROOT.mkdir(parents=True, exist_ok=True)
    REVIEW_ROOT.mkdir(parents=True, exist_ok=True)
    selected = (0, 2, 4, 6, 8, 10, 12, 15)
    panel = (181, 241)
    sheet = Image.new(
        "RGBA",
        (panel[0] * len(selected), panel[1] * 2),
        (15, 19, 40, 255),
    )
    draw = ImageDraw.Draw(sheet)
    for row, direction in enumerate(("left", "right")):
        frames = sequences[("body", direction)]["neutral"]
        for column, index in enumerate(selected):
            background = Image.new("RGBA", FRAME_SIZE, (15, 19, 40, 255))
            background.alpha_composite(frames[index])
            sheet.alpha_composite(
                background.resize(panel, Image.Resampling.LANCZOS),
                (column * panel[0], row * panel[1]),
            )
            draw.text(
                (column * panel[0] + 7, row * panel[1] + 7),
                f"body {direction} {index}/15",
                fill="white",
            )
    path = PREVIEWS_ROOT / "body-keyframes-v1.png"
    sheet.save(path)
    shutil.copy2(path, REVIEW_ROOT / "tsukuyomi-v11-body-keyframes.png")


def main() -> None:
    copy_v10_assets()
    normalize_generated_left_steps()
    sequences = {}
    for kind in ("neck", "body"):
        for direction in ("left", "right"):
            sequences[(kind, direction)] = build_sequence(kind, direction)
    update_manifest()
    render_reviews(sequences)
    print(f"Built character-v11 assets under {V11_ROOT}")


if __name__ == "__main__":
    main()
