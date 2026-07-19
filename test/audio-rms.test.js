import assert from "node:assert/strict";
import test from "node:test";

import {
  AudioRmsController,
  calculateRms,
  normalizeRms,
} from "../src/audio/audio-rms.js";

test("calculateRms returns zero for silence and the expected energy for a waveform", () => {
  assert.equal(calculateRms(new Float32Array([0, 0, 0, 0])), 0);
  assert.equal(calculateRms(new Float32Array([1, -1, 1, -1])), 1);
});

test("normalizeRms removes the noise floor and clamps loud audio", () => {
  assert.equal(normalizeRms(0), 0);
  assert.equal(normalizeRms(0.012), 0);
  assert.ok(normalizeRms(0.08) > 0);
  assert.equal(normalizeRms(1), 1);
});

test("AudioRmsController plays, pauses, and toggles an attached audio element", async () => {
  const controller = new AudioRmsController();
  assert.equal(await controller.play(), false);

  let resumeCount = 0;
  let playCount = 0;
  let pauseCount = 0;
  controller.context = {
    resume: async () => {
      resumeCount += 1;
    },
  };
  controller.audio = {
    paused: true,
    play: async () => {
      playCount += 1;
      controller.audio.paused = false;
    },
    pause: () => {
      pauseCount += 1;
      controller.audio.paused = true;
    },
  };

  assert.equal(await controller.play(), true);
  assert.equal(controller.isPlaying, true);
  controller.pause();
  assert.equal(controller.isPlaying, false);
  await controller.toggle();
  assert.equal(controller.isPlaying, true);
  await controller.toggle();
  assert.equal(controller.isPlaying, false);
  assert.equal(resumeCount, 2);
  assert.equal(playCount, 2);
  assert.equal(pauseCount, 2);
});

test("AudioRmsController smooths analyser samples and decays when paused", () => {
  const controller = new AudioRmsController();
  controller.smoothedLevel = 0.5;
  assert.equal(controller.getLevel(), 0.36);

  controller.audio = { paused: false };
  controller.samples = new Float32Array(8);
  controller.analyser = {
    getFloatTimeDomainData: (samples) => samples.fill(0.2),
  };
  const activeLevel = controller.getLevel();
  assert.ok(activeLevel > 0.36);
  assert.ok(activeLevel <= 1);

  controller.audio.paused = true;
  assert.ok(controller.getLevel() < activeLevel);
});

test("AudioRmsController disconnects browser resources during destroy", () => {
  const controller = new AudioRmsController();
  const calls = [];
  controller.audio = {
    paused: false,
    pause: () => calls.push("pause"),
  };
  controller.source = {
    disconnect: () => calls.push("source"),
  };
  controller.analyser = {
    disconnect: () => calls.push("analyser"),
  };
  controller.context = {
    close: () => calls.push("context"),
  };
  controller.samples = new Float32Array(4);
  controller.smoothedLevel = 0.4;

  controller.destroy();

  assert.deepEqual(calls, ["pause", "source", "analyser", "context"]);
  assert.equal(controller.audio, null);
  assert.equal(controller.context, null);
  assert.equal(controller.smoothedLevel, 0);
});
