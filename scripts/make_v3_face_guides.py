from pathlib import Path

from PIL import Image, ImageDraw


CANVAS = (1086, 1448)
OUT = Path("assets/character-v3/guides")
TRANSPARENT = (0, 0, 0, 0)
OPAQUE = (255, 255, 255, 255)


def save(name, painter):
    image = Image.new("RGBA", CANVAS, TRANSPARENT)
    painter(ImageDraw.Draw(image))
    path = OUT / f"{name}-guide.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    print(path)


def eye_base_open(draw):
    draw.ellipse((435, 315, 520, 363), fill=OPAQUE)
    draw.ellipse((565, 315, 655, 363), fill=OPAQUE)


def irises(draw):
    draw.ellipse((463, 323, 505, 360), fill=OPAQUE)
    draw.ellipse((585, 323, 630, 360), fill=OPAQUE)


def eyes_closed(draw):
    draw.ellipse((435, 326, 520, 356), fill=OPAQUE)
    draw.ellipse((565, 326, 655, 356), fill=OPAQUE)


def brows_neutral(draw):
    draw.rounded_rectangle((440, 291, 515, 311), radius=9, fill=OPAQUE)
    draw.rounded_rectangle((575, 291, 650, 311), radius=9, fill=OPAQUE)


def mouth_closed(draw):
    draw.ellipse((525, 407, 575, 426), fill=OPAQUE)


def mouth_open_small(draw):
    draw.ellipse((527, 402, 570, 441), fill=OPAQUE)


def mouth_open_wide(draw):
    draw.ellipse((519, 394, 581, 453), fill=OPAQUE)


GUIDES = {
    "eye_base_open": eye_base_open,
    "irises": irises,
    "eyes_closed": eyes_closed,
    "brows_neutral": brows_neutral,
    "mouth_closed": mouth_closed,
    "mouth_open_small": mouth_open_small,
    "mouth_open_wide": mouth_open_wide,
}


if __name__ == "__main__":
    for name, painter in GUIDES.items():
        save(name, painter)
