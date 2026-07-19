# Faceless front animation base v3

Use case: precise-object-edit
Asset type: full-canvas faceless base for a layered anime puppet
Input image: `assets/character-v2/master/front-master-v2.png` is the edit target and strict visual reference.

Primary request:
Keep the entire character exactly as in the input image, but remove only both eyes, both eyebrows, and the mouth. Fill those removed areas with seamless matching facial skin so the face becomes a clean neutral faceless animation base.

Scene/backdrop:
Perfectly flat solid #00ff00 chroma-key background.

Invariants:
- Preserve the exact 1086x1448 canvas and exact full-body placement.
- Preserve the original slim body proportions, shoulder width, face contour, head size, neck length, arms, hands, cardigan, dress, hair silhouette, ornaments, earrings, colors, line weight, lighting, and shading.
- Preserve the nose highlight, cheek shading, ears, jawline, and all non-facial artwork.
- Do not redraw, resize, widen, narrow, crop, recenter, or restyle the character.
- Change only the eyes, eyebrows, and mouth regions.
- The removed eye and mouth areas must be smooth skin with no eyelashes, sclera, iris, pupils, eyelid lines, brow lines, lip lines, teeth, or tongue.
- No new facial features.
- No text, watermark, cast shadow, floor, reflection, background gradient, or texture.
- Do not use #00ff00 anywhere on the character.

Output:
One full-canvas PNG-style raster image on the uniform chroma-key background, suitable for local background removal and overlaying separate eyes, brows, and mouth sprites.
