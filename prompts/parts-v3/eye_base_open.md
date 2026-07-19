# ImageGen Prompt: v3 eye_base_open

Use case: precise-object-edit

Image 1 is the approved original front master and is the identity/style/coordinate
reference. Image 2 is the approved faceless overlay base and confirms the final
face position.

Create one full-canvas 1086×1448 animation layer containing only both open-eye
bases: white sclera, upper/lower eyelid lines, elegant lavender-brown eyelashes,
and subtle lid crease shading. Do not include irises, pupils, catchlights,
eyebrows, skin, hair, nose, mouth, ornaments, or body pixels.

Coordinate contract: viewer-left eye bbox x=435..520 y=315..363; viewer-right eye
bbox x=565..655 y=315..363. Keep the original master's narrow, calm, slightly
sleepy eye shape; do not enlarge or round the eyes. Same line weight, palette,
lighting, and exact placement as Image 1. Do not crop, recenter, or rescale.

Every non-target pixel must be perfectly flat #00FF00 with no gradient, shadow,
texture, glow, or transparency. One image only; no labels or guides.
