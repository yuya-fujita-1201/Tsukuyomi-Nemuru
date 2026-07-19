import assert from "node:assert/strict";
import test from "node:test";

import {
  advanceTurnSettleState,
  advanceTurnTransitionState,
  BODY_TURN_FRAME_COUNT,
  computeLayerTransforms,
  createTurnSettleState,
  createTurnTransitionState,
  resolveGazeOffset,
  resolveSideGazeOffset,
  resolveSideGazeLayerAlpha,
  resolveHairFollow,
  resolveParameterCutPose,
  resolveTurnBridgeVisuals,
  resolveHeadOnlyOffsets,
  resolveMouthOpen,
  resolveRequestedTurnPose,
  resolveSideBlinkBlend,
  resolveSideMouthBlend,
  selectHeadTurnFrameBlend,
  selectBodyTurnFrameBlend,
  resolveTurnWipeBoundary,
  selectMouthWeights,
  selectFrontMouthWeights,
  selectFrontBlinkWeights,
  selectSideExpressionAlphas,
  selectSideExpressionWeights,
  selectTurnPoseWeights,
  selectTurnTransitionPoseWeights,
  selectTurnWeights,
} from "../src/rig/layered-motion.js";

function approximatelyEqual(actual, expected, epsilon = 1e-9) {
  assert.ok(
    Math.abs(actual - expected) <= epsilon,
    `expected ${actual} to be within ${epsilon} of ${expected}`,
  );
}

function turnWeights(active, value = 1) {
  return {
    front: 0,
    rightStep25: 0,
    rightStep50: 0,
    naturalLeft: 0,
    naturalRight: 0,
    rightStep80: 0,
    left: 0,
    right: 0,
    [active]: value,
  };
}

test("selectMouthWeights uses a micro opening between closed and small without changing total opacity", () => {
  assert.deepEqual(selectMouthWeights(0), {
    closed: 1,
    micro: 0,
    small: 0,
    wide: 0,
  });
  assert.deepEqual(selectMouthWeights(1), {
    closed: 0,
    micro: 0,
    small: 0,
    wide: 1,
  });

  assert.ok(selectMouthWeights(0.14).micro > 0.5);
  assert.ok(selectMouthWeights(0.28).small > selectMouthWeights(0.28).micro);

  for (const value of [0.04, 0.08, 0.14, 0.2, 0.28, 0.45, 0.65, 0.84]) {
    const weights = selectMouthWeights(value);
    approximatelyEqual(
      weights.closed + weights.micro + weights.small + weights.wide,
      1,
    );
    assert.ok(Object.values(weights).every((weight) => weight >= 0));
    assert.ok(Object.values(weights).every((weight) => weight <= 1));
  }
});

test("head turn maps continuously across sixteen cached keyframes", () => {
  assert.deepEqual(selectHeadTurnFrameBlend(0), {
    active: false,
    direction: 0,
    lowerIndex: 0,
    upperIndex: 0,
    upperAlpha: 0,
  });
  assert.deepEqual(selectHeadTurnFrameBlend(1), {
    active: true,
    direction: 1,
    lowerIndex: 15,
    upperIndex: 15,
    upperAlpha: 0,
  });
  assert.deepEqual(selectHeadTurnFrameBlend(-1), {
    active: true,
    direction: -1,
    lowerIndex: 15,
    upperIndex: 15,
    upperAlpha: 0,
  });

  const midpoint = selectHeadTurnFrameBlend(0.5);
  assert.equal(midpoint.active, true);
  assert.equal(midpoint.direction, 1);
  assert.equal(midpoint.lowerIndex, 7);
  assert.equal(midpoint.upperIndex, 8);
  approximatelyEqual(midpoint.upperAlpha, 0.5);

  let previousPosition = -1;
  for (let step = 0; step <= 100; step += 1) {
    const blend = selectHeadTurnFrameBlend(step / 100);
    const position = blend.lowerIndex + blend.upperAlpha;
    assert.ok(position >= previousPosition);
    previousPosition = position;
  }
});

