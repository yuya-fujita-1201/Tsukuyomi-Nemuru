import sys
import unittest
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_character_v13 as v13  # noqa: E402
import build_character_v7 as v7  # noqa: E402


class SideEyeSeparationTests(unittest.TestCase):
    @staticmethod
    def _broad_support(frame, raw_mask):
        rgba = np.asarray(frame.convert("RGBA"), dtype=np.uint8)
        hsv = cv2.cvtColor(rgba[..., :3], cv2.COLOR_RGB2HSV)
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
        support = np.zeros(hsv.shape[:2], dtype=np.uint8)
        for component in v13._seed_components(raw_mask):
            component = v13._align_component_to_painted_iris(
                component,
                strong_purple,
                dark_colored,
            )
            support = cv2.bitwise_or(
                support,
                v13._painted_iris_support(
                    component,
                    strong_purple,
                    weak_purple,
                    dark_colored,
                ),
            )
        return rgba, support

    @staticmethod
    def _independent_eye_geometry(frame, raw_mask):
        rgba = np.asarray(frame.convert("RGBA"), dtype=np.uint8)
        hsv = cv2.cvtColor(rgba[..., :3], cv2.COLOR_RGB2HSV)
        iris_like = (
            (hsv[..., 0] >= 100)
            & (hsv[..., 0] <= 179)
            & (hsv[..., 1] >= 18)
        ) | ((hsv[..., 2] < 110) & (hsv[..., 1] >= 30))
        strong = (
            (hsv[..., 0] >= 105)
            & (hsv[..., 0] <= 175)
            & (hsv[..., 1] >= 48)
            & (hsv[..., 2] >= 70)
        )
        prior = cv2.dilate(
            np.where(np.asarray(raw_mask) > 0.04, 255, 0).astype(np.uint8),
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 15)),
            iterations=1,
        ) > 0
        color_seed = cv2.morphologyEx(
            np.where(prior & strong, 255, 0).astype(np.uint8),
            cv2.MORPH_OPEN,
            v13.ELLIPSE_3,
        )
        count, labels, stats, _centroids = cv2.connectedComponentsWithStats(
            color_seed
        )
        eyes = sorted(
            (
                label
                for label in range(1, count)
                if stats[label, cv2.CC_STAT_AREA] >= 100
            ),
            key=lambda label: stats[label, cv2.CC_STAT_AREA],
            reverse=True,
        )[:2]
        if len(eyes) != 2:
            raise AssertionError(f"independent eye count was {len(eyes)}")
        reference = np.zeros(hsv.shape[:2], dtype=bool)
        interior = np.zeros(hsv.shape[:2], dtype=bool)
        lash = np.zeros(hsv.shape[:2], dtype=bool)
        yy = np.indices(reference.shape)[0]
        for label in eyes:
            hull = v13._convex_hull_mask(
                np.where(labels == label, 255, 0).astype(np.uint8)
            ) > 0
            outer = cv2.dilate(
                np.where(hull, 255, 0).astype(np.uint8),
                v13.ELLIPSE_7,
                iterations=2,
            ) > 0
            top = np.full(hull.shape[1], np.nan)
            bottom = np.full(hull.shape[1], np.nan)
            for x in np.where(hull.any(axis=0))[0]:
                ys = np.where(hull[:, x])[0]
                top[x] = ys.min()
                bottom[x] = ys.max()
            known = np.where(~np.isnan(top))[0]
            top = np.interp(np.arange(len(top)), known, top[known])
            bottom = np.interp(np.arange(len(bottom)), known, bottom[known])
            lower_start = top + 0.75 * (bottom - top)
            reference |= (
                hull
                & (yy >= lower_start[None, :])
                & iris_like
            )
            interior |= hull & (yy > top[None, :])
            lash |= (
                outer
                & (hsv[..., 2] < 100)
                & (hsv[..., 1] >= 18)
                & (yy >= top[None, :] - 10)
                & (yy <= top[None, :])
            )
        return reference, interior, lash

    @staticmethod
    def _independent_lower_iris_reference(frame, raw_mask):
        reference, _interior, _lash = (
            SideEyeSeparationTests._independent_eye_geometry(frame, raw_mask)
        )
        return reference

    def test_front_eye_base_has_no_baked_iris_in_the_nasal_sclera(self):
        clean_source = Image.open(
            ROOT
            / "assets/character-v7/work/eye-base-no-irises-alpha-v1.png"
        ).convert("RGBA")
        clean_reference = v7.align_components(clean_source, v7.EYE_BOXES)
        eye_base = Image.open(
            ROOT
            / "assets/character-v13/parts/aligned-v1/eye_base_open.png"
        ).convert("RGBA")
        previous_eye_base = Image.open(
            ROOT
            / "assets/character-v12/parts/aligned-v1/eye_base_open.png"
        ).convert("RGBA")

        clean_rgba = np.asarray(clean_reference)
        eye_rgba = np.asarray(eye_base)
        clean_hsv = cv2.cvtColor(clean_rgba[..., :3], cv2.COLOR_RGB2HSV)
        eye_hsv = cv2.cvtColor(eye_rgba[..., :3], cv2.COLOR_RGB2HSV)
        clean_sclera = (
            (clean_rgba[..., 3] > 160)
            & (clean_hsv[..., 1] < 90)
            & (clean_hsv[..., 2] > 160)
        )
        baked_purple = (
            (eye_rgba[..., 3] > 20)
            & (eye_hsv[..., 0] >= 100)
            & (eye_hsv[..., 0] <= 179)
            & (eye_hsv[..., 1] >= 80)
        )
        allowed_repair = np.zeros(clean_sclera.shape, dtype=bool)
        for left, top, right, bottom in v13.FRONT_NASAL_SCLERA_REGIONS:
            allowed_repair[top:bottom, left:right] = True
        allowed_repair &= clean_sclera

        previous_rgba = np.asarray(previous_eye_base)
        self.assertTrue(
            np.array_equal(eye_rgba[..., 3], previous_rgba[..., 3]),
            "front eye alpha must stay unchanged",
        )
        self.assertTrue(
            np.array_equal(
                eye_rgba[~allowed_repair],
                previous_rgba[~allowed_repair],
            ),
            "front eye pixels outside the nasal sclera repair changed",
        )
        self.assertTrue(
            np.array_equal(
                eye_rgba[allowed_repair, :3],
                clean_rgba[allowed_repair, :3],
            ),
            "front nasal sclera does not match the clean reference",
        )

        nasal_regions = {
            "screen-left eye": (462, 448, 498, 507),
            "screen-right eye": (588, 448, 624, 507),
        }
        for label, (left, top, right, bottom) in nasal_regions.items():
            contamination = (
                clean_sclera[top:bottom, left:right]
                & baked_purple[top:bottom, left:right]
            )
            self.assertEqual(
                int(np.count_nonzero(contamination)),
                0,
                label,
            )

    def test_body_right_neutral_has_no_gray_cheek_flow_patch(self):
        frames, _masks = v13._neutral_sequence("body", "right")
        for index, (center, axes) in v13.BODY_RIGHT_CHEEK_REPAIRS.items():
            rgb = np.asarray(frames[index].convert("RGBA"))[..., :3]
            core = np.zeros(rgb.shape[:2], dtype=np.uint8)
            core_axes = (axes[0] - 3, axes[1] - 3)
            cv2.ellipse(core, center, core_axes, 0, 0, 360, 255, -1)
            pixels = rgb[core > 0]
            skin = (
                (pixels[:, 0] > 235)
                & (pixels[:, 1] > 195)
                & (pixels[:, 2] > 190)
            )
            self.assertGreaterEqual(
                np.count_nonzero(skin) / len(skin),
                0.98,
                f"body/right frame {index}",
            )

    def test_v13_preserves_every_untouched_v12_front_layer_exactly(self):
        relative_paths = [
            Path("master/front-faceless-v1.png"),
            *[
                Path("parts/aligned-v1") / name
                for name in (
                    "irises.png",
                    "eyes_closed.png",
                    "brows_neutral.png",
                    "mouth_closed.png",
                    "mouth_open_micro.png",
                    "mouth_open_small.png",
                    "mouth_open_wide.png",
                    "mouth_vowel_a.png",
                    "mouth_vowel_i.png",
                    "mouth_vowel_u.png",
                    "mouth_vowel_e.png",
                    "mouth_vowel_o.png",
                )
            ],
        ]
        for relative_path in relative_paths:
            v12_path = ROOT / "assets/character-v12" / relative_path
            v13_path = ROOT / "assets/character-v13" / relative_path
            self.assertEqual(
                v13_path.read_bytes(),
                v12_path.read_bytes(),
                relative_path,
            )
            self.assertTrue(
                np.array_equal(
                    np.asarray(Image.open(v13_path).convert("RGBA")),
                    np.asarray(Image.open(v12_path).convert("RGBA")),
                ),
                relative_path,
            )

    def test_centered_side_eye_stack_preserves_lids_and_lashes(self):
        for family in ("neck-atlases", "body-atlases"):
            for direction in ("left", "right"):
                atlas_root = ROOT / "assets/character-v13" / family
                neutral_atlas = Image.open(
                    atlas_root / f"{direction}-neutral-v1.webp"
                ).convert("RGBA")
                base_atlas = Image.open(
                    atlas_root / f"{direction}-eye-base-v1.webp"
                ).convert("RGBA")
                iris_atlas = Image.open(
                    atlas_root / f"{direction}-irises-v1.webp"
                ).convert("RGBA")
                patch_box = v13.v10.scaled_roi(
                    v13.v11.PATCH_ROIS[direction]["blink"]
                )
                patch_x, patch_y = patch_box[:2]
                patch_width = base_atlas.width // 4
                patch_height = base_atlas.height // 4

                for index in range(16):
                    frame_x = (index % 4) * v13.FRAME_SIZE[0]
                    frame_y = (index // 4) * v13.FRAME_SIZE[1]
                    neutral = neutral_atlas.crop(
                        (
                            frame_x,
                            frame_y,
                            frame_x + v13.FRAME_SIZE[0],
                            frame_y + v13.FRAME_SIZE[1],
                        )
                    )
                    atlas_x = (index % 4) * patch_width
                    atlas_y = (index // 4) * patch_height
                    atlas_box = (
                        atlas_x,
                        atlas_y,
                        atlas_x + patch_width,
                        atlas_y + patch_height,
                    )
                    reconstructed = neutral.copy()
                    reconstructed.alpha_composite(
                        base_atlas.crop(atlas_box),
                        (patch_x, patch_y),
                    )
                    reconstructed.alpha_composite(
                        iris_atlas.crop(atlas_box),
                        (patch_x, patch_y),
                    )

                    original_rgb = np.asarray(neutral.crop(patch_box))[..., :3]
                    rebuilt_rgb = np.asarray(
                        reconstructed.crop(patch_box)
                    )[..., :3]
                    difference = np.abs(
                        original_rgb.astype(np.int16)
                        - rebuilt_rgb.astype(np.int16)
                    )
                    dark_outline = np.max(original_rgb, axis=2) < 80
                    outline_change = np.max(difference, axis=2) > 20
                    outline_change_ratio = np.count_nonzero(
                        dark_outline & outline_change
                    ) / max(1, np.count_nonzero(dark_outline))

                    label = f"{family}/{direction} frame {index}"
                    # The runtime bypasses this lossy WebP reconstruction at
                    # centered gaze. Keep the fallback stack bounded so its
                    # short activation ramp cannot destroy lids or lashes.
                    self.assertLess(float(np.mean(difference)), 2.5, label)
                    self.assertLess(outline_change_ratio, 0.35, label)
                    self.assertLessEqual(
                        int(np.count_nonzero(np.max(difference, axis=2) > 210)),
                        40,
                        label,
                    )

    def test_clean_base_only_changes_pixels_owned_by_the_movable_iris(self):
        for kind in ("neck", "body"):
            for direction in ("left", "right"):
                frames, masks = v13._neutral_sequence(kind, direction)
                for index, (frame, mask) in enumerate(zip(frames, masks)):
                    eye_base, movable_iris, _fixed_eyeline = (
                        v13.separate_eye_frame(frame, mask)
                    )
                    rebuilt = Image.alpha_composite(frame, eye_base)
                    difference = np.max(
                        np.abs(
                            np.asarray(frame)[..., :3].astype(np.int16)
                            - np.asarray(rebuilt)[..., :3].astype(np.int16)
                        ),
                        axis=2,
                    )
                    movable = np.asarray(movable_iris)[..., 3] > 0
                    protected = cv2.dilate(
                        movable.astype(np.uint8),
                        v13.ELLIPSE_3,
                        iterations=1,
                    ) == 0
                    self.assertLessEqual(
                        int(np.max(difference[protected])),
                        1,
                        f"{kind}/{direction} frame {index}",
                    )

    def test_moved_side_irises_keep_the_fixed_eyeline_pixel_exact(self):
        moves = ((-7, 0), (7, 0), (0, -4), (0, 4))
        for kind in ("neck", "body"):
            for direction in ("left", "right"):
                frames, masks = v13._neutral_sequence(kind, direction)
                for index, (frame, mask) in enumerate(zip(frames, masks)):
                    eye_base, movable_iris, fixed_eyeline = (
                        v13.separate_eye_frame(frame, mask)
                    )
                    base_alpha = np.asarray(eye_base)[..., 3]
                    iris_alpha = np.asarray(movable_iris)[..., 3]
                    line_alpha = np.asarray(fixed_eyeline)[..., 3]
                    label = f"{kind}/{direction} frame {index}"

                    self.assertTrue(
                        np.all(base_alpha[iris_alpha > 0] >= iris_alpha[iris_alpha > 0]),
                        label,
                    )
                    self.assertGreaterEqual(
                        int(np.count_nonzero(base_alpha)),
                        int(np.count_nonzero(iris_alpha)),
                        label,
                    )
                    self.assertGreater(int(np.count_nonzero(line_alpha)), 0, label)
                    self.assertEqual(
                        int(np.count_nonzero((iris_alpha > 0) & (line_alpha > 0))),
                        0,
                        label,
                    )

                    clean = Image.alpha_composite(frame, eye_base)
                    expected = np.asarray(frame)
                    protected = line_alpha > 0
                    for move_x, move_y in moves:
                        shifted = Image.new("RGBA", frame.size, (0, 0, 0, 0))
                        shifted.alpha_composite(
                            movable_iris,
                            (move_x, move_y),
                        )
                        moved = Image.alpha_composite(clean, shifted)
                        moved = Image.alpha_composite(moved, fixed_eyeline)
                        actual = np.asarray(moved)
                        self.assertTrue(
                            np.array_equal(actual[protected], expected[protected]),
                            f"{label} gaze {(move_x, move_y)}",
                        )

    def test_fixed_eyeline_never_freezes_the_iris_interior(self):
        for kind in ("neck", "body"):
            for direction in ("left", "right"):
                frames, masks = v13._neutral_sequence(kind, direction)
                for index, (frame, mask) in enumerate(zip(frames, masks)):
                    rgba, support = self._broad_support(frame, mask)
                    fixed, _movable = v13._fixed_eye_line_masks(
                        rgba,
                        support,
                    )
                    hsv = cv2.cvtColor(rgba[..., :3], cv2.COLOR_RGB2HSV)
                    yy = np.indices(support.shape)[0]
                    count, labels, stats, _centroids = (
                        cv2.connectedComponentsWithStats(support)
                    )
                    eyes = [
                        label
                        for label in range(1, count)
                        if stats[label, cv2.CC_STAT_AREA] >= 100
                    ]
                    self.assertEqual(len(eyes), 2)
                    for eye_number, label in enumerate(eyes):
                        component = labels == label
                        color_seed = (
                            component
                            & (hsv[..., 0] >= 105)
                            & (hsv[..., 0] <= 175)
                            & (hsv[..., 1] >= 48)
                            & (hsv[..., 2] >= 70)
                        )
                        color_seed = cv2.morphologyEx(
                            np.where(color_seed, 255, 0).astype(np.uint8),
                            cv2.MORPH_OPEN,
                            v13.ELLIPSE_3,
                        )
                        iris_hull = v13._convex_hull_mask(
                            v13._largest_component(color_seed)
                        ) > 0
                        top_profile = np.full(iris_hull.shape[1], np.nan)
                        for x in np.where(iris_hull.any(axis=0))[0]:
                            top_profile[x] = np.where(iris_hull[:, x])[0].min()
                        known = np.where(~np.isnan(top_profile))[0]
                        top_profile = np.interp(
                            np.arange(len(top_profile)),
                            known,
                            top_profile[known],
                        )
                        frozen_interior = (
                            (fixed > 0)
                            & component
                            & iris_hull
                            & (yy > top_profile[None, :])
                        )
                        self.assertEqual(
                            int(np.count_nonzero(frozen_interior)),
                            0,
                            (
                                f"{kind}/{direction} frame {index} "
                                f"eye {eye_number}"
                            ),
                        )

    def test_fixed_eyeline_keeps_the_independent_dark_upper_lash_ridge(self):
        reference_pixels = 0
        fixed_pixels = 0
        for kind in ("neck", "body"):
            for direction in ("left", "right"):
                frames, masks = v13._neutral_sequence(kind, direction)
                for frame, mask in zip(frames, masks):
                    rgba, support = self._broad_support(frame, mask)
                    fixed, _movable = v13._fixed_eye_line_masks(rgba, support)
                    hsv = cv2.cvtColor(rgba[..., :3], cv2.COLOR_RGB2HSV)
                    yy = np.indices(support.shape)[0]
                    count, labels, stats, _centroids = (
                        cv2.connectedComponentsWithStats(support)
                    )
                    for label in (
                        component
                        for component in range(1, count)
                        if stats[component, cv2.CC_STAT_AREA] >= 100
                    ):
                        component = labels == label
                        purple = (
                            component
                            & (hsv[..., 0] >= 105)
                            & (hsv[..., 0] <= 175)
                            & (hsv[..., 1] >= 48)
                            & (hsv[..., 2] >= 70)
                        )
                        purple = cv2.morphologyEx(
                            np.where(purple, 255, 0).astype(np.uint8),
                            cv2.MORPH_OPEN,
                            v13.ELLIPSE_3,
                        )
                        iris_hull = v13._convex_hull_mask(
                            v13._largest_component(purple)
                        ) > 0
                        hull_u8 = np.where(
                            iris_hull, 255, 0
                        ).astype(np.uint8)
                        outer = cv2.dilate(
                            hull_u8,
                            v13.ELLIPSE_7,
                            iterations=2,
                        ) > 0
                        top_profile = np.full(iris_hull.shape[1], np.nan)
                        for x in np.where(iris_hull.any(axis=0))[0]:
                            top_profile[x] = np.where(iris_hull[:, x])[0].min()
                        known = np.where(~np.isnan(top_profile))[0]
                        top_profile = np.interp(
                            np.arange(len(top_profile)),
                            known,
                            top_profile[known],
                        )
                        independent_ridge = (
                            component
                            & outer
                            & (hsv[..., 2] < 80)
                            & (yy <= top_profile[None, :])
                            & (yy >= top_profile[None, :] - 10)
                        )
                        reference_pixels += int(
                            np.count_nonzero(independent_ridge)
                        )
                        fixed_pixels += int(
                            np.count_nonzero(independent_ridge & (fixed > 0))
                        )
        self.assertGreater(reference_pixels, 0)
        self.assertGreaterEqual(fixed_pixels / reference_pixels, 0.90)

    def test_eye_masks_do_not_reach_pale_skin_outside_the_independent_iris(self):
        for kind in ("neck", "body"):
            for direction in ("left", "right"):
                frames, masks = v13._neutral_sequence(kind, direction)
                for index, (frame, mask) in enumerate(zip(frames, masks)):
                    eye_base, movable_iris, _fixed_eyeline = (
                        v13.separate_eye_frame(frame, mask)
                    )
                    rgba = np.asarray(frame.convert("RGBA"), dtype=np.uint8)
                    hsv = cv2.cvtColor(rgba[..., :3], cv2.COLOR_RGB2HSV)
                    base = np.asarray(eye_base)[..., 3] > 20
                    movable = np.asarray(movable_iris)[..., 3] > 20
                    _lower, independent_interior, _lash = (
                        self._independent_eye_geometry(frame, mask)
                    )
                    strict_pale = (hsv[..., 1] < 65) & (hsv[..., 2] > 165)
                    overreach = (
                        (base | movable)
                        & strict_pale
                        & ~independent_interior
                    )
                    self.assertEqual(
                        int(np.count_nonzero(overreach)),
                        0,
                        f"{kind}/{direction} frame {index}",
                    )

    def test_safe_eraser_never_expands_into_pale_sclera_or_skin(self):
        for kind in ("neck", "body"):
            for direction in ("left", "right"):
                frames, masks = v13._neutral_sequence(kind, direction)
                for index, (frame, mask) in enumerate(zip(frames, masks)):
                    eye_base, movable_iris, _fixed_eyeline = (
                        v13.separate_eye_frame(frame, mask)
                    )
                    rgba = np.asarray(frame.convert("RGBA"), dtype=np.uint8)
                    hsv = cv2.cvtColor(rgba[..., :3], cv2.COLOR_RGB2HSV)
                    base = np.asarray(eye_base)[..., 3] > 20
                    movable = np.asarray(movable_iris)[..., 3] > 20
                    expanded_only = base & ~movable
                    pale_or_skin = (hsv[..., 1] < 65) & (hsv[..., 2] > 165)
                    self.assertEqual(
                        int(np.count_nonzero(expanded_only & pale_or_skin)),
                        0,
                        f"{kind}/{direction} frame {index}",
                    )

    def test_eye_base_covers_the_independent_lower_iris_reference(self):
        for kind in ("neck", "body"):
            for direction in ("left", "right"):
                frames, masks = v13._neutral_sequence(kind, direction)
                for index, (frame, mask) in enumerate(zip(frames, masks)):
                    eye_base, movable_iris, fixed_eyeline = (
                        v13.separate_eye_frame(frame, mask)
                    )
                    (
                        independent_iris,
                        independent_interior,
                        _independent_lash,
                    ) = self._independent_eye_geometry(
                        frame,
                        mask,
                    )
                    base = np.asarray(eye_base)[..., 3] > 20
                    movable = np.asarray(movable_iris)[..., 3] > 20
                    fixed = np.asarray(fixed_eyeline)[..., 3] > 20
                    count, labels, stats, _centroids = (
                        cv2.connectedComponentsWithStats(
                            np.where(movable, 255, 0).astype(np.uint8)
                        )
                    )
                    movable_components = [
                        label
                        for label in range(1, count)
                        if stats[label, cv2.CC_STAT_AREA] >= 8
                    ]
                    main_components = [
                        label
                        for label in movable_components
                        if stats[label, cv2.CC_STAT_AREA] >= 300
                    ]
                    self.assertEqual(
                        len(main_components),
                        2,
                        f"{kind}/{direction} frame {index}",
                    )
                    for label in movable_components:
                        self.assertTrue(
                            np.any((labels == label) & independent_interior),
                            f"{kind}/{direction} frame {index} component {label}",
                        )
                    self.assertEqual(
                        int(np.count_nonzero(independent_iris & ~base)),
                        0,
                        f"{kind}/{direction} frame {index}",
                    )
                    self.assertEqual(
                        int(np.count_nonzero(independent_iris & ~movable)),
                        0,
                        f"{kind}/{direction} frame {index}",
                    )
                    self.assertEqual(
                        int(np.count_nonzero(independent_iris & fixed)),
                        0,
                        f"{kind}/{direction} frame {index}",
                    )

    def test_independent_upper_lash_is_fixed_and_never_erased(self):
        for kind in ("neck", "body"):
            for direction in ("left", "right"):
                frames, masks = v13._neutral_sequence(kind, direction)
                for index, (frame, mask) in enumerate(zip(frames, masks)):
                    eye_base, movable_iris, fixed_eyeline = (
                        v13.separate_eye_frame(frame, mask)
                    )
                    _lower, _interior, lash = self._independent_eye_geometry(
                        frame,
                        mask,
                    )
                    base = np.asarray(eye_base)[..., 3] > 20
                    movable = np.asarray(movable_iris)[..., 3] > 20
                    fixed = np.asarray(fixed_eyeline)[..., 3] > 20
                    label = f"{kind}/{direction} frame {index}"
                    self.assertGreater(int(np.count_nonzero(lash)), 0, label)
                    self.assertEqual(int(np.count_nonzero(lash & base)), 0, label)
                    self.assertEqual(
                        int(np.count_nonzero(lash & movable)),
                        0,
                        label,
                    )
                    self.assertEqual(
                        int(np.count_nonzero(lash & ~fixed)),
                        0,
                        label,
                    )

    def test_synthetic_iris_moves_without_leaving_the_original_iris(self):
        frame = Image.new("RGBA", (128, 96), (244, 208, 205, 255))
        draw = ImageDraw.Draw(frame)
        draw.ellipse((30, 30, 98, 70), fill=(246, 238, 242, 255))
        draw.ellipse((55, 32, 73, 68), fill=(89, 52, 170, 255))
        draw.ellipse((61, 38, 68, 61), fill=(31, 18, 70, 255))

        raw_mask = np.zeros((96, 128), dtype=np.float32)
        yy, xx = np.ogrid[:96, :128]
        # Reproduce the optical-flow error seen at strong side angles: the
        # propagated mask is eight pixels left of the actual painted iris.
        raw_mask[((xx - 56) / 10) ** 2 + ((yy - 50) / 19) ** 2 <= 1] = 1

        eye_base, movable_iris, _fixed_eyeline = v13.separate_eye_frame(
            frame,
            raw_mask,
        )
        underpaint = Image.alpha_composite(frame, eye_base)

        movable_bbox = movable_iris.getchannel("A").point(
            lambda value: 255 if value > 20 else 0
        ).getbbox()
        self.assertIsNotNone(movable_bbox)
        self.assertGreaterEqual((movable_bbox[0] + movable_bbox[2]) / 2, 62)

        original_center = underpaint.getpixel((64, 50))[:3]
        self.assertGreater(min(original_center), 180)
        self.assertLess(max(original_center) - min(original_center), 55)

        shifted = Image.new("RGBA", frame.size, (0, 0, 0, 0))
        shifted.alpha_composite(movable_iris, (20, 0))
        moved = Image.alpha_composite(underpaint, shifted)
        moved_original = moved.getpixel((64, 50))[:3]
        moved_center = moved.getpixel((84, 50))[:3]
        self.assertGreater(min(moved_original), 180)
        self.assertGreater(moved_center[2] - moved_center[0], 35)

        base_alpha = np.asarray(eye_base)[..., 3]
        iris_alpha = np.asarray(movable_iris)[..., 3]
        self.assertTrue(
            np.all(base_alpha[iris_alpha > 0] >= iris_alpha[iris_alpha > 0])
        )
        self.assertGreaterEqual(
            int(np.count_nonzero(base_alpha)),
            int(np.count_nonzero(iris_alpha)),
        )

    def test_v13_side_atlases_use_safe_split_iris_ownership(self):
        for family in ("neck-atlases", "body-atlases"):
            for direction in ("left", "right"):
                kind = "neck" if family == "neck-atlases" else "body"
                source_frames, source_masks = v13._neutral_sequence(
                    kind,
                    direction,
                )
                patch_box = v13.v10.scaled_roi(
                    v13.v11.PATCH_ROIS[direction]["blink"]
                )
                base_path = (
                    ROOT
                    / "assets/character-v13"
                    / family
                    / f"{direction}-eye-base-v1.webp"
                )
                iris_path = (
                    ROOT
                    / "assets/character-v13"
                    / family
                    / f"{direction}-irises-v1.webp"
                )
                line_path = (
                    ROOT
                    / "assets/character-v13"
                    / family
                    / f"{direction}-eye-line-v1.png"
                )
                self.assertTrue(base_path.exists(), base_path)
                self.assertTrue(iris_path.exists(), iris_path)
                self.assertTrue(line_path.exists(), line_path)

                base = Image.open(base_path).convert("RGBA")
                iris = Image.open(iris_path).convert("RGBA")
                eye_line = Image.open(line_path).convert("RGBA")
                frame_width = base.width // 4
                frame_height = base.height // 4
                for index in range(16):
                    x = (index % 4) * frame_width
                    y = (index // 4) * frame_height
                    box = (x, y, x + frame_width, y + frame_height)
                    base_alpha = np.asarray(base.crop(box))[..., 3]
                    iris_alpha = np.asarray(iris.crop(box))[..., 3]
                    line_alpha = np.asarray(eye_line.crop(box))[..., 3]
                    base_area = np.count_nonzero(base_alpha > 20)
                    iris_area = np.count_nonzero(iris_alpha > 20)
                    self.assertGreater(base_area, 0)
                    self.assertGreater(iris_area, 0)
                    self.assertTrue(
                        np.all(
                            base_alpha[iris_alpha > 20]
                            >= iris_alpha[iris_alpha > 20]
                        ),
                        f"{family}/{direction} frame {index}",
                    )
                    self.assertGreaterEqual(
                        base_area,
                        iris_area,
                        f"{family}/{direction} frame {index}",
                    )
                    self.assertGreater(
                        int(np.count_nonzero(line_alpha > 20)),
                        0,
                        f"{family}/{direction} frame {index}",
                    )
                    self.assertEqual(
                        int(
                            np.count_nonzero(
                                (iris_alpha > 20) & (line_alpha > 20)
                            )
                        ),
                        0,
                        f"{family}/{direction} frame {index}",
                    )
                    # Each main eye is a large component. Smaller antialiased
                    # fringes are valid only when independently tied to an iris
                    # interior; detached upper-lash islands are not.
                    iris_binary = np.where(iris_alpha > 20, 255, 0).astype(
                        np.uint8
                    )
                    component_count, labels, stats, _centroids = (
                        cv2.connectedComponentsWithStats(iris_binary)
                    )
                    eye_components = [
                        component
                        for component in range(1, component_count)
                        if stats[component, cv2.CC_STAT_AREA] >= 8
                    ]
                    main_components = [
                        component
                        for component in eye_components
                        if stats[component, cv2.CC_STAT_AREA] >= 300
                    ]
                    self.assertEqual(
                        len(main_components),
                        2,
                        f"{family}/{direction} frame {index}",
                    )
                    lower, interior, lash = self._independent_eye_geometry(
                        source_frames[index],
                        source_masks[index],
                    )
                    left, top, right, bottom = patch_box
                    lower = lower[top:bottom, left:right]
                    interior = interior[top:bottom, left:right]
                    lash = lash[top:bottom, left:right]
                    for component in eye_components:
                        self.assertTrue(
                            np.any((labels == component) & interior),
                            (
                                f"{family}/{direction} frame {index} "
                                f"component {component}"
                            ),
                        )
                    base_owned = base_alpha > 20
                    iris_owned = iris_alpha > 20
                    line_owned = line_alpha > 20
                    label = f"{family}/{direction} frame {index}"
                    self.assertEqual(
                        int(np.count_nonzero(lower & ~base_owned)),
                        0,
                        label,
                    )
                    self.assertEqual(
                        int(np.count_nonzero(lower & ~iris_owned)),
                        0,
                        label,
                    )
                    self.assertEqual(
                        int(np.count_nonzero(lower & line_owned)),
                        0,
                        label,
                    )
                    self.assertEqual(
                        int(np.count_nonzero(lash & base_owned)),
                        0,
                        label,
                    )
                    self.assertEqual(
                        int(np.count_nonzero(lash & iris_owned)),
                        0,
                        label,
                    )
                    self.assertEqual(
                        int(np.count_nonzero(lash & ~line_owned)),
                        0,
                        label,
                    )


if __name__ == "__main__":
    unittest.main()
