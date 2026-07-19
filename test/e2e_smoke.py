import os
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageChops, ImageStat
from playwright.sync_api import sync_playwright


BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:4173")
SCREENSHOT_DIR = Path("output/screenshots")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

WIDE_PATH = SCREENSHOT_DIR / "parameter-review-v14-wide.png"
FINAL_PATH = SCREENSHOT_DIR / "parameter-review-v14-final.png"
FRONT_GAZE_CENTER_PATH = SCREENSHOT_DIR / "faceless-v14-front-gaze-center.png"
FRONT_GAZE_MOVED_PATH = SCREENSHOT_DIR / "faceless-v14-front-gaze-right-up.png"
FRONT_BLINK_HALF_PATH = SCREENSHOT_DIR / "faceless-v14-front-blink-half.png"
FRONT_BLINK_CLOSED_PATH = SCREENSHOT_DIR / "faceless-v14-front-blink-closed.png"
FRONT_I_PATH = SCREENSHOT_DIR / "faceless-v14-front-mouth-i-reference.png"
NECK_NEUTRAL_PATH = SCREENSHOT_DIR / "faceless-v14-neck-right-neutral.png"
NECK_EYE_BASE_PATH = SCREENSHOT_DIR / "faceless-v14-neck-right-eye-base-clean.png"
NECK_GAZE_MOUTH_PATH = SCREENSHOT_DIR / "faceless-v14-neck-right-gaze-mouth.png"
BODY_LEFT_NEUTRAL_PATH = SCREENSHOT_DIR / "faceless-v14-body-left-neutral.png"
BODY_LEFT_EYE_BASE_PATH = SCREENSHOT_DIR / "faceless-v14-body-left-eye-base-clean.png"
BODY_LEFT_STATIC_A_PATH = SCREENSHOT_DIR / "faceless-v14-body-left-static-a.png"
BODY_LEFT_STATIC_B_PATH = SCREENSHOT_DIR / "faceless-v14-body-left-static-b.png"
BODY_LEFT_GAZE_MOUTH_PATH = SCREENSHOT_DIR / "faceless-v14-body-left-gaze-mouth.png"
BODY_RIGHT_PATH = SCREENSHOT_DIR / "faceless-v14-body-right-endpoint.png"


def mean_difference(first_path, second_path):
    difference = ImageChops.difference(
        Image.open(first_path).convert("RGB"),
        Image.open(second_path).convert("RGB"),
    )
    return max(ImageStat.Stat(difference).mean)


def images_are_identical(first_path, second_path):
    difference = ImageChops.difference(
        Image.open(first_path).convert("RGBA"),
        Image.open(second_path).convert("RGBA"),
    )
    return difference.getbbox() is None


def screenshot_page_with_canvas(page, canvas, output_path):
    """Composite a locator capture over Chromium's blank WebGL page layer."""
    box = canvas.bounding_box()
    assert box is not None
    page_image = Image.open(BytesIO(page.screenshot())).convert("RGBA")
    canvas_image = Image.open(BytesIO(canvas.screenshot())).convert("RGBA")
    pixels = canvas_image.convert("RGB").get_flattened_data()
    bright_ratio = sum(max(pixel) >= 100 for pixel in pixels) / (
        canvas_image.width * canvas_image.height
    )
    assert bright_ratio > 0.1, f"WebGL character was blank: {bright_ratio:.4f}"
    viewport = page.viewport_size
    scale_x = page_image.width / viewport["width"]
    scale_y = page_image.height / viewport["height"]
    expected_size = (
        round(box["width"] * scale_x),
        round(box["height"] * scale_y),
    )
    if canvas_image.size != expected_size:
        canvas_image = canvas_image.resize(
            expected_size,
            Image.Resampling.LANCZOS,
        )
    page_image.alpha_composite(
        canvas_image,
        (round(box["x"] * scale_x), round(box["y"] * scale_y)),
    )
    page_image.convert("RGB").save(output_path)