test("turn atlases keep the approved front art inside the center dead zone", () => {
  for (const selectFrameBlend of [
    selectHeadTurnFrameBlend,
    selectBodyTurnFrameBlend,
  ]) {
    for (const value of [-0.035, -0.01, -0.0001, 0, 0.0001, 0.01, 0.035]) {
      assert.equal(
        selectFrameBlend(value).active,
        false,
        `${value} must keep the direct front layers`,
      );
    }
    assert.equal(selectFrameBlend(-0.036).active, true);
    assert.equal(selectFrameBlend(0.036).active, true);
  }
});

test("body turn maps continuously across sixteen cached keyframes", () => {
  assert.equal(BODY_TURN_FRAME_COUNT, 16);
  assert.deepEqual(selectBodyTurnFrameBlend(0), {
    active: false,
    direction: 0,
    lowerIndex: 0,
    upperIndex: 0,
    upperAlpha: 0,
  });
  assert.deepEqual(selectBodyTurnFrameBlend(1), {
    active: true,
    direction: 1,
    lowerIndex: 15,
    upperIndex: 15,
    upperAlpha: 0,
  });
  assert.deepEqual(selectBodyTurnFrameBlend(-1), {
    active: true,
    direction: -1,
    lowerIndex: 15,
    upperIndex: 15,
    upperAlpha: 0,
  });

  let previousPosition = -1;
  for (let step = 0; step <= 100; step += 1) {
    const blend = selectBodyTurnFrameBlend(step / 100);
    const position = blend.lowerIndex + blend.upperAlpha;
    assert.ok(position >= previousPosition);
    previousPosition = position;
  }
});

test("a stopped turn collapses adjacent-frame blending to one cached key", () => {
  const movingBody = selectBodyTurnFrameBlend(-0.62);
  assert.equal(movingBody.lowerIndex, 9);
  assert.equal(movingBody.upperIndex, 10);
  approximatelyEqual(movingBody.upperAlpha, 0.3);

  assert.deepEqual(selectBodyTurnFrameBlend(-0.62, 16, true), {
    active: true,
    direction: -1,
    lowerIndex: 9,
    upperIndex: 9,
    upperAlpha: 0,
  });
  assert.deepEqual(selectHeadTurnFrameBlend(0.72, 16, true), {
    active: true,
    direction: 1,
    lowerIndex: 11,
    upperIndex: 11,
    upperAlpha: 0,
  });
});

test("turn settling waits for an unchanged target and unlocks on movement", () => {
  let state = createTurnSettleState(0);
  state = advanceTurnSettleState(state, -0.3, -0.62, 1 / 60);
  assert.equal(state.settled, false);
  assert.equal(state.stableFor, 0);

  for (let frame = 0; frame < 6; frame += 1) {
    state = advanceTurnSettleState(state, -0.619, -0.62, 1 / 60);
  }
  assert.equal(state.settled, true);
  assert.ok(state.stableFor >= 0.08);

  state = advanceTurnSettleState(state, -0.619, -0.4, 1 / 60);
  assert.equal(state.settled, false);
  assert.equal(state.stableFor, 0);
});

test("a slowly drifting target never masquerades as a static turn", () => {
  let state = createTurnSettleState(0);
  for (let frame = 1; frame <= 30; frame += 1) {
    const target = frame * 0.0002;
    state = advanceTurnSettleState(state, target, target, 1 / 60);
    assert.equal(state.settled, false);
  }
});

