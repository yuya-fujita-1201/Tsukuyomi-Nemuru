#!/usr/bin/env python3
"""Read-only evaluation of refined fixed-eyeline profile masks."""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
ROIS = {
    "left": (226, 283, 502, 382),
    "right": (276, 283, 552, 382),
}
E3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
E7 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
MOVES = ((-7, 0), (7, 0), (0, -4), (0, 4))
VARIANTS = {
    "p0-v150": {"allowance": 0, "extra_v": None},
    "p1-v150": {"allowance": 1, "extra_v": None},
    "p2-v150": {"allowance": 2, "extra_v": None},
    "hybrid-v100": {"allowance": 0, "extra_v": 100},
    "hybrid-v120": {"allowance": 0, "extra_v": 120},
}


def atlas_frames(atlas: Image.Image, width: int, height: int):
    return [
        atlas.crop(
            (
                (index % 4) * width,
                (index // 4) * height,
                (index % 4 + 1) * width,
                (index // 4 + 1) * height,
            )
        )
        for index in range(16)
    ]


def largest_component(mask: np.ndarray) -> np.ndarray:
    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        np.where(mask, 255, 0).astype(np.uint8)
    )
    candidates = [
        label
        for label in range(1, count)
        if stats[label, cv2.CC_STAT_AREA] >= 8
    ]
    if not candidates:
        raise ValueError("No iris color component")
    label = max(candidates, key=lambda value: stats[value, cv2.CC_STAT_AREA])
    return labels == label


def convex_hull(mask: np.ndarray) -> np.ndarray:
    points = np.column_stack(np.where(mask)[::-1]).astype(np.int32)
    if len(points) < 3:
        raise ValueError("Iris color component too small")
    result = np.zeros(mask.shape, dtype=np.uint8)
    cv2.fillConvexPoly(result, cv2.convexHull(points), 255)
    return result > 0


def build_masks(
    neutral_patch: np.ndarray,
    iris_support: np.ndarray,
    old_line: np.ndarray,
    variant: dict,
):
    full_support = iris_support | old_line
    hsv = cv2.cvtColor(neutral_patch[..., :3], cv2.COLOR_RGB2HSV)
    hue, saturation, value = [hsv[..., index] for index in range(3)]
    yy = np.indices(full_support.shape)[0]
    fixed = np.zeros_like(full_support)
    movable = iris_support.copy()
    core_reference = np.zeros_like(full_support)
    soft_reference = np.zeros_like(full_support)
    below_profile_band = np.zeros_like(full_support)
    eyes = []

    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        np.where(full_support, 255, 0).astype(np.uint8)
    )
    for label in range(1, count):
        if stats[label, cv2.CC_STAT_AREA] < 100:
            continue
        component = labels == label
        color_seed = (
            component
            & (hue >= 105)
            & (hue <= 175)
            & (saturation >= 48)
            & (value >= 70)
        )
        color_seed = cv2.morphologyEx(
            np.where(color_seed, 255, 0).astype(np.uint8),
            cv2.MORPH_OPEN,
            E3,
        ) > 0
        iris_hull = convex_hull(largest_component(color_seed))
        hull_u8 = np.where(iris_hull, 255, 0).astype(np.uint8)
        outer = cv2.dilate(hull_u8, E7, iterations=2) > 0
        near = cv2.dilate(hull_u8, E3, iterations=1) > 0

        top = np.full(iris_hull.shape[1], np.nan)
        for x in np.where(iris_hull.any(axis=0))[0]:
            top[x] = np.where(iris_hull[:, x])[0].min()
        known = np.where(~np.isnan(top))[0]
        top = np.interp(np.arange(len(top)), known, top[known])

        wing = outer & ~near
        base_corridor = (
            outer
            & (yy <= top[None, :] + variant["allowance"])
            & (yy >= top[None, :] - 10)
        )
        line = (
            old_line
            & component
            & (value < 150)
            & (saturation >= 20)
            & (base_corridor | wing)
        )

        extra_v = variant["extra_v"]
        if extra_v is not None:
            base = (
                old_line
                & component
                & (value < 150)
                & (saturation >= 20)
                & (
                    (
                        outer
                        & (yy <= top[None, :])
                        & (yy >= top[None, :] - 10)
                    )
                    | wing
                )
            )
            connected = cv2.dilate(
                np.where(base, 255, 0).astype(np.uint8), E3
            ) > 0
            extra = (
                old_line
                & component
                & (value < extra_v)
                & (saturation >= 18)
                & outer
                & (yy > top[None, :])
                & (yy <= top[None, :] + 1)
                & connected
            )
            line = base | extra

        recovered = old_line & component & iris_hull & ~line
        fixed |= line
        movable |= recovered

        # Independent references are broader than every candidate.
        core_reference |= (
            old_line
            & component
            & (value < 135)
            & (saturation >= 18)
            & (
                (
                    outer
                    & (yy <= top[None, :] + 1)
                    & (yy >= top[None, :] - 11)
                )
                | wing
            )
        )
        soft_reference |= (
            old_line
            & component
            & (value < 175)
            & (saturation >= 12)
            & (
                (
                    outer
                    & (yy <= top[None, :] + 1)
                    & (yy >= top[None, :] - 11)
                )
                | wing
            )
        )
        below_profile_band |= old_line & component & iris_hull & (
            yy > top[None, :]
        )
        eyes.append((component, iris_hull))

    movable &= ~fixed
    return {
        "fixed": fixed,
        "movable": movable,
        "core_reference": core_reference,
        "soft_reference": soft_reference,
        "below_profile_band": below_profile_band,
        "hsv": hsv,
        "eyes": eyes,
    }