def settle_responsive_canvas(page, frames=180):
    """Wait until CSS/ResizeObserver agree, then render after the last resize."""
    previous = None
    stable_samples = 0
    for _attempt in range(20):
        state = page.evaluate(
            """() => {
                const canvas = document.querySelector('#puppet-stage canvas');
                const engine = window.__PUPPET__;
                return [
                    canvas.clientWidth,
                    canvas.clientHeight,
                    engine.app.screen.width,
                    engine.app.screen.height,
                ];
            }"""
        )
        renderer_matches_css = state[:2] == state[2:]
        if state == previous and renderer_matches_css:
            stable_samples += 1
        else:
            stable_samples = 0
        if stable_samples >= 2:
            settle_engine(page, frames)
            page.wait_for_timeout(100)
            final_state = page.evaluate(
                """() => {
                    const canvas = document.querySelector('#puppet-stage canvas');
                    const engine = window.__PUPPET__;
                    return [
                        canvas.clientWidth,
                        canvas.clientHeight,
                        engine.app.screen.width,
                        engine.app.screen.height,
                    ];
                }"""
            )
            if final_state == state:
                settle_engine(page, 1)
                return
            stable_samples = 0
        previous = state
        page.wait_for_timeout(100)
    raise AssertionError("responsive canvas did not settle")


def purple_ratio_in_boxes(path, boxes):
    image = Image.open(path).convert("HSV")
    ratios = []
    for box in boxes:
        left, top, right, bottom = box
        assert 0 <= left < right <= image.width, (path, box, image.size)
        assert 0 <= top < bottom <= image.height, (path, box, image.size)
        pixels = list(image.crop(box).get_flattened_data())
        purple = sum(
            1
            for hue, saturation, value in pixels
            if 149 <= hue <= 248 and saturation >= 48 and value >= 35
        )
        ratios.append(purple / len(pixels))
    return ratios


def settle_engine(page, frames=180):
    page.evaluate(
        """(frameCount) => {
            const engine = window.__PUPPET__;
            for (let frame = 0; frame < frameCount; frame += 1) {
                engine.tick(1 / 60);
            }
            engine.app.render();
        }""",
        frames,
    )


