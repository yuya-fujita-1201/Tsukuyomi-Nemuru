import os
from pathlib import Path

from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright


BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:4173")
OUTPUT_ROOT = Path("output/screenshots/eye-matrix-v14")
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
MATRIX_PATH = Path("output/screenshots/eye-motion-matrix-v14.png")

POSES = (
    ("front", {"turn": 0, "headTurn": 0}, None),
    ("neck-left", {"turn": 0, "headTurn": -1}, "headTurnLeftLower"),
    ("neck-right", {"turn": 0, "headTurn": 1}, "headTurnRightLower"),
    ("body-left", {"turn": -1, "headTurn": 0}, "bodyTurnLeftLower"),
    ("body-right", {"turn": 1, "headTurn": 0}, "bodyTurnRightLower"),
)

GAZES = (
    ("center", 0, 0),
    ("near-right", 0.06, 0),
    ("left", -1, 0),
    ("right", 1, 0),
    ("up", 0, -1),
    ("down", 0, 1),
)


def settle(page, pose, frames=180):
    page.evaluate(
        """({nextPose, frameCount}) => {
            const engine = window.__PUPPET__;
            engine.setManualPose(nextPose);
            for (let frame = 0; frame < frameCount; frame += 1) {
                engine.tick(1 / 60);
            }
            engine.app.render();
        }""",
        {"nextPose": pose, "frameCount": frames},
    )


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
    canvas = page.locator("#puppet-stage canvas")
    panels = {}

    for pose_name, pose, layer_prefix in POSES:
        for gaze_name, gaze_x, gaze_y in GAZES:
            state = {
                **pose,
                "gazeX": gaze_x,
                "gazeY": gaze_y,
                "mouthOpen": 0,
                "blink": 0,
            }
            settle(page, state)
            if layer_prefix is not None:
                layer_state = page.evaluate(
                    """(prefix) => {
                        const engine = window.__PUPPET__;
                        return {
                            gazeAlpha: engine.lastSideGazeLayerAlpha,
                            iris: engine.layers[`${prefix}Irises`].alpha,
                            line: engine.layers[`${prefix}EyeLine`].alpha,
                            lineX: engine.layers[`${prefix}EyeLine`].position.x,
                            lineY: engine.layers[`${prefix}EyeLine`].position.y,
                        };
                    }""",
                    layer_prefix,
                )
                assert layer_state["gazeAlpha"] > 0.99
                assert layer_state["iris"] > 0.99
                assert layer_state["line"] > 0.99
                assert layer_state["lineX"] == 0
                assert layer_state["lineY"] == 0

            screenshot_path = OUTPUT_ROOT / f"{pose_name}-{gaze_name}.png"
            canvas.screenshot(path=str(screenshot_path))
            full = Image.open(screenshot_path).convert("RGB")
            panels[(pose_name, gaze_name)] = full.crop((70, 170, 365, 390))

    browser.close()
    assert not console_errors, console_errors


panel_width, panel_height = next(iter(panels.values())).size
header_height = 26
row_label_width = 86
matrix = Image.new(
    "RGB",
    (
        row_label_width + panel_width * len(GAZES),
        header_height + panel_height * len(POSES),
    ),
    (15, 19, 40),
)
draw = ImageDraw.Draw(matrix)
for column, (gaze_name, _x, _y) in enumerate(GAZES):
    draw.text(
        (row_label_width + column * panel_width + 8, 7),
        gaze_name,
        fill="white",
    )
for row, (pose_name, _pose, _prefix) in enumerate(POSES):
    draw.text((8, header_height + row * panel_height + 8), pose_name, fill="white")
    for column, (gaze_name, _x, _y) in enumerate(GAZES):
        matrix.paste(
            panels[(pose_name, gaze_name)],
            (
                row_label_width + column * panel_width,
                header_height + row * panel_height,
            ),
        )
matrix.save(MATRIX_PATH)
