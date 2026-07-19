# ImageGen Prompt: body_torso

## Input roles

- `front-master-v2-chroma.png`: canonical visual reference and coordinate source.
- `guides/body_torso-guide.png`: layout mask only. White indicates the allowed approximate silhouette and hidden-overlap area.

## Target

Generate exactly one full-canvas part: `body_torso`.

- 1086×1448 canvas
- approximate allowed bbox: left=270, top=460, right=816, bottom=1448
- approximate bbox size: width=546, height=988, center=(543.0, 954.0)
- white guide footprint covers about 28.5% of the canvas
- same coordinate placement as the canonical reference
- include neck, clavicles, upper chest, lavender nightdress, and the cardigan's central back/body panels
- exclude the cardigan sleeves, arms, hands, head, face, ears, all hair, eyes, mouth, earrings, and hair accessories
- continue hidden skin and clothing below the face, hair, collar, shoulders, and sleeves
- every non-target pixel must be flat chroma green `#00FF00`
- do not crop, resize, or recenter the part
