import json
import math
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from PIL import Image, ImageChops, ImageStat
from playwright.sync_api import sync_playwright


BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:4173")
CAPTURE_FPS = int(os.environ.get("CAPTURE_FPS", "30"))
FRAME_WIDTH = 720
FRAME_HEIGHT = 1280
QUIET_MOUTH_MAX = 0.40
OUTPUT_DIR = Path("output/video")
MP4_PATH = OUTPUT_DIR / "tsukuyomi-natural-motion-review-v1.mp4"

if not 20 <= CAPTURE_FPS <= 30:
    raise ValueError("CAPTURE_FPS must be between 20 and 30")


ISOLATE_STAGE_CSS = """
html, body {
  width: 720px !important;
  height: 1280px !important;
  overflow: hidden !important;
  background: #080b14 !important;
}
.star-field,
.moon-orbit,
.topbar,
.section-heading,
.transport,
.control-deck,
.footer-note {
  display: none !important;
}
.app-shell,
.workspace,
.preview-column,
.stage-shell {
  width: 720px !important;
  height: 1280px !important;
  min-height: 1280px !important;
  margin: 0 !important;
  padding: 0 !important;
  border: 0 !important;
  border-radius: 0 !important;
}
.workspace {
  display: block !important;
}
.puppet-stage,
.stage-shell[data-format="short"] .puppet-stage {
  width: 720px !important;
  height: 1280px !important;
  border-radius: 0 !important;
  box-shadow: none !important;
}
"""


@dataclass(frozen=True)
class FramePlan:
    variant: str
    note: str
    turn: float
    blink: float = 0.0
    mouth_open: float = 0.0


def smoothstep(value):
    progress = min(1.0, max(0.0, float(value)))
    return progress * progress * (3.0 - 2.0 * progress)


def blink_pulse(progress, center=0.46, width=0.28):
    distance = abs(progress - center)
    half_width = width / 2.0
    if distance >= half_width:
        return 0.0
    return smoothstep(1.0 - distance / half_width)


def quiet_mouth(progress):
    primary = abs(math.sin(progress * math.tau * 2.15))
    secondary = abs(math.sin(progress * math.tau * 1.25 + 0.6))
    return min(QUIET_MOUTH_MAX, 0.10 + primary * 0.22 + secondary * 0.08)


def append_segment(
    frames,
    duration,
    variant,
    note,
    start_turn,
    end_turn=None,
    *,
    mouth=False,
    blink_center=None,
):
    frame_count = max(1, round(duration * CAPTURE_FPS))
    resolved_end = start_turn if end_turn is None else end_turn
    for index in range(frame_count):
        progress = index / max(1, frame_count - 1)
        eased = smoothstep(progress)
        turn = start_turn + (resolved_end - start_turn) * eased
        blink = (
            blink_pulse(progress, center=blink_center)
            if blink_center is not None
            else 0.0
        )
        frames.append(
            FramePlan(
                variant=variant,
                note=note,
                turn=turn,
                blink=blink,
                mouth_open=quiet_mouth(progress) if mouth else 0.0,
            )
        )


