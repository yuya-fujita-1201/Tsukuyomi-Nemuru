import assert from "node:assert/strict";
import test from "node:test";

import {
  createGrid,
  deformGrid,
  findNearestVertex,
} from "../src/rig/deform.js";
import { normalizePose } from "../src/rig/pose.js";

const WIDTH = 1086;
const HEIGHT = 1448;
const grid = createGrid(WIDTH, HEIGHT, 49, 65);

test("createGrid builds matching positions, UVs, and triangle indices", () => {
  assert.equal(grid.positions.length, 49 * 65 * 2);
  assert.equal(grid.uvs.length, grid.positions.length);
  assert.equal(grid.indices.length, (49 - 1) * (65 - 1) * 6);
  assert.deepEqual(Array.from(grid.positions.slice(0, 2)), [0, 0]);
  assert.deepEqual(Array.from(grid.uvs.slice(-2)), [1, 1]);
});

test("grid helpers reject impossible dimensions and mismatched position data", () => {
  assert.throws(() => createGrid(WIDTH, HEIGHT, 1, 65), /at least 2/i);
  assert.throws(
    () =>
      deformGrid(
        new Float32Array(4),
        49,
        65,
        WIDTH,
        HEIGHT,
        normalizePose(),
      ),
    /does not match/i,
  );
});

test("deformGrid never mutates its base geometry", () => {
  const before = grid.positions.slice();
  deformGrid(
    grid.positions,
    49,
    65,
    WIDTH,
    HEIGHT,
    normalizePose({ headX: 1, blink: 1, mouthOpen: 1 }),
    1.5,
  );

  assert.deepEqual(grid.positions, before);
});

test("outer corners stay pinned while the character moves", () => {
  const deformed = deformGrid(
    grid.positions,
    49,
    65,
    WIDTH,
    HEIGHT,
    normalizePose({
      headX: 1,
      headTilt: 1,
      breath: 1,
      handAccent: 1,
      hairSway: 1,
    }),
    2,
  );

  const cornerIndices = [0, 48, 49 * 64, 49 * 65 - 1];
  for (const index of cornerIndices) {
    assert.equal(deformed[index * 2], grid.positions[index * 2]);
    assert.equal(deformed[index * 2 + 1], grid.positions[index * 2 + 1]);
  }
});

test("blink compresses both eye regions toward their center lines", () => {
  const open = deformGrid(
    grid.positions,
    49,
    65,
    WIDTH,
    HEIGHT,
    normalizePose({ blink: 0 }),
    0,
  );
  const closed = deformGrid(
    grid.positions,
    49,
    65,
    WIDTH,
    HEIGHT,
    normalizePose({ blink: 1 }),
    0,
  );

  const upperEye = findNearestVertex(grid.positions, 49, 65, 458, 370);
  const openDistance = Math.abs(open[upperEye * 2 + 1] - 391);
  const closedDistance = Math.abs(closed[upperEye * 2 + 1] - 391);

  assert.ok(closedDistance < openDistance);
});

test("hand accent is local and moves the raised screen-left hand more than the book", () => {
  const neutral = deformGrid(
    grid.positions,
    49,
    65,
    WIDTH,
    HEIGHT,
    normalizePose(),
    0,
  );
  const accented = deformGrid(
    grid.positions,
    49,
    65,
    WIDTH,
    HEIGHT,
    normalizePose({ handAccent: 1 }),
    0,
  );

  const raisedHand = findNearestVertex(grid.positions, 49, 65, 135, 760);
  const book = findNearestVertex(grid.positions, 49, 65, 510, 835);
  const raisedDelta = Math.hypot(
    accented[raisedHand * 2] - neutral[raisedHand * 2],
    accented[raisedHand * 2 + 1] - neutral[raisedHand * 2 + 1],
  );
  const bookDelta = Math.hypot(
    accented[book * 2] - neutral[book * 2],
    accented[book * 2 + 1] - neutral[book * 2 + 1],
  );

  assert.ok(raisedDelta > bookDelta * 2);
});

test("head-only deformation can lock the torso while moving the head", () => {
  const locked = deformGrid(
    grid.positions,
    49,
    65,
    WIDTH,
    HEIGHT,
    normalizePose({ headX: 1, headTilt: 0.12 }),
    0,
    { lockBody: true },
  );
  const head = findNearestVertex(grid.positions, 49, 65, 532, 369);
  const torso = findNearestVertex(grid.positions, 49, 65, 532, 885);
  const headDelta = Math.hypot(
    locked[head * 2] - grid.positions[head * 2],
    locked[head * 2 + 1] - grid.positions[head * 2 + 1],
  );
  const torsoDelta = Math.hypot(
    locked[torso * 2] - grid.positions[torso * 2],
    locked[torso * 2 + 1] - grid.positions[torso * 2 + 1],
  );

  assert.ok(headDelta > 4);
  assert.ok(torsoDelta < 0.25);
});

test("neck turning moves both long-hair regions while a locked torso stays still", () => {
  const neutral = deformGrid(
    grid.positions,
    49,
    65,
    WIDTH,
    HEIGHT,
    normalizePose(),
    0,
    { lockBody: true },
  );
  const turned = deformGrid(
    grid.positions,
    49,
    65,
    WIDTH,
    HEIGHT,
    normalizePose({ headTurn: 1 }),
    0,
    { lockBody: true },
  );
  const leftHair = findNearestVertex(grid.positions, 49, 65, 250, 820);
  const rightHair = findNearestVertex(grid.positions, 49, 65, 790, 820);
  const torso = findNearestVertex(grid.positions, 49, 65, 532, 885);
  const delta = (index) => Math.hypot(
    turned[index * 2] - neutral[index * 2],
    turned[index * 2 + 1] - neutral[index * 2 + 1],
  );

  assert.ok(delta(leftHair) > 3.5);
  assert.ok(delta(rightHair) > 3.5);
  assert.ok(delta(torso) < 0.25);
});

test("runtime can hold hair deformation so manual trim cannot pull the body", () => {
  const neutral = deformGrid(
    grid.positions,
    49,
    65,
    WIDTH,
    HEIGHT,
    normalizePose(),
    0,
    { deformHair: false },
  );
  const corrected = deformGrid(
    grid.positions,
    49,
    65,
    WIDTH,
    HEIGHT,
    normalizePose({ hairSway: 1, headTurn: 1 }),
    0,
    { deformHair: false },
  );

  assert.deepEqual(corrected, neutral);
});

test("parameter body turn changes the shoulder line without forcing the neck", () => {
  const neutral = deformGrid(
    grid.positions,
    49,
    65,
    WIDTH,
    HEIGHT,
    normalizePose(),
    0,
  );
  const turned = deformGrid(
    grid.positions,
    49,
    65,
    WIDTH,
    HEIGHT,
    normalizePose({ turn: 1, headTurn: 0 }),
    0,
  );
  const leftShoulder = findNearestVertex(grid.positions, 49, 65, 315, 695);
  const rightShoulder = findNearestVertex(grid.positions, 49, 65, 750, 665);
  const headCenter = findNearestVertex(grid.positions, 49, 65, 532, 369);

  const leftDy = turned[leftShoulder * 2 + 1] - neutral[leftShoulder * 2 + 1];
  const rightDy = turned[rightShoulder * 2 + 1] - neutral[rightShoulder * 2 + 1];
  const headDx = turned[headCenter * 2] - neutral[headCenter * 2];

  assert.ok(leftDy * rightDy < 0);
  assert.ok(Math.abs(leftDy - rightDy) > 3);
  assert.ok(Math.abs(headDx) < 2);
});
