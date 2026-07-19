# ImageGen Prompt: arm_l_base v2

The first generated left arm is rejected because its spatial direction is reversed.

Required screen-space direction:

- shoulder attachment: viewer-right half, but on the inner/left side of the target bbox, around x=680-800
- sleeve descends diagonally toward the outer/right side
- wrist and hand: x=850-1061
- fingertips point downward and slightly toward viewer-right
- never put the shoulder near x=1000
- never put the hand near x=700

Generate actual character-left anatomy from the canonical master. Do not merely reuse the rejected output.
