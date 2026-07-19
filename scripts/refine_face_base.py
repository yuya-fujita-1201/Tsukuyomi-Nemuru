from pathlib import Path

from PIL import Image


SOURCE = Path("assets/character-v2/parts/aligned/face_base.png")
OUTPUT = Path("assets/character-v2/parts/aligned/face_base-v2.png")


def main() -> None:
    image = Image.open(SOURCE).convert("RGBA")
    if image.size != (1086, 1448):
        raise ValueError(f"Unexpected source size: {image.size}")

    pixels = image.load()
    for y in range(620, image.height):
        if y >= 706:
            half_width = 0
        else:
            # Preserve the neck, choker, and pendant while removing the
            # rectangular chest underpaint that remains visible over the torso.
            half_width = round(72 - max(0, y - 620) * 0.18)

        left = 543 - half_width
        right = 543 + half_width
        for x in range(image.width):
            if x < left or x > right:
                red, green, blue, _ = pixels[x, y]
                pixels[x, y] = (red, green, blue, 0)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUTPUT)
    print(OUTPUT)


if __name__ == "__main__":
    main()