def build_timeline():
    frames = []

    # NATURAL: the head leads while the shoulders and upper body follow mildly.
    append_segment(frames, 0.72, "natural", "正面・修正版の小さなリップ", 0)
    append_segment(
        frames,
        1.28,
        "natural",
        "首先行＋肩が少し追従して左へ",
        0,
        -1,
    )
    append_segment(frames, 0.32, "natural", "自然な左向き・ニュートラル", -1)
    append_segment(
        frames,
        1.24,
        "natural",
        "自然な左向き・瞬き＋ASMR小口パク",
        -1,
        mouth=True,
        blink_center=0.46,
    )
    append_segment(frames, 1.20, "natural", "自然な左向きから正面へ", -1, 0)
    append_segment(frames, 0.32, "natural", "正面・間", 0)
    append_segment(
        frames,
        1.28,
        "natural",
        "首先行＋肩が少し追従して右へ",
        0,
        1,
    )
    append_segment(frames, 0.32, "natural", "自然な右向き・ニュートラル", 1)
    append_segment(
        frames,
        1.24,
        "natural",
        "自然な右向き・瞬き＋ASMR小口パク",
        1,
        mouth=True,
        blink_center=0.46,
    )
    append_segment(frames, 1.20, "natural", "自然な右向きから正面へ", 1, 0)
    append_segment(frames, 0.40, "natural", "自然な会話モード・正面", 0)

    # FULL: front -> left 3/4 -> front -> right 3/4 -> front.
    append_segment(frames, 0.48, "full", "既存の全身3/4モードも保持", 0)
    append_segment(
        frames,
        1.36,
        "full",
        "全身3/4へ、瞬きを橋渡しにして左へ",
        0,
        -1,
    )
    append_segment(frames, 0.32, "full", "左3/4・ニュートラル", -1)
    append_segment(
        frames,
        1.36,
        "full",
        "左3/4・瞬き＋ASMR小口パク",
        -1,
        mouth=True,
        blink_center=0.46,
    )
    append_segment(frames, 1.28, "full", "左3/4から正面へ", -1, 0)
    append_segment(frames, 0.36, "full", "正面・間", 0)
    append_segment(
        frames,
        1.36,
        "full",
        "全身3/4へ、瞬きを橋渡しにして右へ",
        0,
        1,
    )
    append_segment(frames, 0.32, "full", "右3/4・ニュートラル", 1)
    append_segment(
        frames,
        1.36,
        "full",
        "右3/4・瞬き＋ASMR小口パク",
        1,
        mouth=True,
        blink_center=0.46,
    )
    append_segment(frames, 1.28, "full", "右3/4から正面へ", 1, 0)
    append_segment(frames, 0.36, "full", "正面・間", 0)

    # SOFT: the body remains frontal while the localized head mesh sways.
    append_segment(
        frames,
        1.12,
        "soft",
        "やわらか首振り・小さく左へ",
        0,
        -0.72,
        mouth=True,
    )
    append_segment(
        frames,
        1.72,
        "soft",
        "やわらか首振り・左から右へ",
        -0.72,
        0.72,
        mouth=True,
        blink_center=0.52,
    )
    append_segment(
        frames,
        1.12,
        "soft",
        "やわらか首振り・正面へ",
        0.72,
        0,
    )
    append_segment(frames, 0.32, "soft", "やわらか首振り・正面", 0)

    # HEAD-ONLY: stronger localized neck/head motion, torso locked forward.
    append_segment(
        frames,
        1.12,
        "head-only",
        "体は正面のまま、首だけ左へ",
        0,
        -1,
        mouth=True,
    )
    append_segment(
        frames,
        1.84,
        "head-only",
        "体は正面のまま、首を左から右へ",
        -1,
        1,
        mouth=True,
        blink_center=0.50,
    )
    append_segment(
        frames,
        1.12,
        "head-only",
        "体は正面のまま、首を正面へ",
        1,
        0,
    )
    append_segment(frames, 0.52, "head-only", "正面へ自然に戻る", 0)
    return frames


def prepare_deterministic_engine(page):
    return page.evaluate(
        """({ width, height, fps }) => {
            const engine = window.__PUPPET__;
            if (!engine?.app) throw new Error('Puppet engine is unavailable');

            engine.app.ticker.stop();
            engine.pause();
            engine.script = null;
            engine.setAudioLevelSource(null);
            engine.nextBlinkAt = Number.POSITIVE_INFINITY;
            engine.blinkStartedAt = null;
            engine.onUpdate = null;
            engine.resizeObserver?.disconnect();
            engine.app.renderer.resize(width, height);
            engine.setFraming('short');

            const clock = { seconds: 0 };
            window.__CAPTURE_CLOCK__ = clock;
            window.__CAPTURE_ENGINE__ = engine;
            window.__CAPTURE_BLINK__ = 0;
            engine.getSessionElapsed = () => clock.seconds;
            engine.getAutoBlink = () => window.__CAPTURE_BLINK__;

            const neutral = {
                turn: 0,
                blink: 0,
                mouthOpen: 0,
                speech: 0,
                headX: 0,
                headY: 0,
                headTilt: 0,
                shoulderSway: 0,
                breath: 0.24
            };
            engine.setTurnVariant('natural');
            engine.setManualPose(neutral);
            for (let index = 0; index < 40; index += 1) {
                clock.seconds += 1 / fps;
                engine.tick(1 / fps);
            }
            engine.app.render();

            return {
                width: engine.app.screen.width,
                height: engine.app.screen.height,
                tickerStarted: engine.app.ticker.started,
                variant: engine.turnVariant,
                wide: engine.lastMouthWeights.wide
            };
        }""",
        {"width": FRAME_WIDTH, "height": FRAME_HEIGHT, "fps": CAPTURE_FPS},
    )


