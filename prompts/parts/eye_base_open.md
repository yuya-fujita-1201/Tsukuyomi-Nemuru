# ImageGen Prompt: eye_base_open

Generate exactly one 1086×1448 full-canvas part containing only the two open-eye
bases for Tsukuyomi Nemuri:

- both white sclera shapes
- upper and lower eyelid lines
- long elegant lavender-brown eyelashes
- subtle eyelid crease shading

The irises will be animated independently, so this part must not contain irises,
pupils, catchlights, eyebrows, skin, hair, nose, mouth, or any other face/body
pixels.

Coordinate contract:

- viewer-left eye / character-right: approximately x=425..520, y=365..430
- viewer-right eye / character-left: approximately x=565..660, y=365..430
- preserve the canonical calm, slightly sleepy expression
- keep the two eyes symmetrical but naturally hand-drawn

Every non-target pixel must be perfectly flat `#00FF00`.
