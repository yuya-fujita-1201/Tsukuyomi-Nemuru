#!/usr/bin/env python3
"""Build character-v13 with repaired front sclera and split side-eye masks."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

import build_character_v10 as v10
import build_character_v11 as v11
import build_character_v7 as v7


ROOT = Path(__file__).resolve().parents[1]
V12_ROOT = ROOT / "assets/character-v12"
V13_ROOT = ROOT / "assets/character-v13"
NECK_ATLAS_ROOT = V13_ROOT / "neck-atlases"
BODY_ATLAS_ROOT = V13_ROOT / "body-atlases"
PREVIEWS_ROOT = V13_ROOT / "previews"
FRAME_SIZE = v11.FRAME_SIZE
FRAME_COUNT = v11.FRAME_COUNT

ELLIPSE_3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
ELLIPSE_5 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
ELLIPSE_7 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
ELLIPSE_25_15 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 15))
FRONT_NASAL_SCLERA_REGIONS = (
    (462, 448, 498, 507),
    (588, 448, 624, 507),
)
BODY_RIGHT_CHEEK_REPAIRS = {
    9: ((507, 365), (13, 14)),
    10: ((513, 366), (13, 16)),
}


def copy_v12_assets() -> None:
    if not V12_ROOT.exists():
        raise FileNotFoundError(V12_ROOT)
    V13_ROOT.mkdir(parents=True, exist_ok=True)
    for path in sorted(V12_ROOT.rglob("*")):
        if not path.is_file():
            continue
        destination = V13_ROOT / path.relative_to(V12_ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)


def refine_front_eye_base() -> None:
    """Replace baked nasal iris fragments without touching the eye frame."""
    source_path = (
        ROOT / "assets/character-v7/work/eye-base-no-irises-alpha-v1.png"
    )
    if not source_path.exists():
        raise FileNotFoundError(source_path)
    clean_source = Image.open(source_path).convert("RGBA")
    clean_reference = v7.align_components(clean_source, v7.EYE_BOXES)
    target_path = V13_ROOT / "parts/aligned-v1/eye_base_open.png"
    original = np.asarray(Image.open(target_path).convert("RGBA"), dtype=np.uint8)
    clean = np.asarray(clean_reference, dtype=np.uint8)
    clean_hsv = cv2.cvtColor(clean[..., :3], cv2.COLOR_RGB2HSV)

    # The v7 split only replaced a narrow ellipse and left the old baked iris
    # at both nasal corners. Replace every pixel that the iris-free source
    # identifies as pale sclera, while preserving the approved lashes and
    # eyeliner byte-for-byte outside that interior.
    sclera_interior = (
        (clean[..., 3] > 160)
        & (clean_hsv[..., 1] < 90)
        & (clean_hsv[..., 2] > 160)
    )
    allowed = np.zeros(sclera_interior.shape, dtype=bool)
    for left, top, right, bottom in FRONT_NASAL_SCLERA_REGIONS:
        allowed[top:bottom, left:right] = True
    sclera_interior &= allowed
    repaired = original.copy()
    repaired[sclera_interior, :3] = clean[sclera_interior, :3]
    Image.fromarray(repaired, "RGBA").save(target_path)


def _seed_components(raw_mask: np.ndarray) -> list[np.ndarray]:
    seed = np.where(np.asarray(raw_mask) > 0.04, 255, 0).astype(np.uint8)
    seed = cv2.morphologyEx(seed, cv2.MORPH_CLOSE, ELLIPSE_3)
    count, labels, stats, _centroids = cv2.connectedComponentsWithStats(seed)
    components = []
    for label in range(1, count):
        if stats[label, cv2.CC_STAT_AREA] < 8:
            continue
        components.append(np.where(labels == label, 255, 0).astype(np.uint8))
    return components


def _sclera_sample(rgb: np.ndarray, alpha: np.ndarray, erase: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    outer = cv2.dilate(erase, ELLIPSE_7, iterations=2)
    inner = cv2.dilate(erase, ELLIPSE_3, iterations=1)
    ring = (outer > 0) & (inner == 0) & (alpha > 160)
    pale = ring & (hsv[..., 1] < 95) & (hsv[..., 2] > 155)
    samples = rgb[pale]
    if len(samples) < 8:
        samples = rgb[ring & (hsv[..., 2] > 145)]
    if len(samples) < 8:
        return np.array([239, 218, 225], dtype=np.uint8)
    color = np.median(samples, axis=0)
    # A blank eye should stay pale even when the surrounding skin is shadowed.
    color = np.maximum(color, np.array([205, 196, 205]))
    return np.clip(color, 0, 255).astype(np.uint8)


def _shift_mask(mask: np.ndarray, x: int, y: int) -> np.ndarray:
    matrix = np.float32([[1, 0, x], [0, 1, y]])
    return cv2.warpAffine(
        mask,
        matrix,
        (mask.shape[1], mask.shape[0]),
        flags=cv2.INTER_NEAREST,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    )


def _align_component_to_painted_iris(
    component: np.ndarray,
    purple: np.ndarray,
    dark_colored: np.ndarray,
) -> np.ndarray:
    """Correct small optical-flow offsets against the painted iris pixels."""
    likelihood = purple.astype(np.float32) + dark_colored.astype(np.float32) * 0.35
    best = component
    best_score = -1.0
    for y in range(-6, 7):
        for x in range(-12, 13):
            candidate = _shift_mask(component, x, y)
            selected = candidate > 0
            if not np.any(selected):
                continue
            score = float(np.mean(likelihood[selected]))
            score -= (abs(x) * 0.0025 + abs(y) * 0.004)
            if score > best_score:
                best = candidate
                best_score = score
    return best


def _largest_component(mask: np.ndarray, min_area: int = 8) -> np.ndarray:
    count, labels, stats, _centroids = cv2.connectedComponentsWithStats(mask)
    candidates = [
        label
        for label in range(1, count)
        if stats[label, cv2.CC_STAT_AREA] >= min_area
    ]
    if not candidates:
        raise ValueError("Aligned side-eye mask did not overlap a painted iris")
    largest = max(
        candidates,
        key=lambda label: stats[label, cv2.CC_STAT_AREA],
    )
    return np.where(labels == largest, 255, 0).astype(np.uint8)


def _convex_hull_mask(seed: np.ndarray) -> np.ndarray:
    points = np.column_stack(np.where(seed > 0)[::-1]).astype(np.int32)
    if len(points) < 3:
        raise ValueError("Painted iris seed is too small")
    support = np.zeros_like(seed, dtype=np.uint8)
    cv2.fillConvexPoly(support, cv2.convexHull(points), 255)
    return support


def _painted_iris_support(
    component: np.ndarray,
    strong_purple: np.ndarray,
    weak_purple: np.ndarray,
    dark_colored: np.ndarray,
) -> np.ndarray:
    """Grow a complete painted iris without inheriting warped mask tails."""
    # The propagated component is only a local search window. Using it as the
    # final ownership mask clips pale lavender iris edges and leaves them fixed
    # at the original coordinate when the eye moves.
    search = cv2.dilate(component, ELLIPSE_7, iterations=1)
    strong = np.where(
        (search > 0) & strong_purple,
        255,
        0,
    ).astype(np.uint8)
    strong = cv2.morphologyEx(
        strong,
        cv2.MORPH_OPEN,
        ELLIPSE_3,
        iterations=1,
    )
    strong = _largest_component(strong)

    local = cv2.dilate(
        _convex_hull_mask(strong),
        ELLIPSE_5,
        iterations=2,
    )
    allowed = np.where(
        (local > 0) & (weak_purple | dark_colored),
        255,
        0,
    ).astype(np.uint8)

    grown = strong
    for _ in range(16):
        candidate = cv2.dilate(grown, ELLIPSE_3, iterations=1)
        candidate = np.where(
            (candidate > 0) & (allowed > 0),
            255,
            0,
        ).astype(np.uint8)
        if np.array_equal(candidate, grown):
            break
        grown = candidate
    return _convex_hull_mask(_largest_component(grown))


def _filled_external_component(mask: np.ndarray) -> np.ndarray:
    """Fill holes without expanding a painted iris to its convex hull."""
    contours, _hierarchy = cv2.findContours(
        mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )
    if not contours:
        raise ValueError("Painted iris contour is empty")
    result = np.zeros_like(mask, dtype=np.uint8)
    cv2.drawContours(
        result,
        [max(contours, key=cv2.contourArea)],
        -1,
        255,
        cv2.FILLED,
    )
    return result


def _tight_painted_iris_support(
    component: np.ndarray,
    strong_purple: np.ndarray,
    weak_purple: np.ndarray,
    dark_colored: np.ndarray,
    pale_sclera: np.ndarray,
) -> np.ndarray:
    """Return the painted iris only, excluding the surrounding sclera rim."""
    prior = cv2.dilate(component, ELLIPSE_3, iterations=1)
    seed = np.where(
        (prior > 0) & strong_purple,
        255,
        0,
    ).astype(np.uint8)
    seed = cv2.morphologyEx(
        seed,
        cv2.MORPH_OPEN,
        ELLIPSE_3,
        iterations=1,
    )
    seed = _largest_component(seed)
    allowed = np.where(
        (prior > 0) & (weak_purple | dark_colored),
        255,
        0,
    ).astype(np.uint8)

    grown = seed
    for _ in range(12):
        candidate = cv2.dilate(grown, ELLIPSE_3, iterations=1)
        candidate = np.where(
            (candidate > 0) & (allowed > 0),
            255,
            0,
        ).astype(np.uint8)
        if np.array_equal(candidate, grown):
            break
        grown = candidate

    grown = cv2.morphologyEx(
        grown,
        cv2.MORPH_CLOSE,
        ELLIPSE_3,
        iterations=1,
    )
    support = _filled_external_component(_largest_component(grown)) > 0

    # The visible iris begins at the upper color profile. Above it is lash or
    # lid; pale pixels touching its first few rows are the sclera gap that
    # previously travelled as a white bar.
    iris_hull = _convex_hull_mask(seed) > 0
    top_profile = np.full(iris_hull.shape[1], np.nan)
    for x in np.where(iris_hull.any(axis=0))[0]:
        top_profile[x] = np.where(iris_hull[:, x])[0].min()
    known = np.where(~np.isnan(top_profile))[0]
    top_profile = np.interp(
        np.arange(len(top_profile)),
        known,
        top_profile[known],
    )
    yy = np.indices(support.shape)[0]
    support &= yy >= top_profile[None, :]
    upper_band = yy <= top_profile[None, :] + 3
    support &= ~(upper_band & pale_sclera)

    # Filled contours can capture a pale sclera/skin inlet and move it as a
    # hard white notch. Remove each pale component that touches the exterior
    # in one operation; enclosed catchlights remain part of the iris.
    pale_inside = support & pale_sclera
    outside_edge = cv2.dilate(
        (~support).astype(np.uint8),
        ELLIPSE_3,
        iterations=1,
    ) > 0
    pale_count, pale_labels, _stats, _centroids = (
        cv2.connectedComponentsWithStats(
            np.where(pale_inside, 255, 0).astype(np.uint8)
        )
    )
    for label in range(1, pale_count):
        pale_component = pale_labels == label
        if np.any(pale_component & outside_edge):
            support &= ~pale_component
    return np.where(support, 255, 0).astype(np.uint8)


def _independent_eye_guards(
    rgba: np.ndarray,
    raw_mask: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return iris interior, lower painted iris, and upper-lash guards.

    This path deliberately does not use the generated tight/broad ownership
    masks. It is an independent HSV reference anchored only by the propagated
    raw eye position, so a shared mask bug cannot hide old-iris residue.
    """
    hsv = cv2.cvtColor(rgba[..., :3], cv2.COLOR_RGB2HSV)
    strong = (
        (hsv[..., 0] >= 105)
        & (hsv[..., 0] <= 175)
        & (hsv[..., 1] >= 48)
        & (hsv[..., 2] >= 70)
    )
    iris_like = (
        (
            (hsv[..., 0] >= 100)
            & (hsv[..., 0] <= 179)
            & (hsv[..., 1] >= 18)
        )
        | ((hsv[..., 2] < 110) & (hsv[..., 1] >= 30))
    )
    prior = cv2.dilate(
        np.where(np.asarray(raw_mask) > 0.04, 255, 0).astype(np.uint8),
        ELLIPSE_25_15,
        iterations=1,
    ) > 0
    seed = cv2.morphologyEx(
        np.where(prior & strong, 255, 0).astype(np.uint8),
        cv2.MORPH_OPEN,
        ELLIPSE_3,
        iterations=1,
    )
    count, labels, stats, _centroids = cv2.connectedComponentsWithStats(seed)
    eyes = sorted(
        (
            label
            for label in range(1, count)
            if stats[label, cv2.CC_STAT_AREA] >= 100
        ),
        key=lambda label: stats[label, cv2.CC_STAT_AREA],
        reverse=True,
    )[:2]
    # Production frames contain two eyes. The one-eye allowance keeps this
    # ownership logic independently testable with a compact synthetic fixture.
    if not 1 <= len(eyes) <= 2:
        raise ValueError(f"Independent side-eye count was {len(eyes)}")

    interior = np.zeros(seed.shape, dtype=bool)
    recovered_lower = np.zeros(seed.shape, dtype=bool)
    lash_guard = np.zeros(seed.shape, dtype=bool)
    yy = np.indices(seed.shape)[0]
    for label in eyes:
        hull = _convex_hull_mask(
            np.where(labels == label, 255, 0).astype(np.uint8)
        ) > 0
        hull_u8 = np.where(hull, 255, 0).astype(np.uint8)
        outer = cv2.dilate(hull_u8, ELLIPSE_7, iterations=2) > 0
        top = np.full(hull.shape[1], np.nan)
        bottom = np.full(hull.shape[1], np.nan)
        for x in np.where(hull.any(axis=0))[0]:
            ys = np.where(hull[:, x])[0]
            top[x] = ys.min()
            bottom[x] = ys.max()
        known = np.where(~np.isnan(top))[0]
        top = np.interp(np.arange(len(top)), known, top[known])
        bottom = np.interp(np.arange(len(bottom)), known, bottom[known])
        interior |= hull & (yy > top[None, :])
        recovered_lower |= (
            hull
            & (yy >= top[None, :] + 0.35 * (bottom - top)[None, :])
            & iris_like
        )
        lash_guard |= (
            outer
            & (hsv[..., 2] < 100)
            & (hsv[..., 1] >= 18)
            & (yy >= top[None, :] - 10)
            & (yy <= top[None, :])
        )
    return interior, recovered_lower, lash_guard