test("manual vowel review selects one medium mouth without using the maximum opening", () => {
  const closed = selectFrontMouthWeights(0, "a");
  assert.equal(closed.closed, 1);
  assert.equal(closed.a, 0);

  for (const vowel of ["a", "i", "u", "e", "o"]) {
    const weights = selectFrontMouthWeights(0.5, vowel);
    approximatelyEqual(Object.values(weights).reduce((sum, value) => sum + value, 0), 1);
    assert.equal(weights[vowel], 1);
    assert.equal(weights.wide, 0);
    assert.equal(weights.small, 0);
    assert.equal(
      ["a", "i", "u", "e", "o"].filter((key) => weights[key] > 0).length,
      1,
    );
  }

  assert.deepEqual(
    selectFrontMouthWeights(0.5, "unsupported"),
    selectFrontMouthWeights(0.5, "auto"),
  );
});

test("selectTurnWeights keeps one fully opaque pose selected for every turn value", () => {
  assert.deepEqual(selectTurnWeights(0), turnWeights("front"));
  assert.deepEqual(selectTurnWeights(-1), turnWeights("left"));
  assert.deepEqual(selectTurnWeights(1), turnWeights("right"));

  assert.deepEqual(selectTurnWeights(-0.59), turnWeights("front"));
  assert.deepEqual(selectTurnWeights(-0.6), turnWeights("left"));

  for (const variant of ["parameter", "full", "natural", "soft", "head-only"] ) {
    for (let step = -100; step <= 100; step += 1) {
      const weights = selectTurnWeights(step / 100, variant);
      const values = Object.values(weights);
      assert.ok(values.every(Number.isFinite));
      assert.ok(values.every((weight) => weight >= 0 && weight <= 1));
      approximatelyEqual(Object.values(weights).reduce((sum, value) => sum + value, 0), 1);
      assert.equal(values.filter((weight) => weight === 1).length, 1);
    }
  }
});

test("turn variants preserve full 3/4 while adding natural shoulder-follow poses", () => {
  const full = selectTurnWeights(0.62, "full");
  const natural = selectTurnWeights(0.62, "natural");
  const soft = selectTurnWeights(0.62, "soft");
  assert.ok(full.right > soft.right);
  assert.deepEqual(full, turnWeights("right"));
  assert.deepEqual(natural, turnWeights("naturalRight"));
  assert.deepEqual(soft, turnWeights("front"));
  assert.deepEqual(selectTurnWeights(-1, "soft"), turnWeights("front"));
  assert.deepEqual(selectTurnWeights(1, "head-only"), turnWeights("front"));
  assert.deepEqual(selectTurnWeights(1, "parameter"), turnWeights("rightStep25"));
  assert.deepEqual(selectTurnWeights(1, "unsupported"), selectTurnWeights(1));
});

test("parameter review walks the new right-side in-between frames one adjacent cut at a time", () => {
  assert.equal(resolveParameterCutPose({ headTurn: -0.45, turn: 0 }), "front");
  assert.equal(resolveParameterCutPose({ headTurn: -0.46, turn: 0 }), "natural-left");
  assert.equal(
    resolveParameterCutPose(
      { headTurn: -0.4, turn: 0 },
      "natural-left",
    ),
    "natural-left",
  );
  assert.equal(
    resolveParameterCutPose(
      { headTurn: -0.38, turn: 0 },
      "natural-left",
    ),
    "front",
  );
  assert.equal(resolveParameterCutPose({ headTurn: 1, turn: 0 }), "right-step-25");
  assert.equal(
    resolveParameterCutPose({ headTurn: 1, turn: 0 }, "right-step-25"),
    "right-step-50",
  );
  assert.equal(
    resolveParameterCutPose({ headTurn: 1, turn: 0 }, "right-step-50"),
    "natural-right",
  );
  assert.equal(
    resolveParameterCutPose({ headTurn: 1, turn: 0 }, "natural-right"),
    "natural-right",
  );

  assert.equal(resolveParameterCutPose({ headTurn: 0, turn: 1 }), "right-step-25");
  assert.equal(
    resolveParameterCutPose({ headTurn: 0, turn: 1 }, "right-step-25"),
    "right-step-50",
  );
  assert.equal(
    resolveParameterCutPose({ headTurn: 0, turn: 1 }, "right-step-50"),
    "natural-right",
  );
  assert.equal(
    resolveParameterCutPose({ headTurn: 0, turn: 1 }, "natural-right"),
    "right-step-80",
  );
  assert.equal(
    resolveParameterCutPose({ headTurn: 0, turn: 1 }, "right-step-80"),
    "right",
  );

  assert.equal(resolveParameterCutPose({ headTurn: 1, turn: -0.6 }), "left");
  assert.equal(
    resolveParameterCutPose({ headTurn: 0, turn: -0.55 }, "left"),
    "left",
  );
  assert.equal(
    resolveParameterCutPose({ headTurn: 0, turn: -0.52 }, "left"),
    "front",
  );
  assert.equal(
    resolveParameterCutPose({ headTurn: 0, turn: -1 }, "right-step-50"),
    "front",
  );
  assert.equal(
    resolveParameterCutPose(
      { headTurn: -1, turn: 0.52 },
      "right",
    ),
    "front",
  );
  assert.deepEqual(
    selectTurnPoseWeights("right-step-50", "parameter"),
    turnWeights("rightStep50"),
  );
});