def render(
    neutral: Image.Image,
    neutral_patch: np.ndarray,
    base_rgb: np.ndarray,
    movable: np.ndarray,
    fixed: np.ndarray,
    roi,
    dx: int,
    dy: int,
):
    alpha = np.where(movable, 255, 0).astype(np.uint8)
    result = neutral.copy()
    result.alpha_composite(
        Image.fromarray(np.dstack([base_rgb, alpha]), "RGBA"), roi[:2]
    )
    iris = Image.fromarray(
        np.dstack([neutral_patch[..., :3], alpha]), "RGBA"
    )
    shifted = Image.new("RGBA", iris.size, (0, 0, 0, 0))
    shifted.alpha_composite(iris, (dx, dy))
    result.alpha_composite(shifted, roi[:2])
    line_alpha = np.where(fixed, 255, 0).astype(np.uint8)
    result.alpha_composite(
        Image.fromarray(
            np.dstack([neutral_patch[..., :3], line_alpha]), "RGBA"
        ),
        roi[:2],
    )
    return result


def summarize(rows):
    result = {}
    for field in rows[0]:
        if field in {"kind", "direction", "frame"}:
            continue
        values = np.asarray([row[field] for row in rows], dtype=float)
        result[field] = {
            "mean": float(values.mean()),
            "p95": float(np.percentile(values, 95)),
            "max": float(values.max()),
            "min": float(values.min()),
        }
    result["frames_core_loss_gt1pct"] = int(
        sum(row["core_loss"] > 0.01 for row in rows)
    )
    result["frames_soft_loss_gt1pct"] = int(
        sum(row["soft_loss"] > 0.01 for row in rows)
    )
    result["frames_band_fixed"] = int(
        sum(row["band_fixed"] > 0 for row in rows)
    )
    result["frames_incomplete_band_recovery"] = int(
        sum(row["band_recovered"] != row["band_area"] for row in rows)
    )
    return result


def aggregate_loss_ownership(rows):
    result = {}
    for reference in ("core", "soft"):
        total = sum(row[f"{reference}_lost_pixels"] for row in rows)
        in_band = sum(
            row[f"{reference}_lost_pixels_in_false_band"] for row in rows
        )
        outside_band = sum(
            row[f"{reference}_lost_pixels_outside_false_band"] for row in rows
        )
        result[reference] = {
            "lost_pixels": int(total),
            "lost_pixels_in_false_band": int(in_band),
            "lost_pixels_outside_false_band": int(outside_band),
            "lost_pixels_in_false_band_ratio": float(
                in_band / max(1, total)
            ),
        }
    return result