def render_frame(page, plan, delta_seconds):
    return page.evaluate(
        """({ plan, deltaSeconds, quietMouthMax }) => {
            const engine = window.__PUPPET__;
            if (engine !== window.__CAPTURE_ENGINE__) {
                throw new Error('Puppet engine changed during deterministic capture');
            }
            const mouthOpen = Math.min(
                quietMouthMax,
                Math.max(0, plan.mouthOpen)
            );
            engine.setTurnVariant(plan.variant);
            engine.setManualPose({
                turn: plan.turn,
                blink: plan.blink,
                mouthOpen,
                speech: 0,
                headX: 0,
                headY: 0,
                headTilt: 0,
                shoulderSway: 0,
                breath: 0.24
            });
            const modeLabel = {
                natural: 'NATURAL / HEAD-LED TURN',
                full: 'FULL 3/4 TURN',
                soft: 'SOFT HEAD SWAY',
                'head-only': 'HEAD ONLY / FRONT BODY'
            }[plan.variant];
            document.querySelector('#stage-mode').textContent = modeLabel;
            document.querySelector('#cue-note').textContent = plan.note;
            document.querySelector('#stage-fps').textContent =
                `${Math.round(1 / deltaSeconds)} FPS`;
            window.__CAPTURE_BLINK__ = plan.blink;
            window.__CAPTURE_CLOCK__.seconds += deltaSeconds;
            engine.tick(deltaSeconds);
            engine.app.render();

            const mouth = engine.lastMouthWeights;
            const side = engine.lastSideExpressionWeights;
            const transition = engine.turnTransitionState;
            const bridge = engine.lastTurnBridgeVisuals;
            const turnWeights = engine.lastTurnWeights;
            return {
                variant: engine.turnVariant,
                front: engine.frontGroup.alpha,
                naturalLeft: engine.naturalLeftPoseGroup.alpha,
                naturalRight: engine.naturalRightPoseGroup.alpha,
                left: engine.leftPoseGroup.alpha,
                right: engine.rightPoseGroup.alpha,
                turnWeightFront: turnWeights.front,
                turnWeightNaturalLeft: turnWeights.naturalLeft,
                turnWeightNaturalRight: turnWeights.naturalRight,
                turnWeightLeft: turnWeights.left,
                turnWeightRight: turnWeights.right,
                blink: side.blink + side.blinkMouthSmall,
                sideMouth: side.mouthSmall + side.blinkMouthSmall,
                wide: mouth.wide,
                wideAlpha: engine.layers.mouthWide.alpha,
                tickerStarted: engine.app.ticker.started,
                transitionPhase: transition.phase,
                transitionBlink: transition.blink,
                displayPose: transition.displayPose,
                targetPose: transition.targetPose,
                bridgeActive: bridge.active,
                bridgeProgress: bridge.progress
            };
        }""",
        {
            "plan": {
                "variant": plan.variant,
                "turn": plan.turn,
                "blink": plan.blink,
                "mouthOpen": plan.mouth_open,
                "note": plan.note,
            },
            "deltaSeconds": delta_seconds,
            "quietMouthMax": QUIET_MOUTH_MAX,
        },
    )


