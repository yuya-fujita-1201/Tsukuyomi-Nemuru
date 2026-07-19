import assert from "node:assert/strict";
import test from "node:test";

import {
  DEFAULT_POSE,
  addPose,
  blendPose,
  normalizePose,
} from "../src/rig/pose.js";

test("normalizePose fills defaults and clamps every public input", () => {
  const pose = normalizePose({
    headX: 7,
    headY: -4,
    headTurn: 6,
    headTilt: 2,
    blink: -1,
    gazeX: -3,
    gazeY: 4,
    mouthOpen: 9,
    smile: -2,
    breath: 8,
    shoulderSway: -8,
    handAccent: 5,
    bookBob: -5,
    hairSway: 5,
    speech: 3,
    turn: -7,
  });

  assert.deepEqual(pose, {
    headX: 1,
    headY: -1,
    headTurn: 1,
    headTilt: 1,
    blink: 0,
    gazeX: -1,
    gazeY: 1,
    mouthOpen: 1,
    smile: -1,
    breath: 1,
    shoulderSway: -1,
    handAccent: 1,
    bookBob: -1,
    hairSway: 1,
    speech: 1,
    turn: -1,
  });
});

test("normalizePose ignores non-finite values", () => {
  const pose = normalizePose({
    headX: Number.NaN,
    blink: Number.POSITIVE_INFINITY,
  });

  assert.equal(pose.headX, DEFAULT_POSE.headX);
  assert.equal(pose.blink, DEFAULT_POSE.blink);
});

test("blendPose interpolates and remains within pose limits", () => {
  const result = blendPose(
    { headX: -1, blink: 0, smile: -1 },
    { headX: 1, blink: 1, smile: 1 },
    0.25,
  );

  assert.equal(result.headX, -0.5);
  assert.equal(result.blink, 0.25);
  assert.equal(result.smile, -0.5);
});

test("blendPose and addPose tolerate invalid additions without escaping limits", () => {
  const unchanged = blendPose({ headX: -1 }, { headX: 1 }, Number.NaN);
  const added = addPose(
    { headX: 0.8, breath: 0.4 },
    { headX: 0.5, breath: Number.NaN, handAccent: -0.25 },
  );

  assert.equal(unchanged.headX, -1);
  assert.equal(added.headX, 1);
  assert.equal(added.breath, 0.4);
  assert.equal(added.handAccent, -0.25);
});
