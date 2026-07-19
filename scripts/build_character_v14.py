#!/usr/bin/env python3
"""Build character-v14 with reference irises and lossless side-eye layers."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

import build_character_v10 as v10
import build_character_v11 as v11
import build_character_v13 as v13


ROOT = Path(__file__).resolve().parents[1]
V13_ROOT = ROOT / "assets/character-v13"
V14_ROOT = ROOT / "assets/character-v14"
NECK_ATLAS_ROOT = V14_ROOT / "neck-atlases"
BODY_ATLAS_ROOT = V14_ROOT / "body-atlases"
PREVIEWS_ROOT = V14_ROOT / "previews"
WORK_ROOT = V14_ROOT / "work"
FRAME_SIZE = v11.FRAME_SIZE
FRAME_COUNT = v11.FRAME_COUNT
ATLAS_COLUMNS = v11.ATLAS_COLUMNS
ATLAS_ROWS = v11.ATLAS_ROWS

REFERENCE_GREEN = (
    ROOT / "assets/character-v5/raw/source/identity-green-reference.png"
)
REFERENCE_HERO = (
    ROOT / "assets/character-v5/raw/source/identity-hero-reference.png"
)
REFERENCE_IRIS_ROIS = (
    (405, 454, 481, 529),
    (599, 448, 681, 523),
)
FRONT_IRIS_CENTERS = ((455, 478), (630, 478))
FRONT_IRIS_SIZE = (50, 51)

ELLIPSE_3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
ELLIPSE_5 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
ELLIPSE_7 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
ELLIPSE_11 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
SCLERA_FALLBACK_RGB = np.array([252, 242, 241], dtype=np.uint8)
FRONT_LEFT_EYE_BOX = (388, 446, 498, 507)
FRONT_RIGHT_EYE_BOX = (588, 446, 698, 507)
FRONT_UPPER_LID_BOTTOM = 480
FRONT_MOUTH_NAMES = (
    "mouth_closed",
    "mouth_open_micro",
    "mouth_open_small",
    "mouth_open_wide",
    "mouth_vowel_a",
    "mouth_vowel_i",
    "mouth_vowel_u",
    "mouth_vowel_e",
    "mouth_vowel_o",
)
FRONT_MOUTH_SHIFT_X = 4
FRONT_LEFT_LID_ANCHORS = ((389, 471), (496, 474))
FRONT_LID_WORK_Y = (430, 510)


@dataclass(frozen=True)
class IrisShape:
    mask: np.ndarray
    lash_guard: np.ndarray
    lower_guard: np.ndarray
    center: tuple[int, int]
    bbox: tuple[int, int, int, int]


def copy_v13_assets() -> None:
    if not V13_ROOT.exists():
        raise FileNotFoundError(V13_ROOT)
    V14_ROOT.mkdir(parents=True, exist_ok=True)
    for source in sorted(V13_ROOT.rglob("*")):
        if not source.is_file():
            continue
        destination = V14_ROOT / source.relative_to(V13_ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def _save_alpha_guide(layer: Image.Image, name: str) -> None:
    guide = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    guide.paste((255, 255, 255, 255), (0, 0), layer.getchannel("A"))
    guide.save(V14_ROOT / f"guides/{name}-guide.png", "PNG", optimize=True)


def refine_front_eye_and_mouth_parts() -> None:
    """Apply only the approved front eyelid symmetry and mouth-X corrections."""
    parts_root = V14_ROOT / "parts/aligned-v1"
    eye_path = parts_root / "eye_base_open.png"
    eye = np.asarray(Image.open(eye_path).convert("RGBA"), dtype=np.uint8).copy()
    left, top, right, _bottom = FRONT_LEFT_EYE_BOX
    right_left, right_top, right_right, _right_bottom = FRONT_RIGHT_EYE_BOX
    if top != right_top or (right - left) != (right_right - right_left):
        raise ValueError("Front eye boxes lost their mirrored geometry")
    upper = eye[top:FRONT_UPPER_LID_BOTTOM, left:right].copy()
    eye[right_top:FRONT_UPPER_LID_BOTTOM, right_left:right_right] = np.flip(
        upper,
        axis=1,
    )
    eye_layer = Image.fromarray(eye, "RGBA")
    eye_layer.save(eye_path, "PNG", optimize=True)
    _save_alpha_guide(eye_layer, "eye_base_open")

    for name in FRONT_MOUTH_NAMES:
        path = parts_root / f"{name}.png"
        source = Image.open(path).convert("RGBA")
        shifted = Image.new("RGBA", source.size, (0, 0, 0, 0))
        shifted.alpha_composite(source, (FRONT_MOUTH_SHIFT_X, 0))
        shifted.save(path, "PNG", optimize=True)
        _save_alpha_guide(shifted, name)


def _front_lid_curve(xs: np.ndarray, state: str) -> np.ndarray:
    (outer_x, outer_y), (inner_x, inner_y) = FRONT_LEFT_LID_ANCHORS
    u = np.clip((xs - outer_x) / (inner_x - outer_x), 0.0, 1.0)
    baseline = outer_y + (inner_y - outer_y) * u
    arch = np.maximum(0.0, np.sin(np.pi * u)) ** 0.85
    open_curve = baseline - 19.0 * arch
    closed_curve = baseline + 19.0 * arch
    if state == "open":
        return open_curve
    if state == "half":
        return (open_curve + closed_curve) / 2.0
    if state == "closed":
        return closed_curve
    raise ValueError(f"Unknown front lid state: {state}")


def _warp_left_upper_lid(
    eye_layer: np.ndarray,
    state: str,
) -> np.ndarray:
    left, _top, right, _bottom = FRONT_LEFT_EYE_BOX
    work_top, work_bottom = FRONT_LID_WORK_Y
    source = eye_layer[work_top:work_bottom, left:right].copy()
    hsv = cv2.cvtColor(source[..., :3], cv2.COLOR_RGB2HSV)
    local_y, local_x = np.indices(source.shape[:2])
    global_y = local_y + work_top
    global_x = local_x + left
    upper_line = (
        (source[..., 3] > 0)
        & (global_y <= 482)
        & ((hsv[..., 2] < 230) | (hsv[..., 1] >= 24))
    )
    source[..., 3] = np.where(upper_line, source[..., 3], 0).astype(np.uint8)

    xs = np.arange(left, right, dtype=np.float32)
    source_curve = _front_lid_curve(xs, "open")
    target_curve = _front_lid_curve(xs, state)
    vertical_scale = 0.88 if state == "half" else 0.78
    output_y, output_x = np.indices(source.shape[:2], dtype=np.float32)
    output_global_y = output_y + work_top
    source_global_y = source_curve[np.newaxis, :] + (
        output_global_y - target_curve[np.newaxis, :]
    ) / vertical_scale
    map_y = source_global_y - work_top
    warped = cv2.remap(
        source,
        output_x,
        map_y.astype(np.float32),
        interpolation=cv2.INTER_LANCZOS4,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0, 0),
    )
    return warped


def build_front_blink_keys() -> tuple[Image.Image, Image.Image]:
    """Build a half-lid cover and a mirrored closed line with fixed corners."""
    parts_root = V14_ROOT / "parts/aligned-v1"
    eye = np.asarray(
        Image.open(parts_root / "eye_base_open.png").convert("RGBA"),
        dtype=np.uint8,
    )
    master = np.asarray(
        Image.open(V14_ROOT / "master/front-faceless-v1.png").convert("RGBA"),
        dtype=np.uint8,
    )
    left, _top, right, _bottom = FRONT_LEFT_EYE_BOX
    right_left, _right_top, right_right, _right_bottom = FRONT_RIGHT_EYE_BOX
    work_top, work_bottom = FRONT_LID_WORK_Y

    half_line_left = _warp_left_upper_lid(eye, "half")
    closed_line_left = _warp_left_upper_lid(eye, "closed")
    half_line = np.zeros_like(eye)
    closed_line = np.zeros_like(eye)
    half_line[work_top:work_bottom, left:right] = half_line_left
    closed_line[work_top:work_bottom, left:right] = closed_line_left
    half_line[
        work_top:work_bottom,
        right_left:right_right,
    ] = np.flip(half_line_left, axis=1)
    closed_line[
        work_top:work_bottom,
        right_left:right_right,
    ] = np.flip(closed_line_left, axis=1)

    cover_mask = np.zeros(eye.shape[:2], dtype=bool)
    left_xs = np.arange(left, right, dtype=np.float32)
    half_curve = np.rint(_front_lid_curve(left_xs, "half")).astype(int)
    for local_x, bottom_y in enumerate(half_curve):
        cover_mask[440 : min(work_bottom, bottom_y + 1), left + local_x] = True
    right_cover = np.flip(cover_mask[:, left:right], axis=1)
    cover_mask[:, right_left:right_right] |= right_cover

    half = np.zeros_like(eye)
    half[cover_mask] = master[cover_mask]
    half_image = Image.fromarray(half, "RGBA")
    half_image.alpha_composite(Image.fromarray(half_line, "RGBA"))
    closed_image = Image.fromarray(closed_line, "RGBA")

    half_path = parts_root / "eyes_half_closed.png"
    closed_path = parts_root / "eyes_closed.png"
    half_image.save(half_path, "PNG", optimize=True)
    closed_image.save(closed_path, "PNG", optimize=True)
    _save_alpha_guide(half_image, "eyes_half_closed")
    _save_alpha_guide(closed_image, "eyes_closed")
    return half_image, closed_image


def _largest_component_near(
    mask: np.ndarray,
    target: np.ndarray,
    minimum_area: int = 30,
) -> np.ndarray:
    count, labels, stats, _centroids = cv2.connectedComponentsWithStats(mask)
    candidates = []
    target_bool = target > 0
    for label in range(1, count):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area < minimum_area:
            continue
        component = labels == label
        overlap = int(np.count_nonzero(component & target_bool))
        candidates.append((overlap, area, label))
    if not candidates:
        raise ValueError("No painted iris component matched its propagated prior")
    _overlap, _area, selected = max(candidates)
    return np.where(labels == selected, 255, 0).astype(np.uint8)


def _filled_hull(mask: np.ndarray) -> np.ndarray:
    points = np.column_stack(np.where(mask > 0)[::-1]).astype(np.int32)
    if len(points) < 3:
        raise ValueError("Iris seed is too small")
    result = np.zeros_like(mask, dtype=np.uint8)
    cv2.fillConvexPoly(result, cv2.convexHull(points), 255)
    return result


def _alpha_bbox(alpha: np.ndarray, threshold: int = 20) -> tuple[int, int, int, int]:
    ys, xs = np.where(alpha > threshold)
    if len(xs) == 0:
        raise ValueError("Iris alpha is empty")
    return int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)


def _extract_reference_irises() -> tuple[Image.Image, Image.Image]:
    """Extract the direct-gaze dark and luminous irises from the user references."""
    green = np.asarray(Image.open(REFERENCE_GREEN).convert("RGB"), dtype=np.uint8)
    hero = np.asarray(Image.open(REFERENCE_HERO).convert("RGB"), dtype=np.uint8)
    green_hsv = cv2.cvtColor(green, cv2.COLOR_RGB2HSV)
    textures = []

    for index, (left, top, right, bottom) in enumerate(REFERENCE_IRIS_ROIS):
        local_hsv = green_hsv[top:bottom, left:right]
        yy = np.indices(local_hsv.shape[:2])[0]
        purple = (
            (local_hsv[..., 0] >= 104)
            & (local_hsv[..., 0] <= 175)
            & (local_hsv[..., 1] >= 42)
            & (local_hsv[..., 2] >= 55)
            & (yy >= 10)
        )
        seed = cv2.morphologyEx(
            np.where(purple, 255, 0).astype(np.uint8),
            cv2.MORPH_OPEN,
            ELLIPSE_3,
        )
        count, labels, stats, centroids = cv2.connectedComponentsWithStats(seed)
        candidates = [
            label
            for label in range(1, count)
            if stats[label, cv2.CC_STAT_AREA] >= 150
            and centroids[label][1] >= 20
        ]
        if not candidates:
            raise ValueError(f"Reference iris {index} was not detected")
        selected = max(candidates, key=lambda label: stats[label, cv2.CC_STAT_AREA])
        support = _filled_hull(
            np.where(labels == selected, 255, 0).astype(np.uint8)
        )
        x0, y0, x1, y1 = _alpha_bbox(support)

        # The green reference supplies the straight-on geometry and pale ring.
        # The hero reference is sampled as a palette guard so the luminous eye
        # cannot accidentally collapse to the dark-eye treatment during rebuilds.
        source_rgb = green[top:bottom, left:right]
        crop_rgb = source_rgb[y0:y1, x0:x1].copy()
        crop_alpha = support[y0:y1, x0:x1]
        if index == 1:
            hero_roi = hero[485:570, 620:720]
            hero_hsv = cv2.cvtColor(hero_roi, cv2.COLOR_RGB2HSV)
            hero_luminous = hero_roi[
                (hero_hsv[..., 1] < 115) & (hero_hsv[..., 2] > 170)
            ]
            if len(hero_luminous) < 20:
                raise ValueError("Hero reference lost its luminous left-eye palette")
        if index == 1:
            # Keep the approved lavender palette while reinforcing the pale
            # moon ring that identifies the character-left eye.  Limit the
            # adjustment to pixels that are already pale in the reference and
            # to the upper/middle iris so it cannot recreate a white lower
            # wedge.
            crop_hsv = cv2.cvtColor(crop_rgb, cv2.COLOR_RGB2HSV)
            crop_y = np.indices(crop_alpha.shape)[0]
            pale_ring = (
                (crop_alpha > 20)
                & (crop_hsv[..., 1] < 135)
                & (crop_hsv[..., 2] > 150)
                & (crop_y < crop_alpha.shape[0] * 0.72)
            )
            moon_lavender = np.array([235, 220, 250], dtype=np.float32)
            crop_rgb[pale_ring] = np.clip(
                crop_rgb[pale_ring].astype(np.float32) * 0.72
                + moon_lavender * 0.28,
                0,
                255,
            ).astype(np.uint8)

        rgba = np.dstack([crop_rgb, crop_alpha])
        textures.append(Image.fromarray(rgba, "RGBA"))

    return tuple(textures)


def _center_component(
    image: Image.Image,
    expected_center: tuple[int, int],
) -> Image.Image:
    alpha = np.asarray(image.getchannel("A"), dtype=np.uint8)
    ys, xs = np.where(alpha > 20)
    shift_x = int(round(expected_center[0] - float(xs.mean())))
    shift_y = int(round(expected_center[1] - float(ys.mean())))
    result = Image.new("RGBA", image.size, (0, 0, 0, 0))
    result.alpha_composite(image, (shift_x, shift_y))
    return result


def build_front_reference_irises() -> Image.Image:
    textures = _extract_reference_irises()
    result = Image.new("RGBA", v10.CANVAS, (0, 0, 0, 0))
    for texture, center in zip(textures, FRONT_IRIS_CENTERS):
        resized = texture.resize(FRONT_IRIS_SIZE, Image.Resampling.LANCZOS)
        local = Image.new("RGBA", v10.CANVAS, (0, 0, 0, 0))
        local.alpha_composite(
            resized,
            (
                center[0] - FRONT_IRIS_SIZE[0] // 2,
                center[1] - FRONT_IRIS_SIZE[1] // 2,
            ),
        )
        result.alpha_composite(_center_component(local, center))

    target = V14_ROOT / "parts/aligned-v1/irises.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    result.save(target, "PNG", optimize=True)
    guide = Image.new("RGBA", result.size, (0, 0, 0, 0))
    guide.paste((255, 255, 255, 255), (0, 0), result.getchannel("A"))
    guide.save(V14_ROOT / "guides/irises-guide.png", "PNG", optimize=True)

    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    for label, texture in zip(("dark", "luminous"), textures):
        texture.save(WORK_ROOT / f"reference-iris-{label}-v1.png")
    return result


def _configure_build_roots() -> None:
    v10.V10_ROOT = V14_ROOT
    v10.PARTS_ROOT = V14_ROOT / "parts/aligned-v1"
    v10.POSES_ROOT = V14_ROOT / "poses"
    v11.V11_ROOT = V14_ROOT
    v11.RAW_ROOT = V14_ROOT / "raw/imagegen"
    v11.WORK_ROOT = V14_ROOT / "work"
    v11.POSES_ROOT = V14_ROOT / "poses"
    v11.NECK_ATLAS_ROOT = NECK_ATLAS_ROOT
    v11.BODY_ATLAS_ROOT = BODY_ATLAS_ROOT


def _neutral_sequence(kind: str, direction: str):
    _configure_build_roots()
    anchors = v11.sequence_neutral_anchors(kind, direction)
    intervals = v11.sequence_intervals(kind, direction)
    arrays = [v10.load_small_rgba(image) for image in anchors]
    flows = v11.build_flows(arrays)
    frames = [
        v11.image_from_array(array)
        for array in v11.interpolate_arrays(arrays, flows, intervals)
    ]
    if kind == "body" and direction == "right":
        frames = v13._repair_body_right_cheek(frames)
    masks = v11.build_iris_mask_frames(flows, intervals)
    return frames, masks


def _profile(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    top = np.full(mask.shape[1], np.nan)
    bottom = np.full(mask.shape[1], np.nan)
    for x in np.where(mask.any(axis=0))[0]:
        ys = np.where(mask[:, x])[0]
        top[x] = ys.min()
        bottom[x] = ys.max()
    known = np.where(~np.isnan(top))[0]
    if len(known) == 0:
        raise ValueError("Iris profile is empty")
    x_axis = np.arange(mask.shape[1])
    return (
        np.interp(x_axis, known, top[known]),
        np.interp(x_axis, known, bottom[known]),
    )


def detect_side_iris_shapes(
    frame: Image.Image,
    raw_mask: np.ndarray,
) -> list[IrisShape]:
    rgba = np.asarray(frame.convert("RGBA"), dtype=np.uint8)
    hsv = cv2.cvtColor(rgba[..., :3], cv2.COLOR_RGB2HSV)
    strong_purple = (
        (hsv[..., 0] >= 104)
        & (hsv[..., 0] <= 175)
        & (hsv[..., 1] >= 45)
        & (hsv[..., 2] >= 58)
        & (rgba[..., 3] > 20)
    )
    dark_colored = (
        (hsv[..., 2] < 112)
        & (hsv[..., 1] >= 28)
        & (rgba[..., 3] > 20)
    )
    line_colored = (
        ((hsv[..., 2] < 145) & (hsv[..., 1] >= 12))
        | (
            (hsv[..., 0] >= 100)
            & (hsv[..., 0] <= 179)
            & (hsv[..., 1] >= 36)
            & (hsv[..., 2] < 205)
        )
    )
    yy = np.indices(hsv.shape[:2])[0]
    shapes = []

    for raw_component in v13._seed_components(raw_mask):
        # Optical-flow interpolation can shed a tiny disconnected tail below
        # an eye.  It is not a third iris and must not become a movable layer.
        if int(np.count_nonzero(raw_component)) < 50:
            continue
        aligned = v13._align_component_to_painted_iris(
            raw_component,
            strong_purple,
            dark_colored,
        )
        search = cv2.dilate(aligned, ELLIPSE_7, iterations=2)
        painted_seed = np.where(
            (search > 0) & strong_purple,
            255,
            0,
        ).astype(np.uint8)
        seed = cv2.morphologyEx(
            painted_seed,
            cv2.MORPH_OPEN,
            ELLIPSE_3,
        )
        # Far-body interpolation can make the foreshortened iris only one or
        # two pixels thick, so a 3x3 opening may erase it.  Fall back to the
        # un-opened painted seed while still selecting by propagated overlap.
        try:
            selected = _largest_component_near(seed, aligned, minimum_area=30)
        except ValueError:
            selected = _largest_component_near(
                painted_seed,
                aligned,
                minimum_area=10,
            )
        iris = _filled_hull(selected) > 0
        # A propagated mask is an alignment prior, not ownership. This guard
        # keeps the hull on the eye even when a dark upper lash touches it.
        local_prior = cv2.dilate(aligned, ELLIPSE_5, iterations=2) > 0
        iris &= local_prior
        iris = cv2.morphologyEx(
            np.where(iris, 255, 0).astype(np.uint8),
            cv2.MORPH_CLOSE,
            ELLIPSE_3,
        ) > 0

        # Generated 3/4 views clip the far iris against the eye socket.  When
        # that asymmetric silhouette is translated, its missing lower half
        # exposes a conspicuous white wedge.  Complete only the lower half of
        # the inscribed ellipse, inside the existing bbox, so neither the iris
        # center nor its outer dimensions can drift.
        iris_left, iris_top, iris_right, iris_bottom = _alpha_bbox(
            np.where(iris, 255, 0).astype(np.uint8)
        )
        local_height = iris_bottom - iris_top
        local_width = iris_right - iris_left
        local_y, local_x = np.indices((local_height, local_width))
        center_x = (local_width - 1) / 2.0
        center_y = (local_height - 1) / 2.0
        radius_x = max(1.0, local_width / 2.0)
        radius_y = max(1.0, local_height / 2.0)
        lower_ellipse = (
            ((local_x - center_x) / radius_x) ** 2
            + ((local_y - center_y) / radius_y) ** 2
            <= 1.0
        ) & (local_y >= center_y)
        iris[
            iris_top:iris_bottom,
            iris_left:iris_right,
        ] |= lower_ellipse

        # Fill only the consecutive neutral-sclera rows between the detected
        # iris and the source lower lid.  This is normally one or two pixels
        # (three at the clipped far-eye corner) and stops before any colored
        # lid/skin pixel, so the iris meets rather than covers the lower line.
        bright_sclera = (
            (hsv[..., 1] <= 20)
            & (hsv[..., 2] >= 205)
            & (rgba[..., 3] > 20)
        )
        for x in range(iris_left, iris_right):
            column = np.where(iris[:, x])[0]
            if len(column) == 0:
                continue
            lower = int(column.max())
            for y in range(lower + 1, min(iris.shape[0], lower + 4)):
                if not bright_sclera[y, x]:
                    break
                iris[y, x] = True
        # One final downward ownership row absorbs the curvature mismatch
        # when this raster iris moves five pixels sideways.  The fixed lower
        # surface computed below is composited afterward, so this row cannot
        # cover the actual lid.
        for _step in range(2):
            downward = np.zeros_like(iris)
            downward[1:] = iris[:-1]
            iris |= downward & (yy >= center_y + iris_top)

        outer = cv2.dilate(
            np.where(iris, 255, 0).astype(np.uint8),
            ELLIPSE_7,
            iterations=2,
        ) > 0
        # The upper lid is a horizontal ridge.  Following the iris' per-column
        # top made the corridor dive down at a foreshortened eye's outer edge:
        # it missed the real lash while promoting vertical iris fragments to a
        # fixed line.  Anchor the corridor to the iris' global top instead.
        global_top = int(np.where(iris)[0].min())
        top_lash_candidate = (
            outer
            & line_colored
            # A few darkest antialiased lash-core pixels overlap the top row
            # of the detected iris hull.  Keep only that near-black overlap;
            # medium purple belongs to the movable iris.
            & (~iris | (hsv[..., 2] < 80))
            & (yy >= global_top - 10)
            & (yy <= global_top + 2)
        )
        # Generated frames occasionally leave one-pixel dark specks near the
        # eye.  They are not a continuous lash and would look like floating
        # noise once the iris moves.
        component_count, component_labels, component_stats, _ = (
            cv2.connectedComponentsWithStats(
                np.where(top_lash_candidate, 255, 0).astype(np.uint8)
            )
        )
        top_lash = np.zeros(top_lash_candidate.shape, dtype=bool)
        for label in range(1, component_count):
            if int(component_stats[label, cv2.CC_STAT_AREA]) >= 6:
                top_lash |= component_labels == label
        # Once the clipped lower iris has been completed, the first colored
        # rows beneath its per-column bottom are the actual lower lid/skin,
        # not a floating iris fragment.  Preserve those source pixels above
        # the movable iris.  This also prevents sclera cleanup from painting
        # the lower lid white.
        _top_profile, bottom_profile = _profile(iris)
        non_sclera_surface = (
            (rgba[..., 3] > 20)
            & ((hsv[..., 1] > 20) | (hsv[..., 2] < 205))
        )
        lower_surface = (
            outer
            & non_sclera_surface
            & (yy > bottom_profile[np.newaxis, :])
            & (yy <= bottom_profile[np.newaxis, :] + 4)
        )
        line_guard = top_lash | lower_surface
        # The lower surface is a foreground occluder, not a hole baked into
        # the moving iris.  Cutting it out here would move that hole with gaze
        # and recreate a white notch at the opposite side of the eye.
        iris &= ~top_lash
        left, top_y, right, bottom_y = _alpha_bbox(
            np.where(iris, 255, 0).astype(np.uint8)
        )
        center = (
            int(round((left + right - 1) / 2)),
            int(round((top_y + bottom_y - 1) / 2)),
        )
        shapes.append(
            IrisShape(
                mask=iris,
                lash_guard=top_lash,
                lower_guard=lower_surface,
                center=center,
                bbox=(left, top_y, right, bottom_y),
            )
        )

    shapes.sort(key=lambda shape: shape.center[0])
    if len(shapes) != 2:
        raise ValueError(f"Expected two side irises, got {len(shapes)}")
    return shapes


def _resize_reference_to_shape(
    texture: Image.Image,
    shape: IrisShape,
) -> np.ndarray:
    left, top, right, bottom = shape.bbox
    width = right - left
    height = bottom - top
    resized = np.asarray(
        texture.resize((width, height), Image.Resampling.LANCZOS),
        dtype=np.uint8,
    ).copy()
    target = np.where(
        shape.mask[top:bottom, left:right],
        255,
        0,
    ).astype(np.uint8)
    # A hard binary ownership mask produced a visible saw-tooth edge once the
    # 768x1024 side frame was enlarged in the browser.  Feather only the final
    # alpha edge; the fixed line guard is still removed after placement.
    soft_target = cv2.GaussianBlur(
        target,
        (0, 0),
        0.65,
        borderType=cv2.BORDER_CONSTANT,
    )
    # Keep every owned iris pixel opaque.  Feathering *inside* the silhouette
    # blended the white eye-base through the purple edge and looked like a
    # sticker-like white outline, especially along the lower lid.  The soft
    # alpha now lives only outside the owned silhouette.
    resized[..., 3] = soft_target
    resized[..., 3][target > 0] = 255
    return resized


def _sclera_fill(
    rgb: np.ndarray,
    alpha: np.ndarray,
    erase: np.ndarray,
    line_guard: np.ndarray,
) -> np.ndarray:
    erase_u8 = np.where(erase & ~line_guard, 255, 0).astype(np.uint8)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    result = rgb.copy()
    count, labels, stats, _centroids = cv2.connectedComponentsWithStats(
        erase_u8
    )
    for label in range(1, count):
        if int(stats[label, cv2.CC_STAT_AREA]) < 8:
            continue
        component = labels == label
        outer = cv2.dilate(
            np.where(component, 255, 0).astype(np.uint8),
            ELLIPSE_11,
            iterations=1,
        ) > 0
        ring = outer & ~component & ~line_guard & (alpha > 160)
        # Sample the neutral white already present beside this eye.  The old
        # warm-RGB preference selected cheek skin (S≈40) and exposed it as a
        # peach outline whenever the iris moved.  Tight chroma and channel-gap
        # limits keep the sample on the pale sclera instead.
        red = rgb[..., 0].astype(np.int16)
        green = rgb[..., 1].astype(np.int16)
        blue = rgb[..., 2].astype(np.int16)
        neutral_sclera = (
            ring
            & (hsv[..., 1] <= 20)
            & (hsv[..., 2] >= 205)
            & (np.abs(red - blue) <= 20)
            & (np.abs(red - green) <= 20)
        )
        samples = rgb[neutral_sclera]
        if len(samples) < 5:
            color = SCLERA_FALLBACK_RGB.copy()
        else:
            color = np.median(samples, axis=0).astype(np.uint8)
            peak = int(color.max())
            if peak < 245:
                color = np.clip(
                    color.astype(np.int16) + (245 - peak),
                    0,
                    255,
                ).astype(np.uint8)
            # Keep a slight local tint without allowing a visible skin rim.
            color = np.maximum(color, int(color.max()) - 14).astype(np.uint8)
        # A deterministic local fill avoids Telea pulling dark lashes, hair,
        # or lavender iris pixels into the newly exposed sclera crescent.
        result[component & ~line_guard] = color
    return result


def _upper_lash_top_bridge(
    rgba: np.ndarray,
    shape: IrisShape,
) -> np.ndarray:
    """Recover only the dark AA bridge between both sides of an upper lash."""
    bridge = np.zeros(shape.mask.shape, dtype=bool)
    y = shape.bbox[1]
    iris_x = np.flatnonzero(shape.mask[y])
    if len(iris_x) == 0:
        return bridge

    left_guard = np.flatnonzero(shape.lash_guard[y, : iris_x.min()])
    right_guard = (
        np.flatnonzero(shape.lash_guard[y, iris_x.max() + 1 :])
        + iris_x.max()
        + 1
    )
    if len(left_guard) == 0 or len(right_guard) == 0:
        return bridge

    x0 = int(left_guard.max()) + 1
    x1 = int(right_guard.min())
    if x1 <= x0:
        return bridge

    hsv = cv2.cvtColor(rgba[..., :3], cv2.COLOR_RGB2HSV)
    bridge[y, x0:x1] = (
        shape.mask[y, x0:x1]
        & (rgba[y, x0:x1, 3] > 20)
        & (hsv[y, x0:x1, 1] >= 12)
        & (hsv[y, x0:x1, 2] < 145)
    )
    return bridge


def _screen_left_upper_lash_notch_guard(
    rgba: np.ndarray,
    shape: IrisShape,
) -> np.ndarray:
    """Preserve the compact dark under-lash patch circled on body/right."""
    guard = np.zeros(shape.mask.shape, dtype=bool)
    left = shape.bbox[0] - 2
    right = shape.bbox[0] + 9
    top = shape.bbox[1] + 1
    bottom = shape.bbox[1] + 8
    hsv = cv2.cvtColor(rgba[..., :3], cv2.COLOR_RGB2HSV)
    guard[top:bottom, left:right] = (
        (rgba[top:bottom, left:right, 3] > 20)
        & (hsv[top:bottom, left:right, 1] >= 12)
        & (hsv[top:bottom, left:right, 2] < 145)
    )
    return guard


def separate_side_eye_frame(
    frame: Image.Image,
    raw_mask: np.ndarray,
    *,
    protect_screen_right_upper_lash_bridge: bool = False,
    protect_screen_left_upper_lash_bridge: bool = False,
) -> tuple[Image.Image, Image.Image, Image.Image]:
    rgba = np.asarray(frame.convert("RGBA"), dtype=np.uint8).copy()
    rgb = rgba[..., :3]
    alpha = rgba[..., 3]
    textures = _extract_reference_irises()
    shapes = detect_side_iris_shapes(frame, raw_mask)

    movable = np.zeros_like(rgba)
    line_guard = np.zeros(alpha.shape, dtype=bool)
    movable_exclusion = np.zeros(alpha.shape, dtype=bool)
    actual_iris = np.zeros(alpha.shape, dtype=bool)
    for shape_index, (shape, texture) in enumerate(zip(shapes, textures)):
        left, top, right, bottom = shape.bbox
        rendered = _resize_reference_to_shape(texture, shape)
        movable[top:bottom, left:right] = rendered
        effective_lash_guard = shape.lash_guard
        protect_far_bridge = (
            protect_screen_right_upper_lash_bridge
            and shape_index == len(shapes) - 1
        )
        protect_near_bridge = (
            protect_screen_left_upper_lash_bridge and shape_index == 0
        )
        if protect_far_bridge or protect_near_bridge:
            # At the approved body/right endpoint, the screen-right far lash
            # and screen-left near lash cross their irises on the top row.
            # Their center 11px / 15px are dark-purple antialiasing above the
            # V<80 core threshold, so the eye-base appears as a white notch
            # when gaze moves.  Bridge only that single row between already-
            # fixed lash pixels; do not freeze the iris rows beneath it.
            effective_lash_guard = (
                effective_lash_guard | _upper_lash_top_bridge(rgba, shape)
            )
        if protect_near_bridge:
            # The screen-left near eye also has a compact dark under-lash area
            # immediately below that bridge.  Horizontal iris cleanup painted
            # it sclera-white at gazeX=+1, producing the red-circled rectangular
            # notch.  Keep only this 11x7 dark source window in the fixed line;
            # the iris rows below and the opposite eye remain movable.
            effective_lash_guard = (
                effective_lash_guard
                | _screen_left_upper_lash_notch_guard(rgba, shape)
            )
        line_guard |= effective_lash_guard | shape.lower_guard
        movable_exclusion |= effective_lash_guard
        actual_iris |= shape.mask

    # Fixed lines win ownership wherever a source texture reaches the lid.
    movable[..., 3] = np.where(
        movable_exclusion,
        0,
        movable[..., 3],
    ).astype(np.uint8)
    movable_visible = movable[..., 3] > 0
    erase_core = actual_iris | movable_visible
    # Horizontal gaze needs a little lateral cleanup, but the previous 5x5
    # dilation twice also painted four rows of lower lid and cheek white.
    # Expand laterally only, then add genuinely purple source fringe nearby.
    erase = cv2.dilate(
        np.where(erase_core, 255, 0).astype(np.uint8),
        np.ones((1, 5), dtype=np.uint8),
        iterations=1,
    ) > 0
    source_hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    nearby = cv2.dilate(
        np.where(erase_core, 255, 0).astype(np.uint8),
        ELLIPSE_5,
        iterations=1,
    ) > 0
    purple_fringe = (
        (source_hsv[..., 0] >= 100)
        & (source_hsv[..., 0] <= 179)
        & (source_hsv[..., 1] >= 28)
        & (alpha > 20)
    )
    erase |= nearby & purple_fringe
    erase &= ~line_guard

    clean_rgb = _sclera_fill(rgb, alpha, erase, line_guard)
    feathered_base_alpha = np.where(erase, alpha, 0).astype(np.uint8)
    clean_hsv = cv2.cvtColor(clean_rgb, cv2.COLOR_RGB2HSV)
    fringe_contamination = (
        (feathered_base_alpha > 0)
        & ~line_guard
        & (clean_hsv[..., 0] >= 100)
        & (clean_hsv[..., 0] <= 179)
        & (clean_hsv[..., 1] >= 28)
    )
    clean_rgb[fringe_contamination] = SCLERA_FALLBACK_RGB
    eye_base = np.dstack([clean_rgb, feathered_base_alpha])
    eye_line = rgba.copy()
    eye_line[..., 3] = np.where(line_guard, alpha, 0).astype(np.uint8)
    return (
        Image.fromarray(eye_base, "RGBA"),
        Image.fromarray(movable, "RGBA"),
        Image.fromarray(eye_line, "RGBA"),
    )


def build_eye_patches(
    neutral_frames: list[Image.Image],
    iris_masks: list[np.ndarray],
    direction: str,
    *,
    protect_screen_right_upper_lash_bridge: bool = False,
    protect_screen_left_upper_lash_bridge: bool = False,
) -> tuple[list[Image.Image], list[Image.Image], list[Image.Image]]:
    roi = v10.scaled_roi(v11.PATCH_ROIS[direction]["blink"])
    eye_bases = []
    irises = []
    eye_lines = []
    for frame_index, (frame, raw_mask) in enumerate(
        zip(neutral_frames, iris_masks)
    ):
        eye_base, iris, eye_line = separate_side_eye_frame(
            frame,
            raw_mask,
            protect_screen_right_upper_lash_bridge=(
                protect_screen_right_upper_lash_bridge
                and frame_index == len(neutral_frames) - 1
            ),
            protect_screen_left_upper_lash_bridge=(
                protect_screen_left_upper_lash_bridge
                and frame_index == len(neutral_frames) - 1
            ),
        )
        eye_bases.append(eye_base.crop(roi))
        irises.append(iris.crop(roi))
        eye_lines.append(eye_line.crop(roi))
    return eye_bases, irises, eye_lines


def save_lossless_atlas(path: Path, frames: list[Image.Image]) -> None:
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
    atlas.save(path, "PNG", optimize=True)


def rebuild_side_eye_atlases():
    sequences = {}
    for kind in ("neck", "body"):
        for direction in ("left", "right"):
            neutral_frames, masks = _neutral_sequence(kind, direction)
            eye_bases, irises, eye_lines = build_eye_patches(
                neutral_frames,
                masks,
                direction,
                protect_screen_right_upper_lash_bridge=(
                    kind == "body" and direction == "right"
                ),
                protect_screen_left_upper_lash_bridge=(
                    kind == "body" and direction == "right"
                ),
            )
            atlas_root = NECK_ATLAS_ROOT if kind == "neck" else BODY_ATLAS_ROOT
            if kind == "body" and direction == "right":
                v11.save_atlas(
                    atlas_root / "right-neutral-v1.webp",
                    neutral_frames,
                )
            save_lossless_atlas(
                atlas_root / f"{direction}-eye-base-v1.png",
                eye_bases,
            )
            save_lossless_atlas(
                atlas_root / f"{direction}-irises-v1.png",
                irises,
            )
            save_lossless_atlas(
                atlas_root / f"{direction}-eye-line-v1.png",
                eye_lines,
            )
            sequences[(kind, direction)] = {
                "neutral": neutral_frames,
                "eye-base": eye_bases,
                "irises": irises,
                "eye-line": eye_lines,
            }
    return sequences


def _paste_patch(frame: Image.Image, patch: Image.Image, direction: str) -> Image.Image:
    roi = v10.scaled_roi(v11.PATCH_ROIS[direction]["blink"])
    result = frame.copy()
    result.alpha_composite(patch, (roi[0], roi[1]))
    return result


def _shift_patch(patch: Image.Image, x: int, y: int) -> Image.Image:
    shifted = Image.new("RGBA", patch.size, (0, 0, 0, 0))
    shifted.alpha_composite(patch, (x, y))
    return shifted


def render_review(sequences) -> None:
    examples = [
        ("neck", "left", FRAME_COUNT - 1),
        ("neck", "right", FRAME_COUNT - 1),
        ("body", "left", FRAME_COUNT - 1),
        ("body", "right", FRAME_COUNT - 1),
    ]
    gazes = [
        ("center", 0, 0),
        ("left", -5, 0),
        ("right", 5, 0),
        ("up", 0, -2),
        ("down", 0, 2),
    ]
    crop = (235, 260, 550, 420)
    panel_size = (630, 320)
    sheet = Image.new(
        "RGBA",
        (panel_size[0] * len(gazes), panel_size[1] * len(examples)),
        (15, 19, 40, 255),
    )
    draw = ImageDraw.Draw(sheet)
    for row, (kind, direction, index) in enumerate(examples):
        state = sequences[(kind, direction)]
        underpaint = _paste_patch(
            state["neutral"][index],
            state["eye-base"][index],
            direction,
        )
        for column, (label, x, y) in enumerate(gazes):
            frame = _paste_patch(
                underpaint,
                _shift_patch(state["irises"][index], x, y),
                direction,
            )
            frame = _paste_patch(frame, state["eye-line"][index], direction)
            panel = frame.crop(crop).resize(panel_size, Image.Resampling.LANCZOS)
            sheet.alpha_composite(
                panel,
                (column * panel_size[0], row * panel_size[1]),
            )
            draw.text(
                (column * panel_size[0] + 12, row * panel_size[1] + 10),
                f"{kind} {direction} {index} / gaze {label}",
                fill="white",
            )
    PREVIEWS_ROOT.mkdir(parents=True, exist_ok=True)
    sheet.save(PREVIEWS_ROOT / "side-gaze-clean-v2.png", "PNG", optimize=True)

    body_crop = (220, 285, 550, 380)
    body_panel = (660, 190)
    body_sheet = Image.new(
        "RGBA",
        (body_panel[0] * 3, body_panel[1] * 2),
        (15, 19, 40, 255),
    )
    body_draw = ImageDraw.Draw(body_sheet)
    for row, direction in enumerate(("left", "right")):
        state = sequences[("body", direction)]
        underpaint = _paste_patch(
            state["neutral"][-1],
            state["eye-base"][-1],
            direction,
        )
        for column, x in enumerate((-5, 0, 5)):
            frame = _paste_patch(
                underpaint,
                _shift_patch(state["irises"][-1], x, 0),
                direction,
            )
            frame = _paste_patch(frame, state["eye-line"][-1], direction)
            panel = frame.crop(body_crop).resize(
                body_panel,
                Image.Resampling.LANCZOS,
            )
            target_x = column * body_panel[0]
            target_y = row * body_panel[1]
            body_sheet.alpha_composite(panel, (target_x, target_y))
            body_draw.text(
                (target_x + 10, target_y + 8),
                f"body {direction} / gaze {x:+d}",
                fill="white",
            )
    body_sheet.save(
        PREVIEWS_ROOT / "body-side-lower-lid-v1.png",
        "PNG",
        optimize=True,
    )


def render_front_review(front_irises: Image.Image) -> None:
    eye_base = Image.open(
        V14_ROOT / "parts/aligned-v1/eye_base_open.png"
    ).convert("RGBA")
    frame = Image.open(
        V14_ROOT / "master/front-faceless-v1.png"
    ).convert("RGBA")
    frame.alpha_composite(eye_base)
    frame.alpha_composite(front_irises)
    for name in ("brows_neutral", "mouth_closed"):
        frame.alpha_composite(
            Image.open(V14_ROOT / f"parts/aligned-v1/{name}.png").convert(
                "RGBA"
            )
        )
    PREVIEWS_ROOT.mkdir(parents=True, exist_ok=True)
    frame.save(PREVIEWS_ROOT / "live2d-neutral-v1.png", "PNG", optimize=True)

    states = (
        ("left", -12, 0),
        ("center", 0, 0),
        ("right", 12, 0),
        ("up", 0, -7),
        ("down", 0, 7),
    )
    crop = (330, 370, 756, 650)
    sheet = Image.new("RGBA", (426 * len(states), 280), (15, 19, 40, 255))
    draw = ImageDraw.Draw(sheet)
    for index, (label, x, y) in enumerate(states):
        review = Image.open(
            V14_ROOT / "master/front-faceless-v1.png"
        ).convert("RGBA")
        review.alpha_composite(eye_base)
        shifted = Image.new("RGBA", review.size, (0, 0, 0, 0))
        shifted.alpha_composite(front_irises, (x, y))
        review.alpha_composite(shifted)
        for name in ("brows_neutral", "mouth_closed"):
            review.alpha_composite(
                Image.open(
                    V14_ROOT / f"parts/aligned-v1/{name}.png"
                ).convert("RGBA")
            )
        panel = Image.new("RGBA", review.size, (15, 19, 40, 255))
        panel.alpha_composite(review)
        sheet.alpha_composite(panel.crop(crop), (index * 426, 0))
        draw.text((index * 426 + 12, 10), f"gaze {label}", fill="white")
    sheet.save(PREVIEWS_ROOT / "gaze-range-v2.png", "PNG", optimize=True)

    blink_items = []
    for label in ("open", "half", "closed"):
        blink_frame = Image.open(
            V14_ROOT / "master/front-faceless-v1.png"
        ).convert("RGBA")
        if label != "closed":
            blink_frame.alpha_composite(eye_base)
            blink_frame.alpha_composite(front_irises)
        if label == "half":
            blink_frame.alpha_composite(
                Image.open(
                    V14_ROOT / "parts/aligned-v1/eyes_half_closed.png"
                ).convert("RGBA")
            )
        if label == "closed":
            blink_frame.alpha_composite(
                Image.open(
                    V14_ROOT / "parts/aligned-v1/eyes_closed.png"
                ).convert("RGBA")
            )
        for name in ("brows_neutral", "mouth_closed"):
            blink_frame.alpha_composite(
                Image.open(
                    V14_ROOT / f"parts/aligned-v1/{name}.png"
                ).convert("RGBA")
            )
        blink_items.append((label, blink_frame))

    blink_crop = (350, 400, 736, 550)
    blink_sheet = Image.new(
        "RGBA",
        ((blink_crop[2] - blink_crop[0]) * len(blink_items), 150),
        (15, 19, 40, 255),
    )
    blink_draw = ImageDraw.Draw(blink_sheet)
    for index, (label, blink_frame) in enumerate(blink_items):
        panel = Image.new("RGBA", blink_frame.size, (15, 19, 40, 255))
        panel.alpha_composite(blink_frame)
        x = index * (blink_crop[2] - blink_crop[0])
        blink_sheet.alpha_composite(panel.crop(blink_crop), (x, 0))
        blink_draw.text((x + 10, 8), label, fill="white")
    blink_sheet.save(
        PREVIEWS_ROOT / "front-blink-keys-v1.png",
        "PNG",
        optimize=True,
    )


def update_manifest() -> None:
    path = V14_ROOT / "manifest-live2d-poc-v1.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    layers = [
        layer
        for layer in manifest["layers"]
        if layer["name"] != "eyes_half_closed"
    ]
    for layer in layers:
        if layer["name"] == "eyes_closed":
            layer["order"] = 23
    layers.append(
        {
            "name": "eyes_half_closed",
            "file": "parts/aligned-v1/eyes_half_closed.png",
            "group": "20_eyes",
            "left": 0,
            "top": 0,
            "opacity": 255,
            "visible": False,
            "order": 22,
        }
    )
    manifest["layers"] = sorted(layers, key=lambda layer: layer["order"])
    manifest["notes"] = [
        "character-v14 rebuilds the front tracking irises from the user-approved green and hero identity references instead of the v7 iris generation with a pale lower wedge.",
        "The front iris pair is centered on the camera, fills the lower lid, and preserves a dark screen-left eye plus the pale moon-ring screen-right character-left eye.",
        "All four side sequences retexture only two detected iris silhouettes with the same character-specific reference pair; lashes and lid lines stay in a fixed lossless layer.",
        "The side eye-base uses guarded sclera inpainting; the lower lid is restored as a fixed foreground occluder instead of a hole that moves with the iris.",
        "Side eye-base colors are sampled only from the local low-saturation sclera and neutralized, so horizontal gaze cannot expose a peach skin-colored rim.",
        "Front open upper lids are mirrored from the screen-left key while the distinct dark and luminous moon-ring irises remain unchanged.",
        "Front blink uses a deterministic half-closed upper-lid cover and a mirrored closed line with fixed inner and outer corner anchors; the lower lid and iris coordinates do not move.",
        "All nine front mouth drawings are translated four pixels right without resizing or repainting so their center matches the original identity reference.",
        "Eye-base, iris, and eye-line atlases are lossless PNG; neutral, blink, and mouth atlases remain WebP.",
        "The runtime uses the clean split side eye at full alpha from centered gaze onward, so the baked neutral iris never cross-fades underneath it.",
        "The v13 turn cache, expressions, mouth shapes, static lock, and approved pose endpoints are otherwise preserved.",
        "This remains a cached raster review rig, not Cubism ArtMeshes or deformers.",
        "Live2D Cubism import remains unverified.",
    ]
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    layer_by_name = {layer["name"]: layer for layer in manifest["layers"]}
    half_names = (
        "front_faceless_base",
        "eye_base_open",
        "irises",
        "eyes_half_closed",
        "brows_neutral",
        "mouth_closed",
    )
    half_state = {
        "canvas": manifest["canvas"],
        "layers": [
            {**layer_by_name[name], "visible": True}
            for name in half_names
        ],
    }
    (V14_ROOT / "manifest-state-blink-half-v1.json").write_text(
        json.dumps(half_state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    closed_state_path = V14_ROOT / "manifest-state-blink-v1.json"
    closed_state = json.loads(closed_state_path.read_text(encoding="utf-8"))
    for layer in closed_state["layers"]:
        if layer["name"] == "eyes_closed":
            layer["order"] = 23
    closed_state_path.write_text(
        json.dumps(closed_state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    for reference in (REFERENCE_GREEN, REFERENCE_HERO):
        if not reference.exists():
            raise FileNotFoundError(reference)
    copy_v13_assets()
    refine_front_eye_and_mouth_parts()
    build_front_blink_keys()
    front_irises = build_front_reference_irises()
    render_front_review(front_irises)
    _configure_build_roots()
    sequences = rebuild_side_eye_atlases()
    render_review(sequences)
    update_manifest()
    print(f"Built character-v14 assets under {V14_ROOT}")


if __name__ == "__main__":
    main()