def _fixed_eye_line_masks(
    rgba: np.ndarray,
    support: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Keep only the thin fixed lash ridge above the painted iris profile."""
    support_bool = support > 0
    hsv = cv2.cvtColor(rgba[..., :3], cv2.COLOR_RGB2HSV)
    dark = (hsv[..., 2] < 120) & (hsv[..., 1] >= 20)
    purple = (
        (hsv[..., 0] >= 105)
        & (hsv[..., 0] <= 175)
        & (hsv[..., 1] >= 48)
    )
    value = hsv[..., 2]
    saturation = hsv[..., 1]
    yy = np.indices(support_bool.shape)[0]
    candidate_all = np.zeros(support_bool.shape, dtype=bool)

    count, labels, stats, _centroids = cv2.connectedComponentsWithStats(
        np.where(support_bool, 255, 0).astype(np.uint8)
    )
    eye_components = [
        label
        for label in range(1, count)
        if stats[label, cv2.CC_STAT_AREA] >= 100
    ]
    if not 1 <= len(eye_components) <= 2:
        raise ValueError(
            f"Expected one or two eye components, got {len(eye_components)}"
        )

    for label in eye_components:
        component = labels == label
        strong = np.where(component & purple, 255, 0).astype(np.uint8)
        strong = cv2.morphologyEx(
            strong,
            cv2.MORPH_OPEN,
            ELLIPSE_3,
            iterations=1,
        )
        strong = _largest_component(strong) > 0
        iris_hull = _convex_hull_mask(
            np.where(strong, 255, 0).astype(np.uint8)
        ) > 0
        outer = cv2.dilate(
            np.where(iris_hull, 255, 0).astype(np.uint8),
            ELLIPSE_7,
            iterations=1,
        ) > 0
        inner = cv2.erode(
            np.where(iris_hull, 255, 0).astype(np.uint8),
            ELLIPSE_3,
            iterations=2,
        ) > 0
        dark_band = dark & outer & ~inner

        # Lashes and eyeliner continue beyond the iris ownership component;
        # pupils do not. Preserve every dark connected component that reaches
        # outside, plus short upper-lash segments broken by a one-pixel gap.
        line_count, line_labels, _line_stats, _line_centroids = (
            cv2.connectedComponentsWithStats(
                np.where(dark_band, 255, 0).astype(np.uint8)
            )
        )
        fixed = np.zeros(component.shape, dtype=bool)
        for line_label in range(1, line_count):
            pixels = line_labels == line_label
            if np.any(pixels & ~component):
                fixed |= pixels

        iris_y = np.where(iris_hull)[0]
        iris_height = int(iris_y.max() - iris_y.min() + 1)
        fixed |= (
            dark
            & component
            & outer
            & (
                yy
                <= iris_y.min() + max(3, int(iris_height * 0.16))
            )
        )
        candidate_all |= fixed

    # The broad candidate intentionally mirrors the previous ownership rule;
    # a strict top profile then removes its iris-colored horizontal band.
    candidate_all = cv2.dilate(
        np.where(candidate_all, 255, 0).astype(np.uint8),
        ELLIPSE_3,
        iterations=1,
    ) > 0
    full_support = support_bool | candidate_all
    fixed_all = np.zeros(support_bool.shape, dtype=bool)
    count, labels, stats, _centroids = cv2.connectedComponentsWithStats(
        np.where(full_support, 255, 0).astype(np.uint8)
    )
    eye_components = [
        label
        for label in range(1, count)
        if stats[label, cv2.CC_STAT_AREA] >= 100
    ]
    if not 1 <= len(eye_components) <= 2:
        raise ValueError(
            f"Expected one or two eye components, got {len(eye_components)}"
        )

    for label in eye_components:
        component = labels == label
        color_seed = (
            component
            & purple
            & (value >= 70)
        )
        color_seed = cv2.morphologyEx(
            np.where(color_seed, 255, 0).astype(np.uint8),
            cv2.MORPH_OPEN,
            ELLIPSE_3,
            iterations=1,
        )
        iris_hull = _convex_hull_mask(
            _largest_component(color_seed)
        ) > 0
        hull_u8 = np.where(iris_hull, 255, 0).astype(np.uint8)
        outer = cv2.dilate(hull_u8, ELLIPSE_7, iterations=2) > 0
        near = cv2.dilate(hull_u8, ELLIPSE_3, iterations=1) > 0

        top_profile = np.full(iris_hull.shape[1], np.nan)
        for x in np.where(iris_hull.any(axis=0))[0]:
            top_profile[x] = np.where(iris_hull[:, x])[0].min()
        known = np.where(~np.isnan(top_profile))[0]
        top_profile = np.interp(
            np.arange(len(top_profile)),
            known,
            top_profile[known],
        )
        corridor = (
            outer
            & (yy <= top_profile[None, :])
            & (yy >= top_profile[None, :] - 10)
        )
        wing = outer & ~near
        line_candidate = (
            candidate_all
            & component
            & (value < 150)
            & (saturation >= 20)
            & (corridor | wing)
        )
        # Near-black upper-lash pixels can have too little saturation to enter
        # candidate_all. Keep only the row at or above the independently
        # measured iris top; extending below it reintroduces the fixed purple
        # band that originally looked like a second iris.
        very_dark_top_ridge = (
            component
            & outer
            & (value < 80)
            & (yy <= top_profile[None, :])
            & (yy >= top_profile[None, :] - 10)
        )

        line_candidate = np.where(
            line_candidate | very_dark_top_ridge,
            255,
            0,
        ).astype(np.uint8)
        fixed_all |= line_candidate > 0

    fixed_overlay = fixed_all
    movable = support_bool & ~fixed_overlay
    return (
        np.where(fixed_overlay, 255, 0).astype(np.uint8),
        np.where(movable, 255, 0).astype(np.uint8),
    )


def separate_eye_frame(
    frame: Image.Image,
    raw_mask: np.ndarray,
) -> tuple[Image.Image, Image.Image, Image.Image]:
    """Return safe underpaint, tight iris, and fixed eyeline layers."""
    rgba = np.asarray(frame.convert("RGBA"), dtype=np.uint8).copy()
    rgb = rgba[..., :3]
    alpha = rgba[..., 3]
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    strong_purple = (
        (hsv[..., 0] >= 105)
        & (hsv[..., 0] <= 175)
        & (hsv[..., 1] >= 48)
    )
    weak_purple = (
        (hsv[..., 0] >= 100)
        & (hsv[..., 0] <= 179)
        & (hsv[..., 1] >= 18)
    )
    dark_colored = (hsv[..., 2] < 105) & (hsv[..., 1] >= 38)
    pale_sclera = (hsv[..., 1] < 65) & (hsv[..., 2] > 165)
    chromatic_iris_fringe = (
        (hsv[..., 0] >= 100)
        & (hsv[..., 0] <= 179)
        & (hsv[..., 1] >= 65)
    )

    support_union = np.zeros(alpha.shape, dtype=np.uint8)
    tight_iris_union = np.zeros(alpha.shape, dtype=np.uint8)

    for component in _seed_components(raw_mask):
        component = _align_component_to_painted_iris(
            component,
            strong_purple,
            dark_colored,
        )
        support = _painted_iris_support(
            component,
            strong_purple,
            weak_purple,
            dark_colored,
        )
        support_union = cv2.bitwise_or(support_union, support)
        tight_iris_union = cv2.bitwise_or(
            tight_iris_union,
            _tight_painted_iris_support(
                component,
                strong_purple,
                weak_purple,
                dark_colored,
                pale_sclera,
            ),
        )

    if not np.any(support_union) or not np.any(tight_iris_union):
        raise ValueError("Side-eye separation received an empty iris mask")

    independent_interior, recovered_lower, lash_guard = (
        _independent_eye_guards(rgba, raw_mask)
    )
    fixed_line, broad_movable = _fixed_eye_line_masks(
        rgba,
        support_union,
    )
    fixed_bool = (
        ((fixed_line > 0) & ~independent_interior) | lash_guard
    )
    fixed_line = np.where(fixed_bool, 255, 0).astype(np.uint8)
    recovery_window = cv2.dilate(
        tight_iris_union,
        ELLIPSE_5,
        iterations=1,
    ) > 0
    recovered_painted_edge = (
        (broad_movable > 0)
        & recovery_window
        & (weak_purple | dark_colored)
        & ~pale_sclera
    )
    movable_support = (
        (tight_iris_union > 0)
        | recovered_painted_edge
        | recovered_lower
    ) & ~fixed_bool
    movable_support &= ~(pale_sclera & ~independent_interior)

    # Some side frames contain a detached upper-lash island just above the
    # iris. Every legitimate antialiased iris fringe intersects the independent
    # iris interior; an island of useful size that does not is fixed eye frame.
    movable_count, movable_labels, movable_stats, _centroids = (
        cv2.connectedComponentsWithStats(
            np.where(movable_support, 255, 0).astype(np.uint8)
        )
    )
    for label in range(1, movable_count):
        component = movable_labels == label
        if movable_stats[label, cv2.CC_STAT_AREA] < 8:
            continue
        if not np.any(component & independent_interior):
            fixed_bool |= component
            movable_support &= ~component
    fixed_line = np.where(fixed_bool, 255, 0).astype(np.uint8)
    expanded_erase = cv2.dilate(
        np.where(movable_support, 255, 0).astype(np.uint8),
        ELLIPSE_3,
        iterations=1,
    ) > 0
    erase_support = movable_support | (
        expanded_erase & chromatic_iris_fringe
    )
    erase_support &= ~fixed_bool
    clean_rgb = rgb.copy()
    for component in _seed_components(erase_support.astype(np.float32)):
        fill = _sclera_sample(rgb, alpha, component)
        clean_rgb[component > 0] = fill

    # The eraser is one pixel wider than the tight painted iris. It removes the
    # complete old iris without moving the pale sclera rim or a skin-colored
    # convex-hull notch along with the new gaze position.
    erase_alpha = np.where(erase_support, alpha, 0).astype(np.uint8)
    iris_alpha = np.where(movable_support, alpha, 0).astype(np.uint8)
    eye_base = np.dstack([clean_rgb, erase_alpha])
    movable = rgba.copy()
    movable[..., 3] = iris_alpha
    eyeline = rgba.copy()
    eyeline[..., 3] = np.where(fixed_line > 0, alpha, 0).astype(np.uint8)
    return (
        Image.fromarray(eye_base, "RGBA"),
        Image.fromarray(movable, "RGBA"),
        Image.fromarray(eyeline, "RGBA"),
    )


def build_eye_patches(
    neutral_frames: list[Image.Image],
    iris_masks: list[np.ndarray],
    direction: str,
) -> tuple[list[Image.Image], list[Image.Image], list[Image.Image]]:
    roi = v10.scaled_roi(v11.PATCH_ROIS[direction]["blink"])
    eye_bases = []
    irises = []
    eyelines = []
    for frame, raw_mask in zip(neutral_frames, iris_masks):
        eye_base, iris, eyeline = separate_eye_frame(frame, raw_mask)
        eye_bases.append(eye_base.crop(roi))
        irises.append(iris.crop(roi))
        eyelines.append(eyeline.crop(roi))
    return eye_bases, irises, eyelines


def save_lossless_atlas(path: Path, frames: list[Image.Image]) -> None:
    """Store fixed line art without independent lossy WebP color drift."""
    width, height = frames[0].size
    atlas = Image.new(
        "RGBA",
        (width * v11.ATLAS_COLUMNS, height * v11.ATLAS_ROWS),
        (0, 0, 0, 0),
    )
    for index, frame in enumerate(frames):
        x = (index % v11.ATLAS_COLUMNS) * width
        y = (index // v11.ATLAS_COLUMNS) * height
        atlas.alpha_composite(frame, (x, y))
    path.parent.mkdir(parents=True, exist_ok=True)
    atlas.save(path, "PNG", optimize=True)


def _neutral_sequence(kind: str, direction: str):
    anchors = v11.sequence_neutral_anchors(kind, direction)
    intervals = v11.sequence_intervals(kind, direction)
    arrays = [v10.load_small_rgba(image) for image in anchors]
    flows = v11.build_flows(arrays)
    frames = [
        v11.image_from_array(array)
        for array in v11.interpolate_arrays(arrays, flows, intervals)
    ]
    if kind == "body" and direction == "right":
        frames = _repair_body_right_cheek(frames)
    masks = v11.build_iris_mask_frames(flows, intervals)
    return frames, masks


def _repair_body_right_cheek(frames: list[Image.Image]) -> list[Image.Image]:
    """Remove the two optical-flow blocks below the screen-right eye."""
    repaired = list(frames)
    for index, (center, axes) in BODY_RIGHT_CHEEK_REPAIRS.items():
        rgba = np.asarray(repaired[index].convert("RGBA"), dtype=np.uint8).copy()
        rgb = rgba[..., :3].astype(np.float32)
        mask = np.zeros(rgb.shape[:2], dtype=np.uint8)
        cv2.ellipse(mask, center, axes, 0, 0, 360, 255, -1)
        ring = (
            cv2.dilate(mask, ELLIPSE_7, iterations=2) > 0
        ) & (mask == 0)
        hsv = cv2.cvtColor(rgb.astype(np.uint8), cv2.COLOR_RGB2HSV)
        skin = (
            ring
            & (rgb[..., 0] > 215)
            & (rgb[..., 1] > 165)
            & (rgb[..., 2] > 165)
            & (hsv[..., 1] < 85)
        )
        if np.count_nonzero(skin) < 100:
            raise ValueError(f"Missing cheek skin samples for frame {index}")
        skin_color = np.median(rgb[skin], axis=0)
        filled = rgb.copy()
        filled[mask > 0] = skin_color
        feather = cv2.GaussianBlur(mask, (5, 5), 0.8).astype(np.float32)
        feather = feather[..., None] / 255
        rgba[..., :3] = np.clip(
            rgb * (1 - feather) + filled * feather,
            0,
            255,
        ).astype(np.uint8)
        repaired[index] = Image.fromarray(rgba, "RGBA")
    return repaired


def rebuild_side_eye_atlases():
    sequences = {}
    for kind in ("neck", "body"):
        for direction in ("left", "right"):
            neutral_frames, masks = _neutral_sequence(kind, direction)
            eye_bases, irises, eyelines = build_eye_patches(
                neutral_frames,
                masks,
                direction,
            )
            atlas_root = NECK_ATLAS_ROOT if kind == "neck" else BODY_ATLAS_ROOT
            if kind == "body" and direction == "right":
                v11.save_atlas(
                    atlas_root / "right-neutral-v1.webp",
                    neutral_frames,
                )
            v11.save_atlas(atlas_root / f"{direction}-eye-base-v1.webp", eye_bases)
            v11.save_atlas(atlas_root / f"{direction}-irises-v1.webp", irises)
            save_lossless_atlas(
                atlas_root / f"{direction}-eye-line-v1.png",
                eyelines,
            )
            sequences[(kind, direction)] = {
                "neutral": neutral_frames,
                "eye-base": eye_bases,
                "irises": irises,
                "eye-line": eyelines,
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
    PREVIEWS_ROOT.mkdir(parents=True, exist_ok=True)
    examples = [
        ("neck", "right", 11),
        ("body", "left", 9),
    ]
    directions = [
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
        (panel_size[0] * len(directions), panel_size[1] * len(examples)),
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
        for column, (label, x, y) in enumerate(directions):
            frame = _paste_patch(
                underpaint,
                _shift_patch(state["irises"][index], x, y),
                direction,
            )
            frame = _paste_patch(
                frame,
                state["eye-line"][index],
                direction,
            )
            panel = frame.crop(crop).resize(panel_size, Image.Resampling.LANCZOS)
            sheet.alpha_composite(panel, (column * panel_size[0], row * panel_size[1]))
            draw.text(
                (column * panel_size[0] + 12, row * panel_size[1] + 10),
                f"{kind} {direction} {index} / gaze {label}",
                fill="white",
            )
    sheet.save(PREVIEWS_ROOT / "side-gaze-clean-v1.png")


def update_manifest() -> None:
    path = V13_ROOT / "manifest-live2d-poc-v1.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["notes"] = [
        "character-v13 repairs only the two nasal sclera regions of the front open-eye base; every other character-v12 front layer remains byte-identical.",
        "All four side sequences use an independent HSV/hull reference to recover the lower painted iris while keeping the upper lash ridge fixed.",
        "Every movable component of useful size must intersect the independent iris interior; detached lash islands are reassigned to the fixed eye-line.",
        "The movable iris excludes exposed pale sclera pixels, while the one-pixel eraser expansion is restricted to chromatic iris fringe pixels so it cannot cut the dark eye frame.",
        "Four lossless eye-line PNG atlases render after the shifted iris; the runtime loads 38 layered assets in total.",
        "Two gray optical-flow cheek artifacts in the body-right neutral sequence are locally repaired before its atlas is saved.",
        "At centered side gaze the runtime displays the completed neutral eye directly; the split layers engage only when gaze moves.",
        "Side gaze, blink, mouth movement, and the v12 static turn lock remain independently controllable.",
        "This remains a cached raster review rig, not Cubism ArtMeshes or deformers.",
        "Live2D Cubism import remains unverified.",
    ]
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    copy_v12_assets()
    refine_front_eye_base()
    v11.V11_ROOT = V13_ROOT
    v11.RAW_ROOT = V13_ROOT / "raw/imagegen"
    v11.WORK_ROOT = V13_ROOT / "work"
    v11.POSES_ROOT = V13_ROOT / "poses"
    v11.NECK_ATLAS_ROOT = NECK_ATLAS_ROOT
    v11.BODY_ATLAS_ROOT = BODY_ATLAS_ROOT
    sequences = rebuild_side_eye_atlases()
    render_review(sequences)
    update_manifest()
    print(f"Built character-v13 assets under {V13_ROOT}")


if __name__ == "__main__":
    main()