test("same-direction intermediate cuts bridge directly while opposite turns return front", () => {
  const next = advanceTurnTransitionState(
    createTurnTransitionState("right-step-25"),
    { headTurn: 1, turn: 0 },
    0,
    "parameter",
  );
  assert.equal(next.targetPose, "right-step-50");
  assert.equal(next.phase, "closing");

  const opposite = advanceTurnTransitionState(
    createTurnTransitionState("right-step-50"),
    { headTurn: 0, turn: -1 },
    0,
    "parameter",
  );
  assert.equal(opposite.targetPose, "front");
});

test("parameter cut bridge exposes complementary completed rasters", () => {
  const state = {
    ...createTurnTransitionState(),
    displayPose: "front",
    targetPose: "natural-right",
    phase: "bridge",
    bridgeProgress: 0.5,
    blink: 1,
  };
  const weights = selectTurnTransitionPoseWeights(state, "parameter");
  approximatelyEqual(weights.front, 0.5);
  approximatelyEqual(weights.naturalRight, 0.5);
  approximatelyEqual(Object.values(weights).reduce((sum, value) => sum + value, 0), 1);
});

test("requested turn pose uses 0.60 enter and 0.52 exit hysteresis", () => {
  let requested = "front";
  requested = resolveRequestedTurnPose(0.59, requested);
  assert.equal(requested, "front");
  requested = resolveRequestedTurnPose(0.6, requested);
  assert.equal(requested, "right");
  requested = resolveRequestedTurnPose(0.54, requested);
  assert.equal(requested, "right");
  requested = resolveRequestedTurnPose(0.52, requested);
  assert.equal(requested, "front");

  requested = resolveRequestedTurnPose(-0.6, requested);
  assert.equal(requested, "left");
  requested = resolveRequestedTurnPose(-0.54, requested);
  assert.equal(requested, "left");
  requested = resolveRequestedTurnPose(-0.52, requested);
  assert.equal(requested, "front");
  assert.equal(resolveRequestedTurnPose(1, "right", "soft"), "front");
});

test("natural turns use an earlier 0.46 enter and 0.38 exit without replacing full 3/4", () => {
  let requested = "front";
  requested = resolveRequestedTurnPose(0.45, requested, "natural");
  assert.equal(requested, "front");
  requested = resolveRequestedTurnPose(0.46, requested, "natural");
  assert.equal(requested, "natural-right");
  requested = resolveRequestedTurnPose(0.4, requested, "natural");
  assert.equal(requested, "natural-right");
  requested = resolveRequestedTurnPose(0.38, requested, "natural");
  assert.equal(requested, "front");

  requested = resolveRequestedTurnPose(-0.46, requested, "natural");
  assert.equal(requested, "natural-left");
  assert.equal(resolveRequestedTurnPose(-1, requested, "full"), "left");
});

