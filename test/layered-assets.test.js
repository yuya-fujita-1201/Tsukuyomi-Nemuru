import assert from "node:assert/strict";
import test from "node:test";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";

import {
  FACE_LAYOUT,
  BODY_TURN_ATLAS_LAYOUT,
  BODY_TURN_PATCH_LAYOUTS,
  HEAD_TURN_ATLAS_LAYOUT,
  HEAD_TURN_PATCH_LAYOUTS,
  LAYERED_ASSET_COUNT,
  LAYERED_ASSET_URLS,
  MOUTH_MICRO_BOUNDS,
  MOUTH_VOWEL_BOUNDS,
  SIDE_EXPRESSION_ROIS,
} from "../src/data/layered-assets.js";

test("v14 keeps the front face rig and uses lossless corrected eye atlases", () => {
  assert.equal(LAYERED_ASSET_COUNT, 39);
  assert.match(
    LAYERED_ASSET_URLS.frontBase,
    /character-v14\/master\/front-faceless-v1\.png$/,
  );
  assert.match(
    LAYERED_ASSET_URLS.eyeOpen,
    /character-v14\/parts\/aligned-v1\/eye_base_open\.png$/,
  );
  assert.match(
    LAYERED_ASSET_URLS.irises,
    /character-v14\/parts\/aligned-v1\/irises\.png$/,
  );
  assert.match(
    LAYERED_ASSET_URLS.eyesHalf,
    /character-v14\/parts\/aligned-v1\/eyes_half_closed\.png$/,
  );

  for (const [key, filename] of Object.entries({
    mouthA: "mouth_vowel_a.png",
    mouthI: "mouth_vowel_i.png",
    mouthU: "mouth_vowel_u.png",
    mouthE: "mouth_vowel_e.png",
    mouthO: "mouth_vowel_o.png",
  })) {
    assert.match(
      LAYERED_ASSET_URLS[key],
      new RegExp(`character-v14/parts/aligned-v1/${filename}$`),
    );
  }

  assert.match(
    LAYERED_ASSET_URLS.mouthMicro,
    /character-v14\/parts\/aligned-v1\/mouth_open_micro\.png$/,
  );
  assert.deepEqual(MOUTH_MICRO_BOUNDS, [516, 596, 578, 614]);
  assert.deepEqual(MOUTH_VOWEL_BOUNDS.i, [521, 598, 573, 613]);
  assert.ok(
    MOUTH_VOWEL_BOUNDS.i[2] - MOUTH_VOWEL_BOUNDS.i[0] <
      MOUTH_VOWEL_BOUNDS.e[2] - MOUTH_VOWEL_BOUNDS.e[0],
    "I / い should be narrower than E / え",
  );

  for (const removedLargePart of [
    "hairBack",
    "armR",
    "armL",
    "body",
    "face",
    "hairFront",
    "earringR",
    "earringL",
    "accessoryHead",
  ]) {
    assert.equal(
      removedLargePart in LAYERED_ASSET_URLS,
      false,
      `${removedLargePart} must not be composited over the coherent base`,
    );
  }

  for (const url of Object.values(LAYERED_ASSET_URLS)) {
    assert.equal(existsSync(fileURLToPath(url)), true, `missing asset: ${url}`);
  }

  assert.deepEqual(HEAD_TURN_ATLAS_LAYOUT, {
    frameWidth: 768,
    frameHeight: 1024,
    displayWidth: 1086,
    displayHeight: 1448,
    columns: 4,
    rows: 4,
    frameCount: 16,
  });
  assert.deepEqual(HEAD_TURN_PATCH_LAYOUTS, {
    left: {
      blink: { frameWidth: 276, frameHeight: 99, trim: [320, 400, 710, 540] },
      mouthSmall: { frameWidth: 141, frameHeight: 64, trim: [400, 550, 600, 640] },
      eyeBase: { frameWidth: 276, frameHeight: 99, trim: [320, 400, 710, 540] },
      irises: { frameWidth: 276, frameHeight: 99, trim: [320, 400, 710, 540] },
      eyeLine: { frameWidth: 276, frameHeight: 99, trim: [320, 400, 710, 540] },
    },
    right: {
      blink: { frameWidth: 276, frameHeight: 99, trim: [390, 400, 780, 540] },
      mouthSmall: { frameWidth: 148, frameHeight: 67, trim: [500, 550, 710, 645] },
      eyeBase: { frameWidth: 276, frameHeight: 99, trim: [390, 400, 780, 540] },
      irises: { frameWidth: 276, frameHeight: 99, trim: [390, 400, 780, 540] },
      eyeLine: { frameWidth: 276, frameHeight: 99, trim: [390, 400, 780, 540] },
    },
  });
  for (const direction of ["Left", "Right"]) {
    for (const state of ["Neutral", "Blink", "MouthSmall", "EyeBase", "Irises", "EyeLine"]) {
      const key = `headTurn${direction}${state}Atlas`;
      const extension = ["EyeBase", "Irises", "EyeLine"].includes(state)
        ? "png"
        : "webp";
      assert.match(
        LAYERED_ASSET_URLS[key],
        new RegExp(`character-v14/neck-atlases/${direction.toLowerCase()}-${state
          .replaceAll(/([a-z])([A-Z])/g, "$1-$2")
          .toLowerCase()}-v1\\.${extension}$`),
      );
    }
  }

  assert.deepEqual(BODY_TURN_ATLAS_LAYOUT, HEAD_TURN_ATLAS_LAYOUT);
  assert.deepEqual(BODY_TURN_PATCH_LAYOUTS, HEAD_TURN_PATCH_LAYOUTS);
  for (const direction of ["Left", "Right"]) {
    for (const state of ["Neutral", "Blink", "MouthSmall", "EyeBase", "Irises", "EyeLine"]) {
      const key = `bodyTurn${direction}${state}Atlas`;
      const extension = ["EyeBase", "Irises", "EyeLine"].includes(state)
        ? "png"
        : "webp";
      assert.match(
        LAYERED_ASSET_URLS[key],
        new RegExp(`character-v14/body-atlases/${direction.toLowerCase()}-${state
          .replaceAll(/([a-z])([A-Z])/g, "$1-$2")
          .toLowerCase()}-v1\\.${extension}$`),
      );
    }
  }

  for (const removedSideAsset of [
    "poseNaturalLeft",
    "poseNaturalLeftBlink",
    "poseNaturalLeftMouthSmall",
    "poseNaturalLeftBlinkMouthSmall",
    "poseNaturalRight",
    "poseNaturalRightBlink",
    "poseNaturalRightMouthSmall",
    "poseNaturalRightBlinkMouthSmall",
    "poseRightStep25",
    "poseRightStep25Blink",
    "poseRightStep25MouthSmall",
    "poseRightStep25BlinkMouthSmall",
    "poseRightStep50",
    "poseRightStep50Blink",
    "poseRightStep50MouthSmall",
    "poseRightStep50BlinkMouthSmall",
    "poseRightStep80",
    "poseRightStep80Blink",
    "poseRightStep80MouthSmall",
    "poseRightStep80BlinkMouthSmall",
    "poseLeftBlink",
    "poseLeftMouthSmall",
    "poseLeftBlinkMouthSmall",
    "poseRightBlink",
    "poseRightMouthSmall",
    "poseRightBlinkMouthSmall",
  ]) {
    assert.equal(
      removedSideAsset in LAYERED_ASSET_URLS,
      false,
      `${removedSideAsset} must not be loaded with the core atlas rig`,
    );
  }
});

