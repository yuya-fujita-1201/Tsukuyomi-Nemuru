from pathlib import Path

from PIL import Image


PARTS = {
    Path("assets/character-v2/parts/aligned/arm_r_base.png"): Path(
        "assets/character-v2/parts/aligned/arm_r_base-v2.png"
    ),
    Path("assets/character-v2/parts/aligned/arm_l_base-v2.png"): Path(
        "assets/character-v2/parts/aligned/arm_l_base-v3.png"
    ),
}


def main() -> None:
    for source, output in PARTS.items():
        image = Image.open(source).convert("RGBA")
        if image.size != (1086, 1448):
            raise ValueError(f"Unexpected source size for {source}: {image.size}")

        pixels = image.load()
        removed = 0
        for y in range(540, 800):
            for x in range(image.width):
                red, green, blue, alpha = pixels[x, y]
                is_hidden_inner_shoulder = (
                    source.name == "arm_r_base.png" and x >= 225
                ) or (
                    source.name == "arm_l_base-v2.png" and x <= 860
                )
                if alpha and is_hidden_inner_shoulder:
                    pixels[x, y] = (red, green, blue, 0)
                    removed += 1

        output.parent.mkdir(parents=True, exist_ok=True)
        image.save(output)
        print(f"{output}: removed {removed} hidden shoulder pixels")


if __name__ == "__main__":
    main()