def set_pose(page, pose, frames=180):
    page.evaluate(
        """(nextPose) => {
            const engine = window.__PUPPET__;
            engine.setManualPose(nextPose);
        }""",
        pose,
    )
    settle_engine(page, frames)


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1100})
    console_errors = []
    page.on(
        "console",
        lambda message: console_errors.append(message.text)
        if message.type == "error"
        else None,
    )

    page.goto(BASE_URL)
    page.wait_for_load_state("networkidle")
    page.wait_for_selector('body[data-ready="true"]', timeout=30000)
    page.wait_for_function(
        "() => Number(getComputedStyle(document.querySelector('#stage-loading')).opacity) < 0.01",
        timeout=3000,
    )
    page.evaluate(
        """() => {
            const engine = window.__PUPPET__;
            engine.app.ticker.stop();
            engine.nextBlinkAt = Number.POSITIVE_INFINITY;
            engine.blinkStartedAt = null;
        }"""
    )

    assert page.locator("h1").inner_text() == "眠りの演技室"
    assert page.locator("body").get_attribute("data-engine") == "layered"
    assert page.locator("#puppet-stage canvas").is_visible()
    assert page.locator("#play-toggle").get_attribute("data-state") == "paused"
    assert "39素材" in page.locator("#system-label").inner_text()
    assert page.locator("#turn-variant-select").input_value() == "parameter"
    assert page.evaluate("() => window.__PUPPET__.turnVariant") == "parameter"

    engine_state = page.evaluate(
        """() => ({
            layerKeys: Object.keys(window.__PUPPET__.layers).sort(),
            textureKeys: Object.keys(window.__PUPPET__.textures).sort(),
            resolution: window.__PUPPET__.app.renderer.resolution,
            frontAlpha: window.__PUPPET__.frontGroup.alpha
        })"""
    )
    assert len(engine_state["textureKeys"]) == 39
    assert engine_state["resolution"] <= 1.5
    assert engine_state["frontAlpha"] > 0.9
    assert not any(key.startswith("pose") for key in engine_state["layerKeys"])
    for family in ("headTurn", "bodyTurn"):
        for direction in ("Left", "Right"):
            for slot in ("Lower", "Upper"):
                for state in (
                    "Neutral",
                    "EyeBase",
                    "Irises",
                    "EyeLine",
                    "Blink",
                    "MouthSmall",
                ):
                    assert f"{family}{direction}{slot}{state}" in engine_state["layerKeys"]

    canvas = page.locator("#puppet-stage canvas")

    # Front gaze remains independent from the eye drawing.
    set_pose(
        page,
        {"turn": 0, "headTurn": 0, "gazeX": 0, "gazeY": 0, "mouthOpen": 0},
    )
    canvas.screenshot(path=str(FRONT_GAZE_CENTER_PATH))
    set_pose(page, {"gazeX": 0.8, "gazeY": -0.4})
    front_gaze = page.evaluate(
        """() => {
            const engine = window.__PUPPET__;
            return {
                irisX: engine.irisGroup.position.x - engine.anchors.iris.x,
                irisY: engine.irisGroup.position.y - engine.anchors.iris.y,
                eyeX: engine.layers.eyeOpen.position.x,
                eyeY: engine.layers.eyeOpen.position.y
            };
        }"""
    )
    assert front_gaze["irisX"] > 8
    assert front_gaze["irisY"] < -2
    assert front_gaze["eyeX"] == 0
    assert front_gaze["eyeY"] == 0
    canvas.screenshot(path=str(FRONT_GAZE_MOVED_PATH))
    assert mean_difference(FRONT_GAZE_CENTER_PATH, FRONT_GAZE_MOVED_PATH) > 0.01

    # Front blink has a real half key. The iris keeps the same transform and
    # coordinates until the closed key rather than sliding during the blink.
    set_pose(page, {"gazeX": 0, "gazeY": 0, "blink": 0})
    open_blink_state = page.evaluate(
        """() => ({
            irisX: window.__PUPPET__.irisGroup.position.x,
            irisY: window.__PUPPET__.irisGroup.position.y,
            weights: window.__PUPPET__.lastFrontBlinkWeights
        })"""
    )
    set_pose(page, {"blink": 0.5})
    half_blink_state = page.evaluate(
        """() => ({
            eyeOpen: window.__PUPPET__.layers.eyeOpen.alpha,
            iris: window.__PUPPET__.irisGroup.alpha,
            half: window.__PUPPET__.layers.eyesHalf.alpha,
            closed: window.__PUPPET__.layers.eyesClosed.alpha,
            irisX: window.__PUPPET__.irisGroup.position.x,
            irisY: window.__PUPPET__.irisGroup.position.y,
            weights: window.__PUPPET__.lastFrontBlinkWeights
        })"""
    )
    assert half_blink_state["weights"]["open"] < 1e-8
    assert half_blink_state["weights"]["half"] > 1 - 1e-8
    assert half_blink_state["weights"]["closed"] < 1e-8
    assert half_blink_state["weights"]["iris"] > 1 - 1e-8
    assert half_blink_state["eyeOpen"] > 1 - 1e-8
    assert half_blink_state["iris"] > 1 - 1e-8
    assert half_blink_state["half"] > 1 - 1e-8
    assert half_blink_state["closed"] < 1e-8
    assert abs(half_blink_state["irisX"] - open_blink_state["irisX"]) < 1e-8
    assert abs(half_blink_state["irisY"] - open_blink_state["irisY"]) < 1e-8
    canvas.screenshot(path=str(FRONT_BLINK_HALF_PATH))

    set_pose(page, {"blink": 1})
    closed_blink_state = page.evaluate(
        """() => ({
            eyeOpen: window.__PUPPET__.layers.eyeOpen.alpha,
            iris: window.__PUPPET__.irisGroup.alpha,
            half: window.__PUPPET__.layers.eyesHalf.alpha,
            closed: window.__PUPPET__.layers.eyesClosed.alpha
        })"""
    )
    assert closed_blink_state["eyeOpen"] < 1e-8
    assert closed_blink_state["iris"] < 1e-8
    assert closed_blink_state["half"] < 1e-8
    assert closed_blink_state["closed"] > 1 - 1e-8
    canvas.screenshot(path=str(FRONT_BLINK_CLOSED_PATH))
    assert mean_difference(FRONT_GAZE_CENTER_PATH, FRONT_BLINK_HALF_PATH) > 0.01
    assert mean_difference(FRONT_BLINK_HALF_PATH, FRONT_BLINK_CLOSED_PATH) > 0.01
    set_pose(page, {"blink": 0})

    # Tiny input noise must keep the exact approved front layers rather than
    # swapping the entire character to side-atlas frame zero.
    set_pose(
        page,
        {
            "turn": 0,
            "headTurn": 0.01,
            "gazeX": 0,
            "gazeY": 0,
            "mouthOpen": 0,
            "blink": 0,
        },
    )
    near_front_state = page.evaluate(
        """() => ({
            front: window.__PUPPET__.frontGroup.alpha,
            headActive: window.__PUPPET__.headTurnSequenceActive,
            bodyActive: window.__PUPPET__.bodyTurnSequenceActive,
            blendActive: window.__PUPPET__.lastHeadTurnFrameBlend.active
        })"""
    )
    assert near_front_state == {
        "front": 1,
        "headActive": False,
        "bodyActive": False,
        "blendActive": False,
    }
    set_pose(page, {"headTurn": 0})

    # The user-reference I mouth is the only active front mouth at medium open.
    page.locator('[data-mouth-vowel="i"]').click()
    settle_engine(page)
    i_mouth_state = page.evaluate(
        """() => ({
            vowel: window.__PUPPET__.mouthVowel,
            weights: window.__PUPPET__.lastMouthWeights,
            closed: window.__PUPPET__.layers.mouthClosed.alpha,
            micro: window.__PUPPET__.layers.mouthMicro.alpha,
            small: window.__PUPPET__.layers.mouthSmall.alpha,
            wide: window.__PUPPET__.layers.mouthWide.alpha,
            i: window.__PUPPET__.layers.mouthI.alpha
        })"""
    )
    assert i_mouth_state["vowel"] == "i"
    assert i_mouth_state["weights"]["i"] == 1
    assert i_mouth_state["i"] == 1
    for key in ("closed", "micro", "small", "wide"):
        assert i_mouth_state[key] == 0
    page.wait_for_function(
        "() => new URLSearchParams(window.location.search).get('vowel') === 'i'",
        timeout=1000,
    )
    canvas.screenshot(path=str(FRONT_I_PATH))
    page.locator('[data-mouth-vowel="auto"]').click()

    # Neck input reaches 90% in twelve 60-fps ticks and never enters a cut state.
    neck_response = page.evaluate(
        """() => {
            const engine = window.__PUPPET__;
            engine.currentTurn = 0;
            engine.currentHeadTurn = 0;
            engine.setManualPose({
                turn: 0,
                headTurn: 1,
                gazeX: 0,
                gazeY: 0,
                mouthOpen: 0,
                blink: 0
            });
            const samples = [];
            for (let frame = 0; frame < 12; frame += 1) {
                engine.tick(1 / 60);
                samples.push(engine.currentHeadTurn);
            }
            engine.app.render();
            return {
                samples,
                current: engine.currentHeadTurn,
                phase: engine.turnTransitionState.phase,
                displayPose: engine.turnTransitionState.displayPose,
                active: engine.headTurnSequenceActive,
                bodyActive: engine.bodyTurnSequenceActive
            };
        }"""
    )
    assert neck_response["current"] > 0.9
    assert all(
        later > earlier
        for earlier, later in zip(neck_response["samples"], neck_response["samples"][1:])
    )
    assert neck_response["phase"] == "idle"
    assert neck_response["displayPose"] == "front"
    assert neck_response["active"]
    assert not neck_response["bodyActive"]

    # At a side-facing neck angle, gaze and the quiet mouth patch remain live.
    set_pose(
        page,
        {"turn": 0, "headTurn": 0.72, "gazeX": 0, "gazeY": 0, "mouthOpen": 0},
    )
    canvas.screenshot(path=str(NECK_NEUTRAL_PATH))
    neck_center_eye_state = page.evaluate(
        """() => ({
            layerAlpha: window.__PUPPET__.lastSideGazeLayerAlpha,
            base: window.__PUPPET__.layers.headTurnRightLowerEyeBase.alpha,
            iris: window.__PUPPET__.layers.headTurnRightLowerIrises.alpha,
            line: window.__PUPPET__.layers.headTurnRightLowerEyeLine.alpha
        })"""
    )
    assert neck_center_eye_state == {
        "layerAlpha": 1,
        "base": 1,
        "iris": 1,
        "line": 1,
    }
    page.evaluate(
        """() => {
            const slots = window.__PUPPET__.headTurnSlots.right;
            slots.lower.layers.eyeBase.alpha = 1;
            slots.upper.layers.eyeBase.alpha = 1;
            slots.lower.layers.irises.alpha = 0;
            slots.upper.layers.irises.alpha = 0;
            window.__PUPPET__.app.render();
        }"""
    )
    canvas.screenshot(path=str(NECK_EYE_BASE_PATH))
    neck_underpaint_ratios = purple_ratio_in_boxes(
        NECK_EYE_BASE_PATH,
        # Start below the fixed upper-eyeliner overlay; this inspection is for
        # baked pupil color in the sclera interior, not preserved line art.
        [(196, 278, 218, 292), (295, 278, 316, 294)],
    )
    assert max(neck_underpaint_ratios) < 0.18
    settle_engine(page, 1)
    set_pose(page, {"gazeX": 0.78, "gazeY": -0.32, "mouthOpen": 0.35})
    neck_side_state = page.evaluate(
        """() => {
            const engine = window.__PUPPET__;
            return {
                active: engine.headTurnSequenceActive,
                direction: engine.lastHeadTurnFrameBlend.direction,
                frame: engine.lastHeadTurnFrameBlend.lowerIndex +
                    engine.lastHeadTurnFrameBlend.upperAlpha,
                irisX: engine.layers.headTurnRightLowerIrises.position.x,
                irisY: engine.layers.headTurnRightLowerIrises.position.y,
                irisAlpha: engine.layers.headTurnRightLowerIrises.alpha,
                lineAlpha: engine.layers.headTurnRightLowerEyeLine.alpha,
                mouthAlpha: engine.layers.headTurnRightLowerMouthSmall.alpha,
                front: engine.frontGroup.alpha
            };
        }"""
    )
    assert neck_side_state["active"]
    assert neck_side_state["direction"] == 1
    assert neck_side_state["frame"] == 11
    assert neck_side_state["irisX"] > 3.5
    assert neck_side_state["irisY"] < -0.5
    assert neck_side_state["irisAlpha"] > 0.9
    assert neck_side_state["lineAlpha"] > 0.9
    assert neck_side_state["mouthAlpha"] > 0.8
    assert neck_side_state["front"] == 0
    canvas.screenshot(path=str(NECK_GAZE_MOUTH_PATH))
    assert mean_difference(NECK_NEUTRAL_PATH, NECK_GAZE_MOUTH_PATH) > 0.01

    # Blink hides the movable side iris instead of leaving a doubled eye.
    set_pose(page, {"blink": 1}, frames=240)
    neck_blink = page.evaluate(
        """() => ({
            iris: window.__PUPPET__.layers.headTurnRightLowerIrises.alpha,
            line: window.__PUPPET__.layers.headTurnRightLowerEyeLine.alpha,
            blink: window.__PUPPET__.layers.headTurnRightLowerBlink.alpha
        })"""
    )
    assert neck_blink["iris"] < 0.01
    assert neck_blink["line"] < 0.01
    assert neck_blink["blink"] > 0.99

    # Body input also traverses a monotonic 16-key sequence without raster cuts.
    body_response = page.evaluate(
        """() => {
            const engine = window.__PUPPET__;
            engine.currentTurn = 0;
            engine.currentHeadTurn = 0;
            engine.setManualPose({
                turn: 1,
                headTurn: 0,
                gazeX: 0,
                gazeY: 0,
                mouthOpen: 0,
                blink: 0
            });
            const turns = [];
            const frames = [];
            const phases = [];
            for (let frame = 0; frame < 24; frame += 1) {
                engine.tick(1 / 60);
                turns.push(engine.currentTurn);
                frames.push(
                    engine.lastBodyTurnFrameBlend.lowerIndex +
                    engine.lastBodyTurnFrameBlend.upperAlpha
                );
                phases.push(engine.turnTransitionState.phase);
            }
            engine.app.render();
            return {
                turns,
                frames,
                phases,
                current: engine.currentTurn,
                displayPose: engine.turnTransitionState.displayPose,
                active: engine.bodyTurnSequenceActive,
                headActive: engine.headTurnSequenceActive
            };
        }"""
    )
    assert body_response["current"] > 0.97
    assert all(
        later > earlier
        for earlier, later in zip(body_response["turns"], body_response["turns"][1:])
    )
    assert all(
        later > earlier
        for earlier, later in zip(body_response["frames"], body_response["frames"][1:])
    )
    assert set(body_response["phases"]) == {"idle"}
    assert body_response["displayPose"] == "front"
    assert body_response["active"]
    assert not body_response["headActive"]

    # A left 3/4 body pose keeps gaze and mouth control at an intermediate frame.
    set_pose(
        page,
        {
            "turn": -0.62,
            "headTurn": 0,
            "gazeX": 0,
            "gazeY": 0,
            "mouthOpen": 0,
            "blink": 0,
        },
    )
    canvas.screenshot(path=str(BODY_LEFT_NEUTRAL_PATH))
    body_center_eye_state = page.evaluate(
        """() => ({
            layerAlpha: window.__PUPPET__.lastSideGazeLayerAlpha,
            base: window.__PUPPET__.layers.bodyTurnLeftLowerEyeBase.alpha,
            iris: window.__PUPPET__.layers.bodyTurnLeftLowerIrises.alpha,
            line: window.__PUPPET__.layers.bodyTurnLeftLowerEyeLine.alpha
        })"""
    )
    assert body_center_eye_state == {
        "layerAlpha": 1,
        "base": 1,
        "iris": 1,
        "line": 1,
    }
    page.evaluate(
        """() => {
            const slots = window.__PUPPET__.bodyTurnSlots.left;
            slots.lower.layers.eyeBase.alpha = 1;
            slots.upper.layers.eyeBase.alpha = 1;
            slots.lower.layers.irises.alpha = 0;
            slots.upper.layers.irises.alpha = 0;
            window.__PUPPET__.app.render();
        }"""
    )
    canvas.screenshot(path=str(BODY_LEFT_EYE_BASE_PATH))
    body_underpaint_ratios = purple_ratio_in_boxes(
        BODY_LEFT_EYE_BASE_PATH,
        # Sample only the cleaned pupil cores. The top/outer purple eyeliner is
        # intentional character makeup and must remain outside these boxes.
        [(112, 269, 121, 282), (184, 268, 193, 279)],
    )
    assert max(body_underpaint_ratios) < 0.18
    settle_engine(page, 1)

    # A stopped 3/4 pose must be a single sharp frame with an identity motion
    # transform. Advancing wall time must produce the exact same canvas pixels.
    page.evaluate(
        """() => {
            const engine = window.__PUPPET__;
            engine.nextBlinkAt = Number.POSITIVE_INFINITY;
            engine.blinkStartedAt = null;
            engine.currentPose = engine.targetPose;
            engine.tick(1 / 60);
            engine.app.render();
        }"""
    )
    static_state = page.evaluate(
        """() => {
            const engine = window.__PUPPET__;
            const group = engine.bodyTurnGroups.left;
            const anchor = engine.anchors.bodyTurnLeftGroup;
            return {
                settled: engine.bodyTurnSettleState.settled,
                locked: engine.sideMotionLocked,
                lower: engine.lastBodyTurnFrameBlend.lowerIndex,
                upper: engine.lastBodyTurnFrameBlend.upperIndex,
                upperAlpha: engine.lastBodyTurnFrameBlend.upperAlpha,
                x: group.position.x - anchor.x,
                y: group.position.y - anchor.y,
                rotation: group.rotation,
                scaleX: group.scale.x,
                scaleY: group.scale.y
            };
        }"""
    )
    assert static_state == {
        "settled": True,
        "locked": True,
        "lower": 9,
        "upper": 9,
        "upperAlpha": 0,
        "x": 0,
        "y": 0,
        "rotation": 0,
        "scaleX": 1,
        "scaleY": 1,
    }
    canvas.screenshot(path=str(BODY_LEFT_STATIC_A_PATH))
    page.wait_for_timeout(160)
    page.evaluate("() => { window.__PUPPET__.tick(1 / 60); window.__PUPPET__.app.render(); }")
    canvas.screenshot(path=str(BODY_LEFT_STATIC_B_PATH))
    assert images_are_identical(BODY_LEFT_STATIC_A_PATH, BODY_LEFT_STATIC_B_PATH)

    set_pose(page, {"gazeX": 0.75, "gazeY": -0.25, "mouthOpen": 0.35})
    body_side_state = page.evaluate(
        """() => {
            const engine = window.__PUPPET__;
            return {
                active: engine.bodyTurnSequenceActive,
                headActive: engine.headTurnSequenceActive,
                direction: engine.lastBodyTurnFrameBlend.direction,
                frame: engine.lastBodyTurnFrameBlend.lowerIndex +
                    engine.lastBodyTurnFrameBlend.upperAlpha,
                irisX: engine.layers.bodyTurnLeftLowerIrises.position.x,
                irisY: engine.layers.bodyTurnLeftLowerIrises.position.y,
                mouthAlpha: engine.layers.bodyTurnLeftLowerMouthSmall.alpha,
                lineAlpha: engine.layers.bodyTurnLeftLowerEyeLine.alpha,
                lowerAlpha: engine.bodyTurnSlots.left.lower.group.alpha,
                upperAlpha: engine.bodyTurnSlots.left.upper.group.alpha,
                transitionPhase: engine.turnTransitionState.phase,
                front: engine.frontGroup.alpha
            };
        }"""
    )
    assert body_side_state["active"]
    assert not body_side_state["headActive"]
    assert body_side_state["direction"] == -1
    assert body_side_state["frame"] == 9
    assert body_side_state["irisX"] > 3.5
    assert body_side_state["irisY"] <= -0.49
    assert body_side_state["mouthAlpha"] > 0.8
    assert body_side_state["lineAlpha"] > 0.9
    assert body_side_state["lowerAlpha"] == 1
    assert body_side_state["upperAlpha"] == 0
    assert body_side_state["transitionPhase"] == "idle"
    assert body_side_state["front"] == 0
    canvas.screenshot(path=str(BODY_LEFT_GAZE_MOUTH_PATH))
    assert mean_difference(BODY_LEFT_NEUTRAL_PATH, BODY_LEFT_GAZE_MOUTH_PATH) > 0.01

    # The first new turn input unlocks static snapping and resumes interpolation.
    page.evaluate(
        """() => {
            const engine = window.__PUPPET__;
            engine.setManualPose({ turn: -0.4 });
            engine.tick(1 / 60);
            engine.app.render();
        }"""
    )
    unlocked = page.evaluate(
        """() => ({
            settled: window.__PUPPET__.bodyTurnSettleState.settled,
            locked: window.__PUPPET__.sideMotionLocked,
            lower: window.__PUPPET__.lastBodyTurnFrameBlend.lowerIndex,
            upper: window.__PUPPET__.lastBodyTurnFrameBlend.upperIndex
        })"""
    )
    assert unlocked["settled"] is False
    assert unlocked["locked"] is False
    assert unlocked["upper"] >= unlocked["lower"]

    # Both body endpoints remain callable; the reviewed 3/4 right pose is preserved.
    set_pose(
        page,
        {"turn": 1, "headTurn": 0, "gazeX": 0, "gazeY": 0, "mouthOpen": 0},
    )
    endpoint = page.evaluate(
        """() => ({
            frame: window.__PUPPET__.lastBodyTurnFrameBlend.lowerIndex +
                window.__PUPPET__.lastBodyTurnFrameBlend.upperAlpha,
            right: window.__PUPPET__.bodyTurnGroups.right.alpha,
            visible: window.__PUPPET__.bodyTurnGroups.right.visible
        })"""
    )
    assert abs(endpoint["frame"] - 15) < 0.001
    assert endpoint["right"] == 1
    assert endpoint["visible"]
    canvas.screenshot(path=str(BODY_RIGHT_PATH))

    # Slider changes update the shareable URL only after the debounce window.
    page.locator("#reset-parameters").click()
    page.locator('input[data-pose="headTurn"]').fill("0.56")
    page.locator('input[data-pose="gazeX"]').fill("0.46")
    page.locator('input[data-pose="gazeY"]').fill("-0.18")
    page.locator('input[data-pose="mouthOpen"]').fill("0.22")
    expected_query = {
        "variant": "parameter",
        "headTurn": "0.56",
        "gazeX": "0.46",
        "gazeY": "-0.18",
        "mouthOpen": "0.22",
    }
    page.wait_for_function(
        """(expected) => {
            const params = new URLSearchParams(window.location.search);
            return Object.entries(expected).every(
                ([key, value]) => params.get(key) === value,
            );
        }""",
        arg=expected_query,
        timeout=1000,
    )
    query = page.evaluate(
        "() => Object.fromEntries(new URLSearchParams(window.location.search))"
    )
    for key, value in expected_query.items():
        assert query[key] == value

    # URL state restores on a fresh page.
    restored_page = browser.new_page(viewport={"width": 1000, "height": 900})
    restored_page.goto(
        f"{BASE_URL}/?variant=parameter&vowel=i&headTurn=-0.62&turn=0.25&"
        "gazeX=0.44&gazeY=0.20&mouthOpen=0.35"
    )
    restored_page.wait_for_selector('body[data-ready="true"]', timeout=30000)
    restored_state = restored_page.evaluate(
        """() => ({
            variant: window.__PUPPET__.turnVariant,
            vowel: window.__PUPPET__.mouthVowel,
            headTurn: window.__PUPPET__.targetPose.headTurn,
            turn: window.__PUPPET__.targetPose.turn,
            gazeX: window.__PUPPET__.targetPose.gazeX,
            gazeY: window.__PUPPET__.targetPose.gazeY,
            mouthOpen: window.__PUPPET__.targetPose.mouthOpen
        })"""
    )
    assert restored_state == {
        "variant": "parameter",
        "vowel": "i",
        "headTurn": -0.62,
        "turn": 0.25,
        "gazeX": 0.44,
        "gazeY": 0.2,
        "mouthOpen": 0.35,
    }
    restored_page.close()

    # Keep the whole review UI inside one viewport. Chromium can omit a WebGL
    # canvas while stitching a full-page screenshot after scroll/resize.
    page.set_viewport_size({"width": 1440, "height": 1800})
    page.locator('button[data-format="wide"]').click()
    assert page.locator("#stage-shell").get_attribute("data-format") == "wide"
    settle_responsive_canvas(page, 180)
    screenshot_page_with_canvas(page, canvas, WIDE_PATH)
    page.locator('button[data-format="short"]').click()
    assert page.locator("#stage-shell").get_attribute("data-format") == "short"
    settle_responsive_canvas(page, 2)
    screenshot_page_with_canvas(page, canvas, FINAL_PATH)

    assert console_errors == []
    browser.close()