def frame_mean(path):
    image = Image.open(path).convert("RGB")
    return sum(ImageStat.Stat(image).mean) / 3.0


def thumbnail_difference(first, second):
    difference = ImageChops.difference(first, second)
    return sum(ImageStat.Stat(difference).mean) / 3.0


def encode_candidate(frames_dir, candidate_path):
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-framerate",
            str(CAPTURE_FPS),
            "-start_number",
            "0",
            "-i",
            str(frames_dir / "%06d.png"),
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-r",
            str(CAPTURE_FPS),
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(candidate_path),
        ],
        check=True,
    )


def probe_candidate(candidate_path, expected_frames):
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=width,height,avg_frame_rate,nb_frames",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(candidate_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    stream = payload["streams"][0]
    actual_fps = float(Fraction(stream["avg_frame_rate"]))
    actual_frames = int(stream["nb_frames"])
    duration = float(payload["format"]["duration"])

    assert stream["width"] == FRAME_WIDTH
    assert stream["height"] == FRAME_HEIGHT
    assert abs(actual_fps - CAPTURE_FPS) < 0.001
    assert actual_frames == expected_frames
    assert abs(duration - expected_frames / CAPTURE_FPS) <= 1 / CAPTURE_FPS

    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(candidate_path),
            "-f",
            "null",
            "-",
        ],
        check=True,
    )
    return {
        "fps": actual_fps,
        "frames": actual_frames,
        "duration": duration,
        "width": stream["width"],
        "height": stream["height"],
    }


def capture_frames(page, frames_dir, timeline):
    stage = page.locator("#puppet-stage")
    assert stage.is_visible()

    seen = {
        "natural_left": False,
        "natural_right": False,
        "natural_left_blink": False,
        "natural_left_mouth": False,
        "natural_right_blink": False,
        "natural_right_mouth": False,
        "full_left": False,
        "full_right": False,
        "left_blink": False,
        "left_mouth": False,
        "right_blink": False,
        "right_mouth": False,
    }
    variants = set()
    bridge_frames = {}
    return_source_hold = {}
    previous_thumbnail = None
    max_frame_difference = 0.0

    for frame_index, plan in enumerate(timeline):
        state = render_frame(page, plan, 1 / CAPTURE_FPS)
        assert not state["tickerStarted"]
        assert state["wide"] <= 1e-9
        assert state["wideAlpha"] <= 1e-9

        variants.add(state["variant"])
        transition_pair = (
            f'{state["displayPose"]}->{state["targetPose"]}'
        )
        if state["bridgeActive"]:
            bridge_frames[transition_pair] = (
                bridge_frames.get(transition_pair, 0) + 1
            )
        if (
            state["transitionPhase"] == "source-hold"
            and state["displayPose"] in {"left", "right"}
            and state["targetPose"] == "front"
        ):
            entry = return_source_hold.setdefault(
                transition_pair,
                {"frames": 0, "minBlink": 1.0, "firstFrame": frame_index},
            )
            entry["frames"] += 1
            entry["minBlink"] = min(
                entry["minBlink"],
                state["transitionBlink"],
            )
        if (
            state["variant"] == "natural"
            and state["transitionPhase"] != "bridge"
            and state["displayPose"] == "natural-left"
            and state["turnWeightNaturalLeft"] > 0.999
        ):
            seen["natural_left"] = True
            seen["natural_left_blink"] |= (
                plan.blink > 0.75 and state["blink"] > 0.75
            )
            seen["natural_left_mouth"] |= state["sideMouth"] > 0.75
        if (
            state["variant"] == "natural"
            and state["transitionPhase"] != "bridge"
            and state["displayPose"] == "natural-right"
            and state["turnWeightNaturalRight"] > 0.999
        ):
            seen["natural_right"] = True
            seen["natural_right_blink"] |= (
                plan.blink > 0.75 and state["blink"] > 0.75
            )
            seen["natural_right_mouth"] |= state["sideMouth"] > 0.75
        if (
            state["variant"] == "full"
            and state["transitionPhase"] != "bridge"
            and state["displayPose"] == "left"
            and state["turnWeightLeft"] > 0.999
        ):
            seen["full_left"] = True
            seen["left_blink"] |= (
                plan.blink > 0.75 and state["blink"] > 0.75
            )
            seen["left_mouth"] |= state["sideMouth"] > 0.75
        if (
            state["variant"] == "full"
            and state["transitionPhase"] != "bridge"
            and state["displayPose"] == "right"
            and state["turnWeightRight"] > 0.999
        ):
            seen["full_right"] = True
            seen["right_blink"] |= (
                plan.blink > 0.75 and state["blink"] > 0.75
            )
            seen["right_mouth"] |= state["sideMouth"] > 0.75

        frame_path = frames_dir / f"{frame_index:06d}.png"
        stage.screenshot(
            path=str(frame_path),
            type="png",
            animations="disabled",
            caret="hide",
        )
        with Image.open(frame_path) as captured:
            assert captured.size == (FRAME_WIDTH, FRAME_HEIGHT)
            thumbnail = captured.convert("RGB").resize((90, 160))
        if previous_thumbnail is not None:
            max_frame_difference = max(
                max_frame_difference,
                thumbnail_difference(previous_thumbnail, thumbnail),
            )
        previous_thumbnail = thumbnail

    assert variants == {"natural", "full", "soft", "head-only"}
    assert all(seen.values()), seen
    expected_bridges = {
        "front->natural-left",
        "natural-left->front",
        "front->natural-right",
        "natural-right->front",
        "front->left",
        "left->front",
        "front->right",
        "right->front",
    }
    assert set(bridge_frames) == expected_bridges, bridge_frames
    assert all(7 <= count <= 10 for count in bridge_frames.values()), (
        bridge_frames
    )
    assert set(return_source_hold) == {"left->front", "right->front"}
    assert all(
        entry["frames"] >= 2 and entry["minBlink"] >= 0.999
        for entry in return_source_hold.values()
    ), return_source_hold
    assert frame_mean(frames_dir / "000000.png") > 30
    return {
        "variants": sorted(variants),
        "coverage": seen,
        "bridgeFrames": bridge_frames,
        "returnSourceHold": return_source_hold,
        "maxFrameDifference": max_frame_difference,
    }


