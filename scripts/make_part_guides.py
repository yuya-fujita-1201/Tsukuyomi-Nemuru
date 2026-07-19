from pathlib import Path

from PIL import Image, ImageDraw


CANVAS = (1086, 1448)
OUT = Path("assets/character-v2/guides")
BG = (0, 0, 0, 0)
FG = (255, 255, 255, 255)


def save(name: str, draw_fn) -> None:
    image = Image.new("RGBA", CANVAS, BG)
    draw = ImageDraw.Draw(image)
    draw_fn(draw)
    path = OUT / f"{name}-guide.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    print(path)


def hair_back(draw: ImageDraw.ImageDraw) -> None:
    draw.ellipse((250, 55, 842, 650), fill=FG)
    draw.polygon(
        [(250, 240), (145, 560), (90, 1030), (185, 1447), (460, 1447), (465, 520)],
        fill=FG,
    )
    draw.polygon(
        [(835, 240), (940, 560), (995, 1030), (900, 1447), (625, 1447), (620, 520)],
        fill=FG,
    )
    draw.rectangle((365, 360, 720, 1447), fill=FG)


def body_torso(draw: ImageDraw.ImageDraw) -> None:
    draw.polygon(
        [(470, 460), (615, 460), (700, 570), (815, 800), (770, 1447), (315, 1447), (270, 800), (385, 570)],
        fill=FG,
    )


def face_base(draw: ImageDraw.ImageDraw) -> None:
    draw.ellipse((365, 205, 720, 590), fill=FG)
    draw.polygon([(470, 520), (615, 520), (645, 720), (440, 720)], fill=FG)
    draw.ellipse((340, 330, 400, 480), fill=FG)
    draw.ellipse((685, 330, 745, 480), fill=FG)


def hair_front(draw: ImageDraw.ImageDraw) -> None:
    draw.pieslice((292, 65, 794, 610), start=180, end=360, fill=FG)
    draw.polygon([(310, 160), (475, 115), (525, 500), (390, 620), (340, 500)], fill=FG)
    draw.polygon([(775, 160), (610, 115), (560, 500), (695, 620), (745, 500)], fill=FG)
    draw.polygon([(360, 320), (455, 330), (465, 970), (345, 900)], fill=FG)
    draw.polygon([(725, 320), (630, 330), (620, 970), (740, 900)], fill=FG)


def arm_r_base(draw: ImageDraw.ImageDraw) -> None:
    draw.polygon(
        [(285, 570), (405, 610), (360, 940), (255, 1280), (150, 1395), (25, 1380), (125, 1260), (170, 850)],
        fill=FG,
    )


def arm_l_base(draw: ImageDraw.ImageDraw) -> None:
    draw.polygon(
        [(800, 570), (680, 610), (725, 940), (830, 1280), (935, 1395), (1060, 1380), (960, 1260), (915, 850)],
        fill=FG,
    )


def accessory_head(draw: ImageDraw.ImageDraw) -> None:
    draw.ellipse((610, 130, 850, 500), fill=FG)
    draw.ellipse((395, 300, 470, 510), fill=FG)
    draw.ellipse((615, 300, 700, 510), fill=FG)


def eye_base_open(draw: ImageDraw.ImageDraw) -> None:
    draw.ellipse((425, 365, 520, 430), fill=FG)
    draw.ellipse((565, 365, 660, 430), fill=FG)


def irises(draw: ImageDraw.ImageDraw) -> None:
    draw.ellipse((455, 374, 505, 427), fill=FG)
    draw.ellipse((580, 374, 630, 427), fill=FG)


def brows_neutral(draw: ImageDraw.ImageDraw) -> None:
    draw.rounded_rectangle((430, 330, 515, 360), radius=14, fill=FG)
    draw.rounded_rectangle((570, 330, 655, 360), radius=14, fill=FG)


def eyes_closed(draw: ImageDraw.ImageDraw) -> None:
    draw.ellipse((425, 378, 520, 425), fill=FG)
    draw.ellipse((565, 378, 660, 425), fill=FG)


def mouth_closed(draw: ImageDraw.ImageDraw) -> None:
    draw.ellipse((505, 515, 580, 545), fill=FG)


def mouth_open_small(draw: ImageDraw.ImageDraw) -> None:
    draw.ellipse((513, 510, 573, 558), fill=FG)


def mouth_open_wide(draw: ImageDraw.ImageDraw) -> None:
    draw.ellipse((503, 500, 583, 570), fill=FG)


GUIDES = {
    "hair_back": hair_back,
    "body_torso": body_torso,
    "face_base": face_base,
    "hair_front": hair_front,
    "arm_r_base": arm_r_base,
    "arm_l_base": arm_l_base,
    "accessory_head": accessory_head,
    "eye_base_open": eye_base_open,
    "irises": irises,
    "brows_neutral": brows_neutral,
    "eyes_closed": eyes_closed,
    "mouth_closed": mouth_closed,
    "mouth_open_small": mouth_open_small,
    "mouth_open_wide": mouth_open_wide,
}


if __name__ == "__main__":
    for guide_name, guide_drawer in GUIDES.items():
        save(guide_name, guide_drawer)
