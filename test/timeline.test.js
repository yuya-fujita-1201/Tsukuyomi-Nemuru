import assert from "node:assert/strict";
import test from "node:test";

import {
  normalizeDirectorScript,
  poseForCue,
  sampleDirectorScript,
} from "../src/rig/timeline.js";

test("normalizeDirectorScript sorts valid cues and supplies safe defaults", () => {
  const script = normalizeDirectorScript({
    version: 1,
    title: "test",
    cues: [
      { at: 4, duration: 2, emotion: "sleepy" },
      {
        at: 0,
        duration: 3,
        emotion: "gentle",
        speech: 0.8,
        look: [0.4, -0.2],
        gesture: "present",
        turn: -0.6,
      },
    ],
  });

  assert.equal(script.cues[0].at, 0);
  assert.equal(script.cues[0].speech, 0.8);
  assert.deepEqual(script.cues[0].look, [0.4, -0.2]);
  assert.equal(script.cues[0].turn, -0.6);
  assert.equal(script.cues[1].speech, 0);
  assert.equal(script.duration, 6);
});

test("normalizeDirectorScript rejects malformed or overlapping cues", () => {
  assert.throws(() => normalizeDirectorScript(null), /must be an object/i);
  assert.throws(
    () => normalizeDirectorScript({ version: 2, cues: [{}] }),
    /version must be 1/i,
  );
  assert.throws(
    () => normalizeDirectorScript({ version: 1, cues: [] }),
    /at least one cue/i,
  );
  assert.throws(
    () =>
      normalizeDirectorScript({
        version: 1,
        cues: [
          { at: 0, duration: 3 },
          { at: 2.5, duration: 1 },
        ],
    }),
    /overlap/i,
  );
});

test("normalizeDirectorScript rejects invalid cue fields", () => {
  const invalidCues = [
    [null, /must be an object/i],
    [{ at: -1, duration: 1 }, /invalid at/i],
    [{ at: 0, duration: 0 }, /invalid duration/i],
    [{ at: 0, duration: 1, emotion: "angry" }, /unknown emotion/i],
    [{ at: 0, duration: 1, gesture: "wave" }, /unknown gesture/i],
  ];

  for (const [cue, pattern] of invalidCues) {
    assert.throws(
      () => normalizeDirectorScript({ version: 1, cues: [cue] }),
      pattern,
    );
  }
});

test("normalizeDirectorScript clamps loose AI values and repairs malformed look", () => {
  const script = normalizeDirectorScript({
    version: 1,
    cues: [
      {
        at: 0,
        duration: 1,
        speech: 4,
        emphasis: -2,
        look: ["bad", 4],
        turn: 9,
      },
    ],
  });

  assert.equal(script.title, "Untitled performance");
  assert.equal(script.cues[0].speech, 1);
  assert.equal(script.cues[0].emphasis, 0);
  assert.deepEqual(script.cues[0].look, [0, 1]);
  assert.equal(script.cues[0].turn, 1);
});

test("poseForCue maps semantic AI direction to bounded rig controls", () => {
  const pose = poseForCue({
    emotion: "gentle",
    speech: 0.75,
    look: [0.5, -0.5],
    gesture: "present",
    emphasis: 0.8,
    turn: -0.5,
  });

  assert.equal(pose.gazeX, 0.5);
  assert.equal(pose.gazeY, -0.5);
  assert.equal(pose.speech, 0.75);
  assert.ok(pose.smile > 0.25);
  assert.ok(pose.handAccent > 0.5);
  assert.equal(pose.turn, -0.5);
  assert.equal(pose.headTurn, -0.36);
});

test("sampleDirectorScript transitions between cues without discontinuity", () => {
  const script = normalizeDirectorScript({
    version: 1,
    cues: [
      { at: 0, duration: 2, emotion: "calm", speech: 0.2 },
      {
        at: 2,
        duration: 2,
        emotion: "surprised",
        speech: 0.9,
        gesture: "nod",
      },
    ],
  });

  const before = sampleDirectorScript(script, 1.99);
  const during = sampleDirectorScript(script, 2.1);
  const after = sampleDirectorScript(script, 2.5);

  assert.ok(during.mouthOpen >= before.mouthOpen);
  assert.ok(during.mouthOpen <= after.mouthOpen);
  assert.ok(after.speech > before.speech);
});

test("sampleDirectorScript accepts a raw script and clamps times outside its duration", () => {
  const raw = {
    version: 1,
    cues: [{ at: 1, duration: 2, emotion: "calm", speech: 0.3 }],
  };

  assert.equal(sampleDirectorScript(raw, -10).speech, 0.3);
  assert.equal(sampleDirectorScript(raw, 99).speech, 0.3);
});