def main():
    timeline = build_timeline()
    temporary_root = Path(tempfile.mkdtemp(prefix="tsukuyomi-side-motion-"))
    frames_dir = temporary_root / "frames"
    frames_dir.mkdir(parents=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    candidate_path = OUTPUT_DIR / (
        f".{MP4_PATH.stem}.candidate-{os.getpid()}.mp4"
    )

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": FRAME_WIDTH, "height": FRAME_HEIGHT},
                device_scale_factor=1,
            )
            page = context.new_page()
            console_errors = []
            page.on(
                "console",
                lambda message: console_errors.append(message.text)
                if message.type == "error"
                else None,
            )
            page.goto(BASE_URL)
            page.wait_for_load_state("networkidle")
            page.wait_for_selector('body[data-ready="true"]', timeout=20000)
            page.add_style_tag(content=ISOLATE_STAGE_CSS)
            setup = prepare_deterministic_engine(page)
            assert setup == {
                "width": FRAME_WIDTH,
                "height": FRAME_HEIGHT,
                "tickerStarted": False,
                "variant": "natural",
                "wide": 0,
            }
            capture_report = capture_frames(page, frames_dir, timeline)
            assert not console_errors, console_errors
            context.close()
            browser.close()

        encode_candidate(frames_dir, candidate_path)
        probe = probe_candidate(candidate_path, len(timeline))
        os.replace(candidate_path, MP4_PATH)
        print(
            json.dumps(
                {
                    "output": str(MP4_PATH.resolve()),
                    "capture": capture_report,
                    "probe": probe,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        candidate_path.unlink(missing_ok=True)
        shutil.rmtree(temporary_root, ignore_errors=True)


if __name__ == "__main__":
    main()
