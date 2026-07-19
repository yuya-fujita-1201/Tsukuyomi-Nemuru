from __future__ import annotations

import json
from collections import deque
from pathlib import Path

from PIL import Image


CANVAS = (1086, 1448)
ALPHA_THRESHOLD = 32
SOURCE = Path("assets/character-v2/parts/accessory_head-v1-raw.png")
OUT_DIR = Path("assets/character-v2/parts/aligned")
PREVIEW_DIR = Path("assets/character-v2/previews")

TARGETS = {
    "accessory_head": (620, 130, 780, 400),
    "earring_r": (425, 330, 470, 465),
    "earring_l": (615, 330, 660, 465),
}


def connected_components(alpha: Image.Image) -> list[tuple[int, tuple[int, int, int, int]]]:
    mask = alpha.point(lambda value: 255 if value >= ALPHA_THRESHOLD else 0)
    width, height = mask.size
    pixels = mask.load()
    seen: set[tuple[int, int]] = set()
    components: list[tuple[int, tuple[int, int, int, int]]] = []

    for y in range(height):
        for x in range(width):
            if not pixels[x, y] or (x, y) in seen:
                continue

            queue = deque([(x, y)])
            seen.add((x, y))
            xs: list[int] = []
            ys: list[int] = []

            while queue:
                current_x, current_y = queue.pop()
                xs.append(current_x)
                ys.append(current_y)
                for next_x, next_y in (
                    (current_x - 1, current_y),
                    (current_x + 1, current_y),
                    (current_x, current_y - 1),
                    (current_x, current_y + 1),
                ):
                    if (
                        0 <= next_x < width
                        and 0 <= next_y < height
                        and pixels[next_x, next_y]
                        and (next_x, next_y) not in seen
                    ):
                        seen.add((next_x, next_y))
                        queue.append((next_x, next_y))

            if len(xs) >= 100:
                components.append(
                    (
                        len(xs),
                        (min(xs), min(ys), max(xs) + 1, max(ys) + 1),
                    )
                )

    return sorted(components, reverse=True)


def fit_component(
    source: Image.Image,
    source_bbox: tuple[int, int, int, int],
    target_bbox: tuple[int, int, int, int],
) -> tuple[Image.Image, tuple[int, int, int, int]]:
    crop = source.crop(source_bbox)
    source_width, source_height = crop.size
    target_left, target_top, target_right, target_bottom = target_bbox
    target_width = target_right - target_left
    target_height = target_bottom - target_top
    scale = min(target_width / source_width, target_height / source_height)
    width = max(1, round(source_width * scale))
    height = max(1, round(source_height * scale))
    resized = crop.resize((width, height), Image.Resampling.LANCZOS)

    left = round(target_left + (target_width - width) / 2)
    top = round(target_top + (target_height - height) / 2)
    layer = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    layer.alpha_composite(resized, (left, top))
    return layer, (left, top, left + width, top + height)


def main() -> None:
    source = Image.open(SOURCE).convert("RGBA")
    if source.size[0] != CANVAS[0] or source.size[1] < CANVAS[1]:
        raise ValueError(f"Unexpected source size: {source.size}")
    source = source.crop((0, 0, *CANVAS))

    components = connected_components(source.getchannel("A"))
    if len(components) != 3:
        raise ValueError(f"Expected exactly 3 accessory components, got {components}")

    main_component = components[0][1]
    earrings = sorted((components[1][1], components[2][1]), key=lambda bbox: bbox[0])
    source_boxes = {
        "accessory_head": main_component,
        "earring_r": earrings[0],
        "earring_l": earrings[1],
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    composite = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    output_boxes: dict[str, tuple[int, int, int, int]] = {}

    for name, target_bbox in TARGETS.items():
        layer, output_bbox = fit_component(source, source_boxes[name], target_bbox)
        layer.save(OUT_DIR / f"{name}.png")
        composite.alpha_composite(layer)
        output_boxes[name] = output_bbox

    composite.save(OUT_DIR / "accessory_set.png")

    checker = Image.new("RGBA", CANVAS, (30, 25, 45, 255))
    checker.alpha_composite(composite)
    checker.save(PREVIEW_DIR / "accessory-alignment-v1.png")

    metadata = {
        "status": "accepted",
        "source": str(SOURCE),
        "canvas": {"width": CANVAS[0], "height": CANVAS[1]},
        "alpha_threshold": ALPHA_THRESHOLD,
        "components": {
            name: {
                "source_bbox": list(source_boxes[name]),
                "target_bbox": list(TARGETS[name]),
                "output_bbox": list(output_boxes[name]),
                "mode": "fit",
            }
            for name in TARGETS
        },
    }
    (OUT_DIR / "accessory_set.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