test("v14 face rig keeps gaze bounds and legacy expression ROI metadata", () => {
  assert.deepEqual(FACE_LAYOUT.irisAnchor, { x: 543, y: 478 });
  assert.deepEqual(FACE_LAYOUT.gazeRange, { x: 12, y: 7 });
  assert.deepEqual(FACE_LAYOUT.browAnchor, { x: 543, y: 407 });
  assert.deepEqual(FACE_LAYOUT.eyeMasks, [
    { x: 443, y: 477, radiusX: 55, radiusY: 31 },
    { x: 643, y: 477, radiusX: 55, radiusY: 31 },
  ]);
  assert.deepEqual(SIDE_EXPRESSION_ROIS, {
    rightStep25: [
      [406, 417, 735, 529],
      [527, 565, 631, 636],
    ],
    rightStep50: [
      [443, 414, 754, 527],
      [568, 566, 663, 632],
    ],
    naturalLeft: [
      [330, 412, 620, 526],
      [414, 560, 500, 620],
    ],
    naturalRight: [
      [474, 412, 770, 526],
      [604, 566, 690, 628],
    ],
    rightStep80: [
      [467, 406, 766, 527],
      [607, 571, 695, 628],
    ],
    left: [
      [312, 402, 620, 527],
      [392, 570, 469, 620],
    ],
    right: [
      [462, 402, 763, 527],
      [610, 575, 699, 628],
    ],
  });
});