test("turn transition closes, wipes while closed, holds, and opens at 10, 30, and 60 fps", () => {
  for (const fps of [10, 30, 60]) {
    let state = createTurnTransitionState();
    const phases = new Set();
    const swaps = [];
    let swapFrame = null;
    let clearedFrame = null;
    let closedFramesAfterSwap = 0;
    let closedSourceFramesBeforeBridge = 0;
    const bridgeProgress = [];

    for (let frame = 0; frame < fps * 2; frame += 1) {
      const previousDisplayPose = state.displayPose;
      state = advanceTurnTransitionState(state, 1, 1 / fps, "full");
      phases.add(state.phase);
      if (state.phase === "source-hold" && state.blink === 1) {
        closedSourceFramesBeforeBridge += 1;
      }
      if (state.phase === "bridge") {
        bridgeProgress.push(state.bridgeProgress);
        assert.equal(state.blink, 1);
      }
      if (state.didSwap) {
        swapFrame = frame;
        swaps.push({
          blink: state.blink,
          from: previousDisplayPose,
          to: state.displayPose,
        });
      }
      if (swapFrame !== null && state.blink >= 0.95) {
        closedFramesAfterSwap += 1;
      }
      if (
        swapFrame !== null &&
        clearedFrame === null &&
        state.phase === "idle" &&
        state.blink === 0
      ) {
        clearedFrame = frame;
      }
    }

    assert.deepEqual([...phases].filter((phase) => phase !== "idle").sort(), [
      "bridge",
      "closing",
      "opening",
      "source-hold",
      "target-hold",
    ]);
    assert.deepEqual(swaps, [{ blink: 1, from: "front", to: "right" }]);
    assert.equal(state.phase, "idle");
    assert.equal(state.displayPose, "right");
    assert.equal(state.blink, 0);
    assert.ok(closedSourceFramesBeforeBridge >= 1);
    assert.ok(bridgeProgress.length >= 2);
    assert.equal(bridgeProgress[0], 0);
    for (let index = 1; index < bridgeProgress.length; index += 1) {
      assert.ok(bridgeProgress[index] > bridgeProgress[index - 1]);
    }
    assert.deepEqual(selectTurnPoseWeights(state.displayPose), turnWeights("right"));
    assert.ok(clearedFrame !== null);
    assert.ok((clearedFrame - swapFrame) / fps <= 0.3 + 1 / fps);
    if (fps >= 30) assert.ok(closedFramesAfterSwap >= 3);
  }
});

test("turn bridge exposes complementary poses with a head-leading curved wipe", () => {
  const state = {
    ...createTurnTransitionState(),
    displayPose: "front",
    targetPose: "right",
    phase: "bridge",
    bridgeProgress: 0.5,
    blink: 1,
  };
  const visuals = resolveTurnBridgeVisuals(state);
  assert.equal(visuals.active, true);
  assert.equal(visuals.sourcePose, "front");
  assert.equal(visuals.targetPose, "right");
  assert.equal(visuals.direction, 1);
  assert.equal(visuals.progress, 0.5);
  assert.ok(visuals.blurStrengthX > 0);

  const weights = selectTurnTransitionPoseWeights(state, "full");
  approximatelyEqual(Object.values(weights).reduce((sum, value) => sum + value, 0), 1);
  approximatelyEqual(weights.front, 0.5);
  approximatelyEqual(weights.right, 0.5);

  assert.ok(resolveTurnWipeBoundary(0, 1, 0.3) > 1);
  assert.ok(resolveTurnWipeBoundary(1, 1, 0.3) < 0);
  const centerTravel = Math.abs(
    resolveTurnWipeBoundary(0.55, 1, 0.7) -
      resolveTurnWipeBoundary(0.45, 1, 0.7),
  );
  const edgeTravel = Math.abs(
    resolveTurnWipeBoundary(0.1, 1, 0.7) -
      resolveTurnWipeBoundary(0, 1, 0.7),
  );
  assert.ok(
    centerTravel < edgeTravel * 0.6,
    "wipe should slow through the dense center and spend larger steps at its empty edges",
  );
  assert.ok(
    resolveTurnWipeBoundary(0.5, 1, 0.3) <
      resolveTurnWipeBoundary(0.5, 1, 0.82),
    "screen-right reveal should let the head lead the lower torso",
  );

  const returning = resolveTurnBridgeVisuals({
    ...state,
    displayPose: "right",
    targetPose: "front",
  });
  assert.equal(returning.direction, -1);
  assert.equal(resolveTurnBridgeVisuals(createTurnTransitionState()).active, false);
});

