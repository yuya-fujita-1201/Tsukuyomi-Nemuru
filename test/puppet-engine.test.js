import assert from "node:assert/strict";
import test from "node:test";

import { PuppetEngine } from "../src/rig/puppet-engine.js";
import { createTurnTransitionState } from "../src/rig/layered-motion.js";

test("turn variant changes recenter before applying and restore the latest manual target", () => {
  const engine = new PuppetEngine({}, {});
  engine.currentTurn = 0.8;
  engine.setManualPose({ turn: 0.8 });

  assert.equal(engine.setTurnVariant("soft"), "full");
  assert.equal(engine.turnVariant, "full");
  assert.equal(engine.pendingTurnVariant, "soft");
  assert.equal(engine.pendingTurnTarget, 0.8);

  engine.setManualPose({ turn: -0.65 });
  assert.equal(engine.pendingTurnTarget, -0.65);

  let previousMagnitude = Math.abs(engine.currentTurn);
  let switchedAt = null;
  for (let frame = 0; frame < 240; frame += 1) {
    const activeBefore = engine.turnVariant;
    engine.advanceTurnTransition(1 / 60);

    if (activeBefore === "full" && engine.turnVariant === "full") {
      assert.ok(Math.abs(engine.currentTurn) <= previousMagnitude);
      previousMagnitude = Math.abs(engine.currentTurn);
    }
    if (activeBefore === "full" && engine.turnVariant === "soft") {
      switchedAt = engine.currentTurn;
      break;
    }
  }

  assert.equal(switchedAt, 0);
  assert.equal(engine.pendingTurnVariant, null);
  assert.equal(engine.targetPose.turn, -0.65);

  engine.advanceTurnTransition(1 / 60);
  assert.ok(engine.currentTurn < 0);
});

test("a newer requested variant replaces the pending variant without skipping center", () => {
  const engine = new PuppetEngine({}, {});
  engine.currentTurn = -0.7;
  engine.setManualPose({ turn: -0.7 });

  engine.setTurnVariant("soft");
  engine.setTurnVariant("head-only");

  assert.equal(engine.turnVariant, "full");
  assert.equal(engine.pendingTurnVariant, "head-only");

  for (let frame = 0; frame < 240 && engine.pendingTurnVariant; frame += 1) {
    engine.advanceTurnTransition(1 / 60);
  }

  assert.equal(engine.turnVariant, "head-only");
  assert.equal(engine.currentTurn, 0);
});

test("turn variant changes apply immediately when the avatar is already centered", () => {
  const engine = new PuppetEngine({}, {});

  assert.equal(engine.setTurnVariant("soft"), "soft");
  assert.equal(engine.turnVariant, "soft");
  assert.equal(engine.pendingTurnVariant, null);
  assert.equal(engine.currentTurn, 0);
});

test("an atlas side pose recenters without a forced blink before mode change", () => {
  const engine = new PuppetEngine({}, {});
  engine.currentTurn = 1;
  engine.turnTransitionState = createTurnTransitionState("right");
  engine.setManualPose({ turn: 1 });
  engine.setTurnVariant("head-only");

  let sawForcedBlink = false;
  for (let frame = 0; frame < 360 && engine.pendingTurnVariant; frame += 1) {
    engine.advanceTurnTransition(1 / 60);
    if (
      engine.turnTransitionState.didSwap &&
      engine.turnTransitionState.displayPose === "front"
    ) {
      sawForcedBlink = engine.turnTransitionState.blink > 0;
    }
    if (engine.turnVariant === "head-only") {
      assert.equal(engine.turnTransitionState.displayPose, "front");
      assert.equal(engine.turnTransitionState.phase, "idle");
      assert.equal(engine.currentTurn, 0);
    }
  }

  assert.equal(sawForcedBlink, false);
  assert.equal(engine.turnVariant, "head-only");
  assert.equal(engine.pendingTurnVariant, null);
  assert.equal(engine.targetPose.turn, 1);
});

test("parameter mode responds to neck input without the old long lag", () => {
  const engine = new PuppetEngine({}, {});
  engine.setTurnVariant("parameter");
  engine.setManualPose({ headTurn: 1, turn: 0 });

  for (let frame = 0; frame < 12; frame += 1) {
    engine.advanceTurnTransition(1 / 60);
  }
  assert.equal(engine.turnTransitionState.displayPose, "front");
  assert.equal(engine.turnTransitionState.phase, "idle");
  assert.ok(engine.currentHeadTurn > 0.9);
});

test("parameter body turn stays continuous and does not start cut transitions", () => {
  const engine = new PuppetEngine({}, {});
  engine.setTurnVariant("parameter");
  engine.setManualPose({ headTurn: 0, turn: 1 });

  for (let frame = 0; frame < 24; frame += 1) {
    engine.advanceTurnTransition(1 / 60);
  }
  assert.equal(engine.turnTransitionState.displayPose, "front");
  assert.equal(engine.turnTransitionState.phase, "idle");
  assert.ok(engine.currentTurn > 0.94);
});

test("parameter body turn no longer visits discrete completed-cut states", () => {
  const engine = new PuppetEngine({}, {});
  engine.setTurnVariant("parameter");
  engine.setManualPose({ headTurn: 0, turn: 1 });
  const swaps = [];

  for (let frame = 0; frame < 720; frame += 1) {
    engine.advanceTurnTransition(1 / 60);
    if (engine.turnTransitionState.didSwap) {
      swaps.push(engine.turnTransitionState.displayPose);
    }
    if (
      engine.turnTransitionState.displayPose === "right" &&
      engine.turnTransitionState.phase === "idle"
    ) {
      break;
    }
  }

  assert.deepEqual(swaps, []);
  assert.equal(engine.turnTransitionState.displayPose, "front");
});

test("parameter turns lock after settling and unlock as soon as the target moves", () => {
  const engine = new PuppetEngine({}, {});
  engine.setTurnVariant("parameter");
  engine.setManualPose({ headTurn: 0, turn: -0.62 });

  for (let frame = 0; frame < 180; frame += 1) {
    engine.advanceTurnTransition(1 / 60);
  }
  assert.equal(engine.bodyTurnSettleState.settled, true);
  assert.equal(engine.headTurnSettleState.settled, true);

  engine.setManualPose({ turn: 0.4 });
  engine.advanceTurnTransition(1 / 60);
  assert.equal(engine.bodyTurnSettleState.settled, false);
});
