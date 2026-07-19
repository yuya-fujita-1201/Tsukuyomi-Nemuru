# ImageGen Prompt: hair_back

## Input roles

- `front-master-v2-chroma.png`: canonical visual reference and coordinate source.
- `guides/hair_back-guide.png`: layout mask only. White indicates the allowed approximate silhouette and hidden-overlap area.

## Target

Generate exactly one full-canvas part: `hair_back`.

- 1086×1448 canvas
- approximate allowed bbox: left=90, top=55, right=996, bottom=1448
- approximate bbox size: width=906, height=1393, center=(543.0, 751.5)
- the white guide footprint covers about 65.7% of the canvas because it includes hidden under-paint
- same coordinate placement as the canonical reference
- only the rear hair mass behind the head, neck, shoulders, torso, and arms
- include the upper hair cap and long rear hair on both sides
- include hidden hair under the face, neck, shoulders, body, and front hair
- do not include face, skin, ears, eyes, mouth, bangs, front side locks, bow, moon ornament, earrings, clothing, arms, or hands
- every non-target pixel must be flat chroma green `#00FF00`
- do not crop, resize, or recenter the part