test("holding a turn near the swap threshold returns blink to idle", () => {
  for (const fps of [10, 30, 60]) {
    let state = createTurnTransitionState();
    for (let frame = 0; frame < fps * 2; frame += 1) {
      state = advanceTurnTransitionState(state, 0.6, 1 / fps);
    }
    assert.equal(state.displayPose, "right");
    assert.equal(state.phase, "idle");

    let extraSwaps = 0;
    for (let frame = 0; frame < fps * 8; frame += 1) {
      state = advanceTurnTransitionState(state, 0.58, 1 / fps);
      if (state.didSwap) extraSwaps += 1;
      assert.equal(state.blink, 0);
    }

    assert.equal(extraSwaps, 0);
    assert.equal(state.displayPose, "right");
    assert.equal(state.requestedPose, "right");
  }
});

test("0.54 to 0.60 jitter cannot retrigger pose swaps after entering a side", () => {
  const jitter = [0.54, 0.6, 0.56, 0.59, 0.55, 0.58];

  for (const fps of [10, 30, 60]) {
    let state = createTurnTransitionState();
    let swaps = 0;
    for (let frame = 0; frame < fps * 8; frame += 1) {
      state = advanceTurnTransitionState(
        state,
        jitter[frame % jitter.length],
        1 / fps,
      );
      if (state.didSwap) swaps += 1;
    }

    assert.equal(swaps, 1);
    assert.equal(state.displayPose, "right");
    assert.equal(state.requestedPose, "right");
    assert.equal(state.phase, "idle");
    assert.equal(state.blink, 0);
  }
});

test("opposite side requests always bridge through the front pose", () => {
  let state = createTurnTransitionState("left");
  const bridgePairs = [];
  for (let frame = 0; frame < 240; frame += 1) {
    state = advanceTurnTransitionState(state, 1, 1 / 60, "full");
    if (state.phase === "bridge") {
      const pair = `${state.displayPose}->${state.targetPose}`;
      if (bridgePairs.at(-1) !== pair) bridgePairs.push(pair);
    }
    if (
      state.displayPose === "right" &&
      state.phase === "idle" &&
      state.blink === 0
    ) break;
  }

  assert.deepEqual(bridgePairs, ["left->front", "front->right"]);
  assert.equal(state.displayPose, "right");
});

test("side expression weights independently blend blink and ASMR-small mouth states", () => {
  assert.deepEqual(selectSideExpressionWeights(0, 0), {
    neutral: 1,
    blink: 0,
    mouthSmall: 0,
    blinkMouthSmall: 0,
  });
  assert.deepEqual(selectSideExpressionWeights(1, 0), {
    neutral: 0,
    blink: 1,
    mouthSmall: 0,
    blinkMouthSmall: 0,
  });
  assert.deepEqual(selectSideExpressionWeights(0, 1), {
    neutral: 0,
    blink: 0,
    mouthSmall: 1,
    blinkMouthSmall: 0,
  });
  assert.deepEqual(selectSideExpressionWeights(1, 1), {
    neutral: 0,
    blink: 0,
    mouthSmall: 0,
    blinkMouthSmall: 1,
  });

  const mixed = selectSideExpressionWeights(0.35, 0.6);
  approximatelyEqual(Object.values(mixed).reduce((sum, value) => sum + value, 0), 1);
  assert.ok(Object.values(mixed).every((weight) => weight > 0));
});

