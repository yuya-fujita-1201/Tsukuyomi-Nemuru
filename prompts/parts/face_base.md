# ImageGen Prompt: face_base

## Target

Generate exactly one full-canvas part: `face_base`.

- same canvas and coordinates as `front-master-v2`
- approximate allowed bbox: left=340, top=205, right=746, bottom=721
- approximate bbox size: width=406, height=516, center=(543.0, 463.0)
- face skin, both ears, neck, upper clavicle skin, choker, and pendant
- include a complete forehead beneath the bangs
- include complete skin beneath eye, brow, blush, nose, and mouth layers
- preserve the canonical face outline, subtle nose mark, base blush, and skin shading
- no hair, eyes, eye whites, irises, eyelashes, eyebrows, or mouth
- no earrings, hair bow, moon ornament, or dangling hair stars
- overlap the `body_torso` neck and clavicle by at least 80px
- non-target pixels are flat `#00FF00`
