from pathlib import Path

from PIL import Image, ImageDraw


CANVAS = (1086, 1448)
FACE = Path("assets/character-v2/parts/aligned/face_base-v2.png")
EYE_BASE = Path("assets/character-v2/parts/aligned/eye_base_open.png")
IRISES = Path("assets/character-v2/parts/aligned/irises.png")
OUT = Path("assets/character-v2/previews/gaze-range-v1.png")

STATES = [
    ("LEFT", -6, 0),
    ("CENTER", 0, 0),
    ("RIGHT", 6, 0),
    ("UP", 0, -4),
    ("DOWN", 0, 4),
]


def shifted(image: Image.Image, x: int, y: int) -> Image.Image:
    output = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    output.alpha_composite(image, (x, y))
    return output


def main() -> None:
    face = Image.open(FACE).convert("RGBA")
    eye_base = Image.open(EYE_BASE).convert("RGBA")
    irises = Image.open(IRISES).convert("RGBA")

    sheet = Image.new("RGBA", (CANVAS[0] * len(STATES), CANVAS[1]), (32, 26, 48, 255))
    draw = ImageDraw.Draw(sheet)
    for index, (label, x, y) in enumerate(STATES):
        frame = face.copy()
        frame.alpha_composite(eye_base)
        frame.alpha_composite(shifted(irises, x, y))
        left = index * CANVAS[0]
        sheet.alpha_composite(frame, (left, 0))
        draw.text((left + 20, 20), f"{label} ({x:+d},{y:+d})", fill="white")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(OUT)
    print(OUT)


if __name__ == "__main__":
    main()
