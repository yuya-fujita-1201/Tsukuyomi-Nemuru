#!/usr/bin/env python3
"""Build character-v4 runtime assets from the user-authored model sheets."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
CANVAS = (1086, 1448)
KEY_COLOR = (0, 255, 0, 255)
ASSET_ROOT = ROOT / "assets/character-v4"
RAW_ROOT = ASSET_ROOT / "raw/imagegen"
WORK_ROOT = ASSET_ROOT / "work"
PARTS_ROOT = ASSET_ROOT / "parts/aligned-v1"
CROPS_ROOT = ASSET_ROOT / "parts/source-crops"
GUIDES_ROOT = ASSET_ROOT / "guides"
MODELS_ROOT = ROOT / "models"

CHROMA_SCRIPT = (
    Path.home()
    / ".codex/skills/.system/imagegen/scripts/remove_chroma_key.py"
)

EXPRESSION_SHEET = MODELS_ROOT / "ChatGPT Image 2026年7月17日 22_01_43.png"

# Pixel bboxes measured from the user-authored expression sheet.
SOURCE_BBOXES = {
    "eye_open_l": (575, 174, 668, 230),
    "eye_open_r": (721, 173, 816, 230),
    "eye_closed_l": (1375, 206, 1475, 229),
    "eye_closed_r": (1526, 205, 1627, 227),
    "brow_l": (583, 379, 668, 401),
    "brow_r": (716, 378, 802, 401),
    "mouth_closed": (673, 736, 758, 754),
    "mouth_open_small": (917, 723, 1003, 769),
    "mouth_open_wide": (1165, 712, 1258, 781),
}

# Full-canvas target positions on the approved 1086x1448 faceless base.
TARGET_POSITIONS = {
    "eye_open_l": (407, 420),
    "eye_open_r": (585, 420),
    "eye_closed_l": (404, 443),
    "eye_closed_r": (582, 443),
    "brow_l": (415, 384),
    "brow_r": (586, 384),
    "mouth_closed": (501, 555),
    "mouth_open_small": (500, 541),
    "mouth_open_wide": (497, 531),
}


def normalize_on_green(source: Path, out: Path, *, offset_y: int = 0) -> None:
    """Preserve aspect ratio, center on the exact runtime canvas, and pad green."""
    with Image.open(source) as image:
        rgb = image.convert("RGB")
    scale = min(CANVAS[0] / rgb.width, CANVAS[1] / rgb.height)
    size = (max(1, round(rgb.width * scale)), max(1, round(rgb.height * scale)))
    resized = rgb.resize(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", CANVAS, KEY_COLOR[:3])
    left = (CANVAS[0] - size[0]) // 2
    top = (CANVAS[1] - size[1]) // 2 + offset_y
    canvas.paste(resized, (left, top))
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)


def remove_chroma(source: Path, out: Path) -> None:
    if not CHROMA_SCRIPT.exists():
        raise FileNotFoundError(f"Missing chroma-key helper: {CHROMA_SCRIPT}")
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            sys.executable,
            str(CHROMA_SCRIPT),
            "--input",
            str(source),
            "--out",
            str(out),
            "--auto-key",
            "corners",
            "--soft-matte",
            "--transparent-threshold",
            "18",
            "--opaque-threshold",
            "86",
            "--edge-feather",
            "0.35",
            "--despill",
            "--force",
        ],
        check=True,
    )


def crop_with_margin(sheet: Image.Image, bbox: tuple[int, int, int, int], margin: int = 6) -> Image.Image:
    left, top, right, bottom = bbox
    crop_box = (
        max(0, left - margin),
        max(0, top - margin),
        min(sheet.width, right + margin),
        min(sheet.height, bottom + margin),
    )
    crop = sheet.crop(crop_box)
    alpha_bbox = crop.getchannel("A").point(lambda value: 255 if value > 12 else 0).getbbox()
    if alpha_bbox is None:
        raise ValueError(f"Empty expression crop for bbox {bbox}")
    return crop.crop(alpha_bbox)


def save_layer(name: str, parts: list[tuple[Image.Image, tuple[int, int]]]) -> None:
    canvas = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    for part, position in parts:
        canvas.alpha_composite(part, position)
    out = PARTS_ROOT / f"{name}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)

    guide = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    alpha = canvas.getchannel("A").point(lambda value: 255 if value > 12 else 0)
    guide.paste((255, 255, 255, 255), (0, 0), alpha)
    GUIDES_ROOT.mkdir(parents=True, exist_ok=True)
    guide.save(GUIDES_ROOT / f"{name}-guide.png")


def main() -> None:
    source_assets = {
        "front": RAW_ROOT / "front-faceless-clean-chroma-v1.png",
        "left": RAW_ROOT / "view-left-3q-chroma-v1.png",
        "right": RAW_ROOT / "view-right-3q-chroma-v1.png",
    }
    for name, path in source_assets.items():
        if not path.exists():
            raise FileNotFoundError(f"Missing ImageGen source for {name}: {path}")
    if not EXPRESSION_SHEET.exists():
        raise FileNotFoundError(f"Missing expression sheet: {EXPRESSION_SHEET}")

    normalized = {}
    offsets_y = {"front": 0, "left": 0, "right": -65}
    for name, source in source_assets.items():
        out = WORK_ROOT / f"{name}-chroma-normalized.png"
        normalize_on_green(source, out, offset_y=offsets_y[name])
        normalized[name] = out

    remove_chroma(normalized["front"], ASSET_ROOT / "master/front-faceless-v1.png")
    remove_chroma(normalized["left"], ASSET_ROOT / "poses/view-left-3q-v1.png")
    remove_chroma(normalized["right"], ASSET_ROOT / "poses/view-right-3q-v1.png")

    expression_alpha = WORK_ROOT / "expression-sheet-alpha.png"
    remove_chroma(EXPRESSION_SHEET, expression_alpha)
    with Image.open(expression_alpha) as source:
        sheet = source.convert("RGBA")

    crops: dict[str, Image.Image] = {}
    CROPS_ROOT.mkdir(parents=True, exist_ok=True)
    for name, bbox in SOURCE_BBOXES.items():
        crop = crop_with_margin(sheet, bbox)
        crops[name] = crop
        crop.save(CROPS_ROOT / f"{name}.png")

    save_layer(
        "eye_base_open",
        [
            (crops["eye_open_l"], TARGET_POSITIONS["eye_open_l"]),
            (crops["eye_open_r"], TARGET_POSITIONS["eye_open_r"]),
        ],
    )
    save_layer(
        "eyes_closed",
        [
            (crops["eye_closed_l"], TARGET_POSITIONS["eye_closed_l"]),
            (crops["eye_closed_r"], TARGET_POSITIONS["eye_closed_r"]),
        ],
    )
    save_layer(
        "brows_neutral",
        [
            (crops["brow_l"], TARGET_POSITIONS["brow_l"]),
            (crops["brow_r"], TARGET_POSITIONS["brow_r"]),
        ],
    )
    save_layer(
        "mouth_closed",
        [(crops["mouth_closed"], TARGET_POSITIONS["mouth_closed"])],
    )
    save_layer(
        "mouth_open_small",
        [(crops["mouth_open_small"], TARGET_POSITIONS["mouth_open_small"])],
    )
    save_layer(
        "mouth_open_wide",
        [(crops["mouth_open_wide"], TARGET_POSITIONS["mouth_open_wide"])],
    )

    # The supplied eye sheet contains complete eyes rather than sclera-only eyes.
    # Keep a practically invisible placeholder so the v3 runtime API remains stable.
    irises = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    irises.putpixel((543, 448), (255, 255, 255, 1))
    PARTS_ROOT.mkdir(parents=True, exist_ok=True)
    irises.save(PARTS_ROOT / "irises.png")
    iris_guide = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    iris_guide.putpixel((543, 448), (255, 255, 255, 255))
    iris_guide.save(GUIDES_ROOT / "irises-guide.png")

    print(f"Built character-v4 assets under {ASSET_ROOT}")


if __name__ == "__main__":
    main()