test("front blink uses synchronized open, half, and closed keys without moving the iris", () => {
  assert.deepEqual(selectFrontBlinkWeights(0), {
    open: 1,
    half: 0,
    closed: 0,
    iris: 1,
  });
  assert.deepEqual(selectFrontBlinkWeights(0.5), {
    open: 0,
    half: 1,
    closed: 0,
    iris: 1,
  });
  assert.deepEqual(selectFrontBlinkWeights(1), {
    open: 0,
    half: 0,
    closed: 1,
    iris: 0,
  });

  for (const blink of [-1, 0.1, 0.25, 0.5, 0.75, 0.9, 2]) {
    const weights = selectFrontBlinkWeights(blink);
    approximatelyEqual(weights.open + weights.half + weights.closed, 1);
    approximatelyEqual(weights.iris, weights.open + weights.half);
    assert.ok(Object.values(weights).every((weight) => weight >= 0 && weight <= 1));
  }
});

test("side blink avoids a long double-eyelid dissolve between full-pose states", () => {
  assert.equal(resolveSideBlinkBlend(0), 0);
  assert.equal(resolveSideBlinkBlend(0.68), 0);
  assert.equal(resolveSideBlinkBlend(0.94), 1);
  assert.equal(resolveSideBlinkBlend(1), 1);
  assert.ok(resolveSideBlinkBlend(0.81) > 0);
  assert.ok(resolveSideBlinkBlend(0.81) < 1);
});

test("side expression alphas preserve logical weights under source-over compositing", () => {
  const logical = selectSideExpressionWeights(0.35, 0.6);
  const alphas = selectSideExpressionAlphas(logical);
  const order = ["neutral", "blink", "mouthSmall", "blinkMouthSmall"];
  let effectiveAlpha = 0;
  for (let index = 0; index < order.length; index += 1) {
    const key = order[index];
    const laterTransparency = order
      .slice(index + 1)
      .reduce((product, laterKey) => product * (1 - alphas[laterKey]), 1);
    approximatelyEqual(alphas[key] * laterTransparency, logical[key]);
    effectiveAlpha = alphas[key] + effectiveAlpha * (1 - alphas[key]);
  }
  approximatelyEqual(effectiveAlpha, 1);
});

test("side mouth blend follows quiet opening continuously instead of sticking open", () => {
  assert.equal(resolveSideMouthBlend(0), 0);
  assert.equal(resolveSideMouthBlend(0.2), 0.5);
  assert.equal(resolveSideMouthBlend(0.4), 1);
  assert.equal(resolveSideMouthBlend(1), 1);
});

test("head-only offsets stay subtle and mirror around the front pose", () => {
  assert.deepEqual(resolveHeadOnlyOffsets(0), { headX: 0, headTilt: 0 });
  const left = resolveHeadOnlyOffsets(-1);
  const right = resolveHeadOnlyOffsets(1);
  assert.ok(Math.abs(left.headX) <= 1);
  assert.ok(Math.abs(left.headTilt) <= 0.2);
  approximatelyEqual(left.headX, -right.headX);
  approximatelyEqual(left.headTilt, -right.headTilt);
});

test("parameter review gaze stays inside the shared elliptical eye range", () => {
  assert.deepEqual(resolveGazeOffset(0, 0), { x: 0, y: 0 });
  assert.deepEqual(resolveGazeOffset(1, 0), { x: 12, y: 0 });
  assert.deepEqual(resolveGazeOffset(0, -1), { x: 0, y: -7 });
  const corner = resolveGazeOffset(1, 1);
  approximatelyEqual((corner.x / 12) ** 2 + (corner.y / 7) ** 2, 1);
});

