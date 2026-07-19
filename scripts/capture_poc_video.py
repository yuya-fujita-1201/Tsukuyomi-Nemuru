import os
import shutil
import subprocess
from pathlib import Path

from playwright.sync_api import sync_playwright


BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:4173")
OUTPUT_DIR = Path("output/video")
TEMP_DIR = OUTPUT_DIR / ".playwright"
WEBM_PATH = OUTPUT_DIR / "tsukuyomi-faceless-poc-v5.webm"
MP4_PATH = OUTPUT_DIR / "tsukuyomi-faceless-poc-v5.mp4"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
shutil.rmtree(TEMP_DIR, ignore_errors=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)

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

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(
        viewport={"width": 720, "height": 1280},
        record_video_dir=str(TEMP_DIR),
        record_video_size={"width": 720, "height": 1280},
    )
    page = context.new_page()
    page.goto(BASE_URL)
    page.wait_for_load_state("networkidle")
    page.wait_for_selector('body[data-ready="true"]', timeout=20000)
    page.add_style_tag(content=ISOLATE_STAGE_CSS)
    page.wait_for_timeout(1000)
    page.evaluate(
        """() => {
          window.__PUPPET__.setFraming('short');
          window.__PUPPET__.restart();
        }"""
    )
    page.wait_for_timeout(13200)
    video = page.video
    context.close()
    recorded_path = Path(video.path())
    browser.close()

shutil.move(recorded_path, WEBM_PATH)
subprocess.run(
    [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(WEBM_PATH),
        "-ss",
        "2.1",
        "-t",
        "13.4",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(MP4_PATH),
    ],
    check=True,
)
WEBM_PATH.unlink(missing_ok=True)
shutil.rmtree(TEMP_DIR, ignore_errors=True)
print(MP4_PATH.resolve())
