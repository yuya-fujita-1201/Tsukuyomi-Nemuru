# ImageGen Prompt: arm_l_base

## Naming

`l` means character-left, visible on viewer-right in the front-facing image.

## Target

Generate exactly one full-canvas part: `arm_l_base`.

- same 1086×1448 canvas and coordinates as `front-master-v2`
- approximate allowed bbox: left=680, top=570, right=1061, bottom=1396
- approximate bbox size: width=381, height=826, center=(870.5, 983.0)
- shoulder, cardigan sleeve, wrist, hand, and fingers on character-left only
- same relaxed-down pose and coordinates as `front-master-v2`
- include hidden shoulder and upper-arm paint beneath torso, hair, and cardigan collar
- include the sleeve cuff, sleeve bow, and the moon/star embroidery that physically moves with this sleeve
- exclude torso, chest, dress, opposite arm, head, hair, choker, earrings, and head accessories
- non-target pixels are flat `#00FF00`