def main():
    rows = {name: [] for name in VARIANTS}
    for family, kind in (
        ("neck-atlases", "neck"),
        ("body-atlases", "body"),
    ):
        for direction in ("left", "right"):
            root = ROOT / "assets/character-v13" / family
            roi = ROIS[direction]
            neutral_atlas = Image.open(
                root / f"{direction}-neutral-v1.webp"
            ).convert("RGBA")
            base_atlas = Image.open(
                root / f"{direction}-eye-base-v1.webp"
            ).convert("RGBA")
            iris_atlas = Image.open(
                root / f"{direction}-irises-v1.webp"
            ).convert("RGBA")
            line_atlas = Image.open(
                root / f"{direction}-eye-line-v1.png"
            ).convert("RGBA")
            patch_width = base_atlas.width // 4
            patch_height = base_atlas.height // 4
            frame_groups = zip(
                atlas_frames(neutral_atlas, 768, 1024),
                atlas_frames(base_atlas, patch_width, patch_height),
                atlas_frames(iris_atlas, patch_width, patch_height),
                atlas_frames(line_atlas, patch_width, patch_height),
            )
            for frame, (neutral, base, iris, old_line) in enumerate(frame_groups):
                neutral_patch = np.asarray(neutral.crop(roi))
                base_array = np.asarray(base)
                iris_support = np.asarray(iris)[..., 3] > 0
                old_line_support = np.asarray(old_line)[..., 3] > 0
                for name, variant in VARIANTS.items():
                    masks = build_masks(
                        neutral_patch,
                        iris_support,
                        old_line_support,
                        variant,
                    )
                    base_rgb = base_array[..., :3].copy()
                    for component, _hull in masks["eyes"]:
                        samples = base_rgb[component & iris_support]
                        fill = np.median(samples, axis=0).astype(np.uint8)
                        recovered = component & masks["movable"] & ~iris_support
                        base_rgb[recovered] = fill

                    neutral_v = masks["hsv"][..., 2].astype(np.int16)
                    core_losses = []
                    soft_losses = []
                    core_lost_pixels = []
                    core_lost_pixels_in_false_band = []
                    soft_lost_pixels = []
                    soft_lost_pixels_in_false_band = []
                    band = masks["below_profile_band"]
                    for dx, dy in MOVES:
                        output = render(
                            neutral,
                            neutral_patch,
                            base_rgb,
                            masks["movable"],
                            masks["fixed"],
                            roi,
                            dx,
                            dy,
                        )
                        output_hsv = cv2.cvtColor(
                            np.asarray(output.crop(roi))[..., :3],
                            cv2.COLOR_RGB2HSV,
                        )
                        delta_v = output_hsv[..., 2].astype(np.int16) - neutral_v
                        core = masks["core_reference"]
                        soft = masks["soft_reference"]
                        core_lost = core & (delta_v > 20)
                        soft_lost = soft & (delta_v > 20)
                        core_losses.append(
                            np.count_nonzero(core_lost)
                            / max(1, np.count_nonzero(core))
                        )
                        soft_losses.append(
                            np.count_nonzero(soft_lost)
                            / max(1, np.count_nonzero(soft))
                        )
                        core_lost_pixels.append(int(np.count_nonzero(core_lost)))
                        core_lost_pixels_in_false_band.append(
                            int(np.count_nonzero(core_lost & band))
                        )
                        soft_lost_pixels.append(int(np.count_nonzero(soft_lost)))
                        soft_lost_pixels_in_false_band.append(
                            int(np.count_nonzero(soft_lost & band))
                        )

                    fixed = masks["fixed"]
                    movable = masks["movable"]
                    core_total = sum(core_lost_pixels)
                    core_in_band = sum(core_lost_pixels_in_false_band)
                    soft_total = sum(soft_lost_pixels)
                    soft_in_band = sum(soft_lost_pixels_in_false_band)
                    rows[name].append(
                        {
                            "kind": kind,
                            "direction": direction,
                            "frame": frame,
                            "core_loss": float(max(core_losses)),
                            "soft_loss": float(max(soft_losses)),
                            "core_recall": float(
                                np.count_nonzero(core & fixed)
                                / max(1, np.count_nonzero(core))
                            ),
                            "soft_recall": float(
                                np.count_nonzero(soft & fixed)
                                / max(1, np.count_nonzero(soft))
                            ),
                            "core_lost_pixels": int(core_total),
                            "core_lost_pixels_in_false_band": int(core_in_band),
                            "core_lost_pixels_outside_false_band": int(
                                core_total - core_in_band
                            ),
                            "soft_lost_pixels": int(soft_total),
                            "soft_lost_pixels_in_false_band": int(soft_in_band),
                            "soft_lost_pixels_outside_false_band": int(
                                soft_total - soft_in_band
                            ),
                            "band_area": int(np.count_nonzero(band)),
                            "band_fixed": int(np.count_nonzero(band & fixed)),
                            "band_recovered": int(
                                np.count_nonzero(band & movable)
                            ),
                            "fixed_area": int(np.count_nonzero(fixed)),
                        }
                    )

    report = {
        "definitions": {
            "core_reference": "oldLine & V<135 & S>=18 & topProfile+1 corridor/wing",
            "soft_reference": "oldLine & V<175 & S>=12 & topProfile+1 corridor/wing",
            "false_band": "oldLine inside iris color hull and y>topProfile",
            "loss": "reference pixel output V > neutral V + 20, worst of four gaze moves",
        },
        "variants": {
            name: {
                "summary": summarize(value),
                "loss_ownership": aggregate_loss_ownership(value),
                "rows": value,
            }
            for name, value in rows.items()
        },
    }
    path = OUT / "profile-variant-independent-metrics.json"
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                name: value["summary"]
                for name, value in report["variants"].items()
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