test("side gaze uses a compact ellipse so raster irises stay inside the lids", () => {
  assert.deepEqual(resolveSideGazeOffset(0, 0), { x: 0, y: 0 });
  assert.deepEqual(resolveSideGazeOffset(1, 0), { x: 5, y: 0 });
  assert.deepEqual(resolveSideGazeOffset(0, -1), { x: 0, y: -2 });
  const corner = resolveSideGazeOffset(1, 1);
  approximatelyEqual((corner.x / 5) ** 2 + (corner.y / 2) ** 2, 1);
});

test("side gaze layers stay fully engaged so the baked iris never cross-fades", () => {
  assert.equal(resolveSideGazeLayerAlpha(0, 0), 1);
  assert.equal(resolveSideGazeLayerAlpha(0.02, 0), 1);
  assert.equal(resolveSideGazeLayerAlpha(0.06, 0), 1);
  assert.equal(resolveSideGazeLayerAlpha(0.1, 0), 1);
  assert.equal(resolveSideGazeLayerAlpha(1, 1), 1);
});

test("hair automatically trails neck motion while retaining manual trim", () => {
  assert.equal(resolveHairFollow({}), 0);
  assert.ok(resolveHairFollow({ headTurn: 1 }) < -0.55);
  assert.ok(resolveHairFollow({ headTurn: -1 }) > 0.55);
  assert.ok(resolveHairFollow({ headTurn: 1, hairSway: 1 }) > 0);
  assert.equal(resolveHairFollow({ headTurn: -1, hairSway: 1 }), 1);
});

test("resolveMouthOpen prioritizes real audio RMS while retaining deterministic cue speech", () => {
  assert.equal(resolveMouthOpen({ mouthOpen: 0, speech: 0 }, 0, 0), 0);
  assert.equal(resolveMouthOpen({ mouthOpen: 0.2, speech: 0 }, 0, 0), 0.2);
  assert.equal(resolveMouthOpen({ mouthOpen: 0, speech: 0 }, 0, 1), 1);

  const cueDriven = resolveMouthOpen(
    { mouthOpen: 0.1, speech: 0.8 },
    0.18,
    0,
  );
  assert.ok(cueDriven > 0.1);
  assert.ok(cueDriven <= 1);
});

test("quiet playback caps automatic opening below the wide-mouth transition", () => {
  const quietLimit = 0.4;
  const audioDriven = resolveMouthOpen(
    { mouthOpen: 0, speech: 0 },
    0,
    1,
    quietLimit,
  );
  const cueDriven = resolveMouthOpen(
    { mouthOpen: 0, speech: 1 },
    0.18,
    0,
    quietLimit,
  );

  assert.equal(audioDriven, quietLimit);
  assert.ok(cueDriven <= quietLimit);
  assert.equal(selectMouthWeights(audioDriven).wide, 0);
  assert.equal(resolveMouthOpen({ mouthOpen: 1, speech: 0 }, 0, 0), 1);
});

test("computeLayerTransforms moves the coherent base as one silhouette", () => {
  const transforms = computeLayerTransforms(
    {
      headX: 1,
      headY: -1,
      headTilt: 1,
      gazeX: -1,
      gazeY: 1,
      breath: 1,
      shoulderSway: -1,
      handAccent: 1,
      hairSway: 1,
      smile: 1,
    },
    1.25,
  );

  assert.deepEqual(Object.keys(transforms).sort(), ["base", "brow", "iris"]);
  assert.ok(Math.abs(transforms.base.x) <= 10);
  assert.ok(Math.abs(transforms.base.y) <= 8);
  assert.ok(Math.abs(transforms.base.rotation) <= 0.04);
  assert.ok(Math.abs(transforms.iris.x) <= 12);
  assert.ok(Math.abs(transforms.iris.y) <= 7);
  assert.ok(transforms.base.scaleY >= 0.995);
  assert.ok(transforms.base.scaleY <= 1.008);
});
