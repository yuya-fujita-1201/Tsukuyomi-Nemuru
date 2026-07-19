import sys
import unittest
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_character_v14 as v14  # noqa: E402


class CharacterV14EyeQualityTests(unittest.TestCase):
    @staticmethod
    def _main_components(alpha: np.ndarray, minimum_area: int = 20):
        count, labels, stats, centroids = cv2.connectedComponentsWithStats(
            np.where(alpha > 20, 255, 0).astype(np.uint8)
        )
        components = []
        for label in range(1, count):
            area = int(stats[label, cv2.CC_STAT_AREA])
            if area < minimum_area:
                continue
            components.append(
                {
                    "label": label,
                    "area": area,
                    "bbox": tuple(int(value) for value in stats[label, :4]),
                    "centroid": tuple(float(value) for value in centroids[label]),
                    "mask": labels == label,
                }
            )
        return sorted(components, key=lambda component: component["centroid"][0])

    @staticmethod
    def _atlas_frame(atlas: Image.Image, index: int) -> Image.Image:
        width = atlas.width // v14.ATLAS_COLUMNS
        height = atlas.height // v14.ATLAS_ROWS
        left = (index % v14.ATLAS_COLUMNS) * width
        top = (index // v14.ATLAS_COLUMNS) * height
        return atlas.crop((left, top, left + width, top + height))

    @staticmethod
    def _luminous_ratio(rgba: np.ndarray, mask: np.ndarray) -> float:
        hsv = cv2.cvtColor(rgba[..., :3], cv2.COLOR_RGB2HSV)
        luminous = (hsv[..., 1] < 92) & (hsv[..., 2] > 205)
        return float(np.count_nonzero(luminous & mask)) / max(
            1,
            int(np.count_nonzero(mask)),
        )

    @staticmethod
    def _moon_ring_ratio(rgba: np.ndarray, component: dict) -> float:
        left, top, width, height = component["bbox"]
        yy, xx = np.indices(rgba.shape[:2])
        center_x = left + 0.50 * width
        center_y = top + 0.40 * height
        radius = np.sqrt(
            ((xx - center_x) / (0.18 * width)) ** 2
            + ((yy - center_y) / (0.20 * height)) ** 2
        )
        ring = component["mask"] & (radius >= 0.5) & (radius <= 1.0)
        return CharacterV14EyeQualityTests._luminous_ratio(rgba, ring)

    @staticmethod
    def _independent_far_upper_lash_core(
        source_patch_rgba: np.ndarray,
        raw_mask: np.ndarray,
        patch_box: tuple[int, int, int, int],
    ) -> np.ndarray:
        """Find the far upper lash from source pixels, not v14 lash_guard."""
        binary = np.where(raw_mask > 0.04, 255, 0).astype(np.uint8)
        count, labels, stats, centroids = cv2.connectedComponentsWithStats(binary)
        iris_priors = [
            label
            for label in range(1, count)
            if int(stats[label, cv2.CC_STAT_AREA]) >= 50
        ]
        if len(iris_priors) != 2:
            raise AssertionError(f"raw iris prior count was {len(iris_priors)}")

        # The screen-right eye is the far eye at the body/right endpoint.
        far_label = max(iris_priors, key=lambda label: centroids[label][0])
        full_left, full_top, width, _height = (
            int(value) for value in stats[far_label, :4]
        )
        patch_left, patch_top, _patch_right, _patch_bottom = patch_box
        left = full_left - patch_left
        top = full_top - patch_top
        right = left + width

        hsv = cv2.cvtColor(source_patch_rgba[..., :3], cv2.COLOR_RGB2HSV)
        dark_source_line = (
            (source_patch_rgba[..., 3] > 200)
            & (hsv[..., 1] >= 12)
            & (hsv[..., 2] < 80)
        )
        corridor = np.zeros(dark_source_line.shape, dtype=np.uint8)
        y0 = max(0, top - 8)
        y1 = min(corridor.shape[0], top + 8)
        x0 = max(0, left - 6)
        x1 = min(corridor.shape[1], right + 6)
        corridor[y0:y1, x0:x1] = 1

        # Reject isolated iris sparkles; keep the horizontal lash ridge.
        horizontal = cv2.morphologyEx(
            np.where(dark_source_line & (corridor > 0), 255, 0).astype(np.uint8),
            cv2.MORPH_OPEN,
            np.ones((1, 5), dtype=np.uint8),
        )
        component_count, component_labels, component_stats, _ = (
            cv2.connectedComponentsWithStats(horizontal)
        )
        lash = np.zeros(horizontal.shape, dtype=bool)
        minimum_width = max(7, int(round(width * 0.45)))
        for label in range(1, component_count):
            area = int(component_stats[label, cv2.CC_STAT_AREA])
            span = int(component_stats[label, cv2.CC_STAT_WIDTH])
            if area >= 6 and span >= minimum_width:
                lash |= component_labels == label
        if int(np.count_nonzero(lash)) < 100:
            raise AssertionError("independent far upper-lash mask became vacuous")
        return lash

    @staticmethod
    def _shift_rgba_patch(patch: Image.Image, x: int, y: int = 0) -> Image.Image:
        shifted = Image.new("RGBA", patch.size, (0, 0, 0, 0))
        shifted.alpha_composite(patch, (x, y))
        return shifted

    def test_front_irises_face_camera_fill_the_lower_lid_and_keep_the_luminous_left_eye(self):
        iris_path = (
            ROOT / "assets/character-v14/parts/aligned-v1/irises.png"
        )
        iris = np.asarray(Image.open(iris_path).convert("RGBA"), dtype=np.uint8)
        components = self._main_components(iris[..., 3], minimum_area=100)

        self.assertEqual(len(components), 2)
        # v5 is the approved straight-on identity reference.  v13 had drifted
        # roughly 13 px outward on both sides, creating a divergent gaze.
        expected_centers = ((455, 478), (630, 478))
        for component, expected in zip(components, expected_centers):
            center_x, center_y = component["centroid"]
            self.assertLessEqual(abs(center_x - expected[0]), 2.0)
            self.assertLessEqual(abs(center_y - expected[1]), 2.0)
            left, top, width, height = component["bbox"]
            self.assertLessEqual(top, 454)
            self.assertGreaterEqual(top + height, 502)
            self.assertGreaterEqual(width, 46)
            self.assertGreaterEqual(height, 48)

        dark_eye, luminous_eye = components
        dark_ratio = self._moon_ring_ratio(iris, dark_eye)
        luminous_ratio = self._moon_ring_ratio(iris, luminous_eye)
        self.assertGreaterEqual(luminous_ratio, 0.22)
        self.assertGreater(
            luminous_ratio,
            dark_ratio + 0.095,
            "screen-right / character-left iris lost its pale luminous ring",
        )

        previous = np.asarray(
            Image.open(
                ROOT / "assets/character-v13/parts/aligned-v1/irises.png"
            ).convert("RGBA"),
            dtype=np.uint8,
        )
        for current_component, previous_component in zip(
            components,
            self._main_components(previous[..., 3], minimum_area=100),
        ):
            current_bottom = (
                current_component["bbox"][1] + current_component["bbox"][3]
            )
            previous_bottom = (
                previous_component["bbox"][1] + previous_component["bbox"][3]
            )
            self.assertGreaterEqual(current_bottom, previous_bottom + 1)

    def test_front_open_eyelids_are_exact_mirrors_without_changing_the_iris_identity(self):
        eye_base = np.asarray(
            Image.open(
                ROOT / "assets/character-v14/parts/aligned-v1/eye_base_open.png"
            ).convert("RGBA"),
            dtype=np.uint8,
        )
        components = self._main_components(eye_base[..., 3], minimum_area=100)
        self.assertEqual(len(components), 2)

        left, top, width, _height = components[0]["bbox"]
        right_left, right_top, right_width, _right_height = components[1]["bbox"]
        self.assertEqual((top, width), (right_top, right_width))
        crops = (
            eye_base[top:480, left : left + width],
            eye_base[right_top:480, right_left : right_left + right_width],
        )
        np.testing.assert_array_equal(
            crops[0],
            np.flip(crops[1], axis=1),
            err_msg=(
                "screen-right upper lid must use the same mirrored opening, "
                "corner heights, curve, and line weight as screen-left"
            ),
        )

        # The character-left iris intentionally keeps its separate moon-ring
        # treatment; eyelid symmetry must never be implemented by copying the
        # complete eye or its iris texture.
        irises = np.asarray(
            Image.open(
                ROOT / "assets/character-v14/parts/aligned-v1/irises.png"
            ).convert("RGBA"),
            dtype=np.uint8,
        )
        iris_components = self._main_components(irises[..., 3], minimum_area=100)
        self.assertEqual(len(iris_components), 2)
        left_component, right_component = iris_components
        self.assertGreater(
            self._moon_ring_ratio(irises, right_component),
            self._moon_ring_ratio(irises, left_component) + 0.095,
        )

    def test_front_blink_has_a_symmetric_half_key_with_fixed_eye_corners(self):
        parts_root = ROOT / "assets/character-v14/parts/aligned-v1"
        paths = {
            "open": parts_root / "eye_base_open.png",
            "half": parts_root / "eyes_half_closed.png",
            "closed": parts_root / "eyes_closed.png",
        }
        for path in paths.values():
            self.assertTrue(path.exists(), path)

        states = {
            name: np.asarray(Image.open(path).convert("RGBA"), dtype=np.uint8)
            for name, path in paths.items()
        }
        for rgba in states.values():
            self.assertEqual(rgba.shape, (1448, 1086, 4))

        left_anchors = ((389, 471), (496, 474))
        right_anchors = tuple((1085 - x, y) for x, y in reversed(left_anchors))
        for state_name, rgba in states.items():
            hsv = cv2.cvtColor(rgba[..., :3], cv2.COLOR_RGB2HSV)
            dark_line = (rgba[..., 3] > 20) & (hsv[..., 2] < 205)
            for x, y in (*left_anchors, *right_anchors):
                self.assertGreater(
                    int(np.count_nonzero(dark_line[y - 1 : y + 2, x - 1 : x + 2])),
                    0,
                    f"{state_name} lost fixed corner {(x, y)}",
                )

        # The half key is an upper-lid/skin cover.  It must not repaint or
        # displace the lower lid, whose open artwork remains underneath.
        half_alpha = states["half"][..., 3]
        self.assertEqual(
            int(np.count_nonzero(half_alpha[500:508, 388:698])),
            0,
        )

        def center_line_y(rgba: np.ndarray, left: int, right: int) -> float:
            hsv = cv2.cvtColor(rgba[..., :3], cv2.COLOR_RGB2HSV)
            dark = (rgba[..., 3] > 20) & (hsv[..., 2] < 205)
            center = (left + right) // 2
            ys, _xs = np.where(dark[440:510, center - 3 : center + 4])
            self.assertGreater(len(ys), 0)
            return float(np.median(ys + 440))

        left_y = {
            name: center_line_y(rgba, 389, 496)
            for name, rgba in states.items()
        }
        self.assertLess(left_y["open"], left_y["half"])
        self.assertLess(left_y["half"], left_y["closed"])
        ratio = (left_y["half"] - left_y["open"]) / (
            left_y["closed"] - left_y["open"]
        )
        self.assertAlmostEqual(ratio, 0.5, delta=0.12)

        for state_name in ("half", "closed"):
            left = states[state_name][440:510, 388:498]
            right = states[state_name][440:510, 588:698]
            np.testing.assert_array_equal(
                left[..., 3],
                np.flip(right[..., 3], axis=1),
                err_msg=f"{state_name} blink silhouette is not mirrored",
            )

    def test_all_front_mouth_keys_are_only_shifted_four_pixels_to_the_face_center(self):
        names = (
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
        for name in names:
            current = np.asarray(
                Image.open(
                    ROOT / f"assets/character-v14/parts/aligned-v1/{name}.png"
                ).convert("RGBA"),
                dtype=np.uint8,
            )
            previous = np.asarray(
                Image.open(
                    ROOT / f"assets/character-v13/parts/aligned-v1/{name}.png"
                ).convert("RGBA"),
                dtype=np.uint8,
            )
            self.assertEqual(current.shape, (1448, 1086, 4), name)
            np.testing.assert_array_equal(current[:, :4], 0, err_msg=name)
            np.testing.assert_array_equal(
                current[:, 4:],
                previous[:, :-4],
                err_msg=f"{name} changed shape instead of a pure +4px X shift",
            )
            alpha = current[..., 3]
            ys, xs = np.where(alpha > 0)
            self.assertEqual(
                (int(xs.min()) + int(xs.max()) + 1) / 2,
                547.0,
                name,
            )

    def test_all_side_eye_layers_are_lossless_and_movable_layers_have_only_two_irises(self):
        for kind in ("neck", "body"):
            atlas_root = ROOT / f"assets/character-v14/{kind}-atlases"
            for direction in ("left", "right"):
                paths = {
                    state: atlas_root / f"{direction}-{state}-v1.png"
                    for state in ("eye-base", "irises", "eye-line")
                }
                for path in paths.values():
                    self.assertTrue(path.exists(), path)

                atlases = {
                    state: Image.open(path).convert("RGBA")
                    for state, path in paths.items()
                }
                for index in range(v14.FRAME_COUNT):
                    frames = {
                        state: np.asarray(
                            self._atlas_frame(atlas, index),
                            dtype=np.uint8,
                        )
                        for state, atlas in atlases.items()
                    }
                    components = self._main_components(
                        frames["irises"][..., 3],
                        minimum_area=8,
                    )
                    label = f"{kind}/{direction}/frame-{index:02d}"
                    self.assertEqual(len(components), 2, label)
                    self.assertTrue(
                        all(component["area"] >= 80 for component in components),
                        label,
                    )
                    for component in components:
                        soft_edge = (
                            component["mask"]
                            & (frames["irises"][..., 3] > 20)
                            & (frames["irises"][..., 3] < 235)
                        )
                        self.assertGreaterEqual(
                            int(np.count_nonzero(soft_edge)),
                            4,
                            f"{label} has a completely hard or clipped iris edge",
                        )

                    iris_alpha = frames["irises"][..., 3]
                    base_alpha = frames["eye-base"][..., 3]
                    line_alpha = frames["eye-line"][..., 3]
                    base_hsv = cv2.cvtColor(
                        frames["eye-base"][..., :3],
                        cv2.COLOR_RGB2HSV,
                    )
                    overlap = (iris_alpha > 20) & (line_alpha > 20)
                    upper_overlap = np.zeros(overlap.shape, dtype=bool)
                    for component in components:
                        left, top, width, height = component["bbox"]
                        upper_overlap[
                            top : top + int(np.ceil(height * 0.55)),
                            left : left + width,
                        ] |= overlap[
                            top : top + int(np.ceil(height * 0.55)),
                            left : left + width,
                        ]
                    self.assertEqual(
                        int(np.count_nonzero(upper_overlap)),
                        0,
                        f"{label}: movable iris overlaps the fixed upper lash",
                    )
                    self.assertEqual(
                        int(
                            np.count_nonzero(
                                (iris_alpha > 20)
                                & (base_alpha <= 20)
                                & (line_alpha <= 20)
                            )
                        ),
                        0,
                        label,
                    )
                    self.assertEqual(
                        int(
                            np.count_nonzero(
                                (iris_alpha > 20)
                                & (base_alpha > 20)
                                & (base_hsv[..., 0] >= 100)
                                & (base_hsv[..., 0] <= 179)
                                & (base_hsv[..., 1] >= 28)
                            )
                        ),
                        0,
                        f"{label} retained purple iris color in eye-base",
                    )

    def test_right_turn_keeps_the_screen_right_luminous_iris_in_every_frame(self):
        for kind in ("neck", "body"):
            path = (
                ROOT
                / f"assets/character-v14/{kind}-atlases/right-irises-v1.png"
            )
            atlas = Image.open(path).convert("RGBA")
            for index in range(v14.FRAME_COUNT):
                rgba = np.asarray(self._atlas_frame(atlas, index), dtype=np.uint8)
                components = self._main_components(rgba[..., 3], minimum_area=20)
                self.assertEqual(len(components), 2, f"{kind}/right/{index}")
                dark_ratio = self._moon_ring_ratio(rgba, components[0])
                luminous_ratio = self._moon_ring_ratio(rgba, components[1])
                self.assertGreaterEqual(
                    luminous_ratio,
                    0.22,
                    f"{kind}/right/frame-{index:02d}",
                )
                self.assertGreater(
                    luminous_ratio,
                    dark_ratio + 0.095,
                    f"{kind}/right/frame-{index:02d}",
                )

    def test_terminal_turns_erase_the_original_iris_and_never_move_lashes(self):
        for kind in ("neck", "body"):
            for direction in ("left", "right"):
                frames, raw_masks = v14._neutral_sequence(kind, direction)
                source = frames[-1]
                shapes = v14.detect_side_iris_shapes(source, raw_masks[-1])
                eye_base, irises, eye_line = v14.separate_side_eye_frame(
                    source,
                    raw_masks[-1],
                )
                base_alpha = np.asarray(eye_base)[..., 3]
                iris_alpha = np.asarray(irises)[..., 3]
                line_alpha = np.asarray(eye_line)[..., 3]
                source_rgba = np.asarray(source.convert("RGBA"), dtype=np.uint8)
                hsv = cv2.cvtColor(source_rgba[..., :3], cv2.COLOR_RGB2HSV)

                for shape in shapes:
                    lower = shape.mask & (
                        np.indices(shape.mask.shape)[0] >= shape.center[1]
                    )
                    self.assertEqual(
                        int(np.count_nonzero(lower & (base_alpha <= 20))),
                        0,
                    )
                    self.assertEqual(
                        int(np.count_nonzero(shape.lash_guard & (iris_alpha > 20))),
                        0,
                    )
                    self.assertEqual(
                        int(np.count_nonzero(shape.lash_guard & (line_alpha <= 20))),
                        0,
                    )

                    baked_iris = (
                        lower
                        & (hsv[..., 0] >= 100)
                        & (hsv[..., 0] <= 179)
                        & (hsv[..., 1] >= 35)
                    )
                    clean_rgb = np.asarray(
                        Image.alpha_composite(source, eye_base)
                    )[..., :3]
                    clean_hsv = cv2.cvtColor(clean_rgb, cv2.COLOR_RGB2HSV)
                    residue = (
                        baked_iris
                        & (clean_hsv[..., 0] >= 100)
                        & (clean_hsv[..., 0] <= 179)
                        & (clean_hsv[..., 1] >= 35)
                    )
                    self.assertLessEqual(
                        int(np.count_nonzero(residue)),
                        max(2, int(np.count_nonzero(baked_iris) * 0.01)),
                        f"{kind}/{direction}/terminal old iris residue",
                    )

    def test_body_right_terminal_far_upper_lash_is_pixel_stable_at_horizontal_gaze_extremes(self):
        source_frames, raw_masks = v14._neutral_sequence("body", "right")
        source = source_frames[-1].convert("RGBA")
        raw_mask = raw_masks[-1]
        patch_box = v14.v10.scaled_roi(v14.v11.PATCH_ROIS["right"]["blink"])
        source_patch = np.asarray(source.crop(patch_box), dtype=np.uint8)

        atlas_root = ROOT / "assets/character-v14/body-atlases"
        layers = {}
        for state in ("eye-base", "irises", "eye-line"):
            atlas = Image.open(atlas_root / f"right-{state}-v1.png").convert(
                "RGBA"
            )
            layers[state] = self._atlas_frame(atlas, v14.FRAME_COUNT - 1)

        lash = self._independent_far_upper_lash_core(
            source_patch,
            raw_mask,
            patch_box,
        )
        base_alpha = np.asarray(layers["eye-base"], dtype=np.uint8)[..., 3]
        iris_alpha = np.asarray(layers["irises"], dtype=np.uint8)[..., 3]
        line_rgba = np.asarray(layers["eye-line"], dtype=np.uint8)
        line_alpha = line_rgba[..., 3]

        self.assertEqual(
            int(np.count_nonzero(lash & (iris_alpha > 20))),
            0,
            "body/right terminal far upper lash leaked into movable iris",
        )

        patch_left, patch_top, _right, _bottom = patch_box
        for move_x in (-5, 5):
            shifted_iris = self._shift_rgba_patch(layers["irises"], move_x)
            shifted_alpha = np.asarray(shifted_iris, dtype=np.uint8)[..., 3]
            overwrite_risk = (base_alpha > 20) | (shifted_alpha > 20)
            unprotected = lash & overwrite_risk & (line_alpha < 245)
            self.assertEqual(
                int(np.count_nonzero(unprotected)),
                0,
                f"body/right terminal gaze {move_x:+d}: upper lash is erased without a fixed-line restore",
            )

            rendered = source.copy()
            rendered.alpha_composite(layers["eye-base"], (patch_left, patch_top))
            rendered.alpha_composite(shifted_iris, (patch_left, patch_top))
            rendered.alpha_composite(layers["eye-line"], (patch_left, patch_top))
            actual = np.asarray(rendered.crop(patch_box), dtype=np.uint8)
            delta = np.max(
                np.abs(actual.astype(np.int16) - source_patch.astype(np.int16)),
                axis=2,
            )
            broken = lash & (delta > 4)
            broken_count, _labels, broken_stats, _centroids = (
                cv2.connectedComponentsWithStats(
                    np.where(broken, 255, 0).astype(np.uint8)
                )
            )
            largest_break = max(
                (
                    int(broken_stats[label, cv2.CC_STAT_AREA])
                    for label in range(1, broken_count)
                ),
                default=0,
            )
            self.assertEqual(
                largest_break,
                0,
                f"body/right terminal gaze {move_x:+d}: upper-lash RGBA changed; max delta={int(delta[lash].max())}",
            )

    def test_body_right_terminal_far_upper_lash_keeps_its_antialiased_center_bridge(self):
        """Keep the user-reported dark-purple lash bridge above the far iris."""
        source_frames, _raw_masks = v14._neutral_sequence("body", "right")
        source = source_frames[-1].convert("RGBA")
        patch_box = v14.v10.scaled_roi(v14.v11.PATCH_ROIS["right"]["blink"])
        source_patch = np.asarray(source.crop(patch_box), dtype=np.uint8)

        atlas_root = ROOT / "assets/character-v14/body-atlases"
        layers = {}
        for state in ("eye-base", "irises", "eye-line"):
            atlas = Image.open(atlas_root / f"right-{state}-v1.png").convert(
                "RGBA"
            )
            layers[state] = self._atlas_frame(atlas, v14.FRAME_COUNT - 1)

        # The black lash core on both sides was already protected.  The center
        # bridge is antialiased against the purple iris, so its source value is
        # V=86..133 rather than V<80.  These are the exact source pixels exposed
        # as a white rectangular notch in the user's gazeX=-1/+1 captures.
        patch_left, patch_top, _right, _bottom = patch_box
        bridge = np.zeros(source_patch.shape[:2], dtype=bool)
        bridge_y = 330 - patch_top
        bridge_x0 = 507 - patch_left
        bridge_x1 = 518 - patch_left
        bridge[bridge_y, bridge_x0:bridge_x1] = True
        source_hsv = cv2.cvtColor(source_patch[..., :3], cv2.COLOR_RGB2HSV)
        bridge &= (
            (source_patch[..., 3] > 200)
            & (source_hsv[..., 1] >= 12)
            & (source_hsv[..., 2] < 145)
        )
        self.assertEqual(
            int(np.count_nonzero(bridge)),
            11,
            "body/right far upper-lash AA bridge source geometry drifted",
        )

        base_alpha = np.asarray(layers["eye-base"], dtype=np.uint8)[..., 3]
        iris_alpha = np.asarray(layers["irises"], dtype=np.uint8)[..., 3]
        line_alpha = np.asarray(layers["eye-line"], dtype=np.uint8)[..., 3]
        self.assertEqual(
            int(np.count_nonzero(bridge & (base_alpha > 20))),
            0,
            "white eye-base still owns the upper-lash AA bridge",
        )
        self.assertEqual(
            int(np.count_nonzero(bridge & (iris_alpha > 20))),
            0,
            "movable iris still owns the upper-lash AA bridge",
        )
        self.assertEqual(
            int(np.count_nonzero(bridge & (line_alpha < 245))),
            0,
            "fixed eye-line does not fully restore the upper-lash AA bridge",
        )

        for move_x in (-5, 5):
            rendered = source.copy()
            rendered.alpha_composite(
                layers["eye-base"],
                (patch_left, patch_top),
            )
            rendered.alpha_composite(
                self._shift_rgba_patch(layers["irises"], move_x),
                (patch_left, patch_top),
            )
            rendered.alpha_composite(
                layers["eye-line"],
                (patch_left, patch_top),
            )
            actual = np.asarray(rendered.crop(patch_box), dtype=np.uint8)
            delta = np.max(
                np.abs(actual.astype(np.int16) - source_patch.astype(np.int16)),
                axis=2,
            )
            self.assertEqual(
                int(np.count_nonzero(bridge & (delta > 0))),
                0,
                (
                    f"body/right terminal gaze {move_x:+d}: upper-lash AA "
                    f"bridge changed; max delta={int(delta[bridge].max())}"
                ),
            )

    def test_body_right_terminal_near_upper_lash_keeps_its_antialiased_center_bridge(self):
        """Keep the circled screen-left lash bridge above the near iris."""
        source_frames, _raw_masks = v14._neutral_sequence("body", "right")
        source = source_frames[-1].convert("RGBA")
        patch_box = v14.v10.scaled_roi(v14.v11.PATCH_ROIS["right"]["blink"])
        source_patch = np.asarray(source.crop(patch_box), dtype=np.uint8)

        atlas_root = ROOT / "assets/character-v14/body-atlases"
        layers = {}
        for state in ("eye-base", "irises", "eye-line"):
            atlas = Image.open(atlas_root / f"right-{state}-v1.png").convert(
                "RGBA"
            )
            layers[state] = self._atlas_frame(atlas, v14.FRAME_COUNT - 1)

        # The user's red circle identifies the dark-purple AA bridge on the
        # screen-left near eye.  It is one source row, bounded on both sides by
        # the already-fixed black lash, but was owned by the movable iris and
        # exposed as five white pixels at either horizontal gaze extreme.
        patch_left, patch_top, _right, _bottom = patch_box
        bridge = np.zeros(source_patch.shape[:2], dtype=bool)
        bridge_y = 323 - patch_top
        bridge_x0 = 393 - patch_left
        bridge_x1 = 408 - patch_left
        bridge[bridge_y, bridge_x0:bridge_x1] = True
        source_hsv = cv2.cvtColor(source_patch[..., :3], cv2.COLOR_RGB2HSV)
        bridge &= (
            (source_patch[..., 3] > 200)
            & (source_hsv[..., 1] >= 12)
            & (source_hsv[..., 2] < 145)
        )
        self.assertEqual(
            int(np.count_nonzero(bridge)),
            15,
            "body/right near upper-lash AA bridge source geometry drifted",
        )

        base_alpha = np.asarray(layers["eye-base"], dtype=np.uint8)[..., 3]
        iris_alpha = np.asarray(layers["irises"], dtype=np.uint8)[..., 3]
        line_rgba = np.asarray(layers["eye-line"], dtype=np.uint8)
        line_alpha = line_rgba[..., 3]
        self.assertEqual(
            int(np.count_nonzero(bridge & (base_alpha > 20))),
            0,
            "white eye-base still owns the circled near-eye lash bridge",
        )
        self.assertEqual(
            int(np.count_nonzero(bridge & (iris_alpha > 20))),
            0,
            "movable iris still owns the circled near-eye lash bridge",
        )
        self.assertEqual(
            int(np.count_nonzero(bridge & (line_alpha < 245))),
            0,
            "fixed eye-line does not fully restore the near-eye lash bridge",
        )
        self.assertTrue(
            np.array_equal(line_rgba[bridge], source_patch[bridge]),
            "near-eye fixed line no longer matches the source lash RGBA",
        )

        for move_x in (-5, 5):
            rendered = source.copy()
            rendered.alpha_composite(
                layers["eye-base"],
                (patch_left, patch_top),
            )
            rendered.alpha_composite(
                self._shift_rgba_patch(layers["irises"], move_x),
                (patch_left, patch_top),
            )
            rendered.alpha_composite(
                layers["eye-line"],
                (patch_left, patch_top),
            )
            actual = np.asarray(rendered.crop(patch_box), dtype=np.uint8)
            self.assertTrue(
                np.array_equal(actual[bridge], source_patch[bridge]),
                f"body/right terminal gaze {move_x:+d}: circled lash bridge changed",
            )

    def test_body_right_terminal_near_upper_lash_has_no_white_notch_at_right_gaze(self):
        """The dark pixels inside the user's circle must not turn sclera-white."""
        source_frames, _raw_masks = v14._neutral_sequence("body", "right")
        source = source_frames[-1].convert("RGBA")
        patch_box = v14.v10.scaled_roi(v14.v11.PATCH_ROIS["right"]["blink"])
        source_patch = np.asarray(source.crop(patch_box), dtype=np.uint8)

        atlas_root = ROOT / "assets/character-v14/body-atlases"
        layers = {}
        for state in ("eye-base", "irises", "eye-line"):
            atlas = Image.open(atlas_root / f"right-{state}-v1.png").convert(
                "RGBA"
            )
            layers[state] = self._atlas_frame(atlas, v14.FRAME_COUNT - 1)

        shifted_iris = self._shift_rgba_patch(layers["irises"], 5)
        rendered = source.crop(patch_box).convert("RGBA")
        rendered.alpha_composite(layers["eye-base"])
        rendered.alpha_composite(shifted_iris)
        rendered.alpha_composite(layers["eye-line"])
        actual = np.asarray(rendered, dtype=np.uint8)

        patch_left, patch_top, _right, _bottom = patch_box
        circled = np.zeros(source_patch.shape[:2], dtype=bool)
        circled[
            324 - patch_top : 331 - patch_top,
            387 - patch_left : 398 - patch_left,
        ] = True
        source_hsv = cv2.cvtColor(source_patch[..., :3], cv2.COLOR_RGB2HSV)
        source_lash = (
            circled
            & (source_patch[..., 3] > 200)
            & (source_hsv[..., 1] >= 12)
            & (source_hsv[..., 2] < 145)
        )
        self.assertEqual(
            int(np.count_nonzero(source_lash)),
            76,
            "circled near-eye upper-lash source geometry drifted",
        )

        actual_hsv = cv2.cvtColor(actual[..., :3], cv2.COLOR_RGB2HSV)
        white_notch = (
            source_lash
            & (actual_hsv[..., 1] <= 25)
            & (actual_hsv[..., 2] >= 205)
        )
        self.assertEqual(
            int(np.count_nonzero(white_notch)),
            0,
            "dark near-eye upper-lash pixels are still exposed as a white notch",
        )

    def test_body_terminal_gaze_exposes_white_sclera_without_a_skin_tinted_rim(self):
        atlas_root = ROOT / "assets/character-v14/body-atlases"
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

        for direction in ("left", "right"):
            source_frames, _raw_masks = v14._neutral_sequence(
                "body",
                direction,
            )
            patch_box = v14.v10.scaled_roi(
                v14.v11.PATCH_ROIS[direction]["blink"]
            )
            source_patch = source_frames[-1].crop(patch_box).convert("RGBA")

            layers = {}
            for state in ("eye-base", "irises", "eye-line"):
                atlas = Image.open(
                    atlas_root / f"{direction}-{state}-v1.png"
                ).convert("RGBA")
                layers[state] = self._atlas_frame(
                    atlas,
                    v14.FRAME_COUNT - 1,
                )

            base_rgba = np.asarray(layers["eye-base"], dtype=np.uint8)
            line_alpha = np.asarray(
                layers["eye-line"],
                dtype=np.uint8,
            )[..., 3]
            yy = np.indices(base_rgba.shape[:2])[0]

            for move_x in (-5, 5):
                shifted_iris = self._shift_rgba_patch(
                    layers["irises"],
                    move_x,
                )
                shifted_alpha = np.asarray(
                    shifted_iris,
                    dtype=np.uint8,
                )[..., 3]
                components = self._main_components(
                    shifted_alpha,
                    minimum_area=8,
                )
                label = (
                    f"body/{direction}/frame-{v14.FRAME_COUNT - 1:02d} "
                    f"gaze {move_x:+d}"
                )
                self.assertEqual(len(components), 2, label)

                rim = np.zeros(base_rgba.shape[:2], dtype=bool)
                for component in components:
                    left, top, width, height = component["bbox"]
                    near_iris = cv2.dilate(
                        np.where(
                            component["mask"],
                            255,
                            0,
                        ).astype(np.uint8),
                        kernel,
                    ) > 0
                    middle_sclera = (
                        (yy >= top + 0.20 * height)
                        & (yy <= top + 0.80 * height)
                    )
                    rim |= near_iris & ~component["mask"] & middle_sclera

                visible_sclera_rim = (
                    rim
                    & (shifted_alpha == 0)
                    & (base_rgba[..., 3] >= 245)
                    & (line_alpha < 20)
                )
                rim_count = int(np.count_nonzero(visible_sclera_rim))
                self.assertGreaterEqual(
                    rim_count,
                    40,
                    f"{label}: exposed sclera-rim mask became vacuous",
                )

                rendered = source_patch.copy()
                rendered.alpha_composite(layers["eye-base"])
                rendered.alpha_composite(shifted_iris)
                rendered.alpha_composite(layers["eye-line"])
                actual_rgba = np.asarray(rendered, dtype=np.uint8)
                actual_hsv = cv2.cvtColor(
                    actual_rgba[..., :3],
                    cv2.COLOR_RGB2HSV,
                )
                saturation_p90 = float(
                    np.percentile(
                        actual_hsv[..., 1][visible_sclera_rim],
                        90,
                    )
                )
                self.assertLessEqual(
                    saturation_p90,
                    18.0,
                    (
                        f"{label}: exposed sclera has a skin-colored rim; "
                        f"p90 saturation={saturation_p90:.1f}, "
                        f"pixels={rim_count}"
                    ),
                )

    def test_body_terminal_irises_touch_the_lower_lids_without_a_white_sanpaku_gap(self):
        atlas_root = ROOT / "assets/character-v14/body-atlases"
        for direction in ("left", "right"):
            source_frames, _raw_masks = v14._neutral_sequence("body", direction)
            patch_box = v14.v10.scaled_roi(
                v14.v11.PATCH_ROIS[direction]["blink"]
            )
            source_patch = source_frames[-1].crop(patch_box).convert("RGBA")
            layers = {}
            for state in ("eye-base", "irises", "eye-line"):
                atlas = Image.open(
                    atlas_root / f"{direction}-{state}-v1.png"
                ).convert("RGBA")
                layers[state] = self._atlas_frame(atlas, v14.FRAME_COUNT - 1)

            for move_x in (-5, 0, 5):
                shifted_iris = self._shift_rgba_patch(layers["irises"], move_x)
                shifted_rgba = np.asarray(shifted_iris, dtype=np.uint8)
                components = self._main_components(
                    shifted_rgba[..., 3],
                    minimum_area=8,
                )
                label = f"body/{direction}/terminal gaze {move_x:+d}"
                self.assertEqual(len(components), 2, label)

                rendered = source_patch.copy()
                rendered.alpha_composite(layers["eye-base"])
                rendered.alpha_composite(shifted_iris)
                rendered.alpha_composite(layers["eye-line"])
                actual = np.asarray(rendered, dtype=np.uint8)
                hsv = cv2.cvtColor(actual[..., :3], cv2.COLOR_RGB2HSV)
                bright_sclera = (
                    (actual[..., 3] > 200)
                    & (hsv[..., 1] <= 20)
                    & (hsv[..., 2] >= 205)
                )

                for eye_index, component in enumerate(components):
                    left, _top, width, _height = component["bbox"]
                    x0 = left + int(np.floor(width * 0.25))
                    x1 = left + int(np.ceil(width * 0.75))
                    gaps = []
                    for x in range(x0, x1):
                        ys = np.where(component["mask"][:, x])[0]
                        if len(ys) == 0:
                            continue
                        gap = 0
                        for y in range(
                            int(ys.max()) + 1,
                            min(actual.shape[0], int(ys.max()) + 15),
                        ):
                            if not bright_sclera[y, x]:
                                break
                            gap += 1
                        gaps.append(gap)
                    self.assertGreaterEqual(len(gaps), 4, f"{label} eye {eye_index}")
                    self.assertEqual(
                        float(np.median(gaps)),
                        0.0,
                        f"{label} eye {eye_index}: lower white gap={gaps}",
                    )
                    self.assertLessEqual(
                        float(np.percentile(gaps, 90)),
                        1.0,
                        f"{label} eye {eye_index}: lower white gap={gaps}",
                    )


if __name__ == "__main__":
    unittest.main()
