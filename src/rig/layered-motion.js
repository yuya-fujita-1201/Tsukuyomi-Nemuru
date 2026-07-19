import { clamp, normalizePose } from "./pose.js";

export const QUIET_MOUTH_OPEN_LIMIT = 0.4;
export const MOUTH_VOWELS = Object.freeze(["auto", "a", "i", "u", "e", "o"]);
export const TURN_VARIANTS = Object.freeze([
  "parameter",
  "full",
  "natural",
  "soft",
  "head-only",
]);
export const TURN_POSES = Object.freeze([
  "front",
  "right-step-25",
  "right-step-50",
  "natural-left",
  "natural-right",
  "right-step-80",
  "left",
  "right",
]);
export const TURN_SWAP_THRESHOLDS = Object.freeze({
  full: Object.freeze({ enter: 0.6, exit: 0.52 }),
  natural: Object.freeze({ enter: 0.46, exit: 0.38 }),
});
export const TURN_TRANSITION_TIMING = Object.freeze({
  closing: 0.12,
  sourceHold: 0.08,
  bridge: 0.28,
  targetHold: 0.08,
  opening: 0.1,
});
export const HEAD_TURN_FRAME_COUNT = 16;
export const BODY_TURN_FRAME_COUNT = 16;
export const TURN_ATLAS_CENTER_EPSILON = 0.035;
export const TURN_SETTLE_TIMING = Object.freeze({
  targetEpsilon: 0.0005,
  positionEpsilon: 0.004,
  delay: 0.08,
});

const TURN_TRANSITION_PHASES = Object.freeze([
  "idle",
  "closing",
  "source-hold",
  "bridge",
  "target-hold",
  "opening",
]);

function smoothstep(edge0, edge1, value) {
  if (value <= edge0) return 0;
  if (value >= edge1) return 1;
  const t = (value - edge0) / (edge1 - edge0);
  return t * t * (3 - 2 * t);
}

export function selectMouthWeights(input) {
  const value = clamp(Number(input) || 0, 0, 1);
  const microEntry = smoothstep(0.03, 0.12, value);
  const smallEntry = smoothstep(0.16, 0.34, value);
  const wideEntry = smoothstep(0.42, 0.78, value);
  const closed = 1 - microEntry;
  const micro = microEntry * (1 - smallEntry);
  const small = microEntry * smallEntry * (1 - wideEntry);
  const wide = microEntry * smallEntry * wideEntry;
  const total = closed + micro + small + wide || 1;

  return {
    closed: closed / total,
    micro: micro / total,
    small: small / total,
    wide: wide / total,
  };
}

function selectDirectionalFrameBlend(
  input,
  frameCount,
  snapToNearest = false,
) {
  const value = clamp(Number(input) || 0, -1, 1);
  const count = Math.max(2, Math.floor(Number(frameCount) || 16));
  // Keep the approved high-resolution front layers around neutral. Without
  // this dead zone, harmless floating-point drift swaps the entire character
  // to the lower-resolution side-atlas frame zero.
  if (Math.abs(value) <= TURN_ATLAS_CENTER_EPSILON) {
    return {
      active: false,
      direction: 0,
      lowerIndex: 0,
      upperIndex: 0,
      upperAlpha: 0,
    };
  }
  const position = Math.abs(value) * (count - 1);
  if (snapToNearest) {
    const frameIndex = Math.min(count - 1, Math.round(position));
    return {
      active: true,
      direction: Math.sign(value),
      lowerIndex: frameIndex,
      upperIndex: frameIndex,
      upperAlpha: 0,
    };
  }
  const lowerIndex = Math.min(count - 1, Math.floor(position));
  const upperIndex = Math.min(count - 1, lowerIndex + 1);
  return {
    active: true,
    direction: Math.sign(value),
    lowerIndex,
    upperIndex,
    upperAlpha: upperIndex === lowerIndex ? 0 : position - lowerIndex,
  };
}

export function selectHeadTurnFrameBlend(
  input,
  frameCount = HEAD_TURN_FRAME_COUNT,
  snapToNearest = false,
) {
  return selectDirectionalFrameBlend(input, frameCount, snapToNearest);
}

export function selectBodyTurnFrameBlend(
  input,
  frameCount = BODY_TURN_FRAME_COUNT,
  snapToNearest = false,
) {
  return selectDirectionalFrameBlend(input, frameCount, snapToNearest);
}

export function createTurnSettleState(target = 0) {
  return {
    target: clamp(Number(target) || 0, -1, 1),
    stableFor: 0,
    settled: false,
  };
}

export function advanceTurnSettleState(
  previousState,
  current,
  target,
  deltaSeconds,
) {
  const previous = previousState ?? createTurnSettleState(target);
  const safeCurrent = clamp(Number(current) || 0, -1, 1);
  const safeTarget = clamp(Number(target) || 0, -1, 1);
  const safeDelta = Math.max(
    0,
    Math.min(Number.isFinite(deltaSeconds) ? deltaSeconds : 0, 0.25),
  );
  const targetMoved =
    Math.abs(safeTarget - previous.target) > TURN_SETTLE_TIMING.targetEpsilon;
  const closeEnough =
    Math.abs(safeCurrent - safeTarget) <= TURN_SETTLE_TIMING.positionEpsilon;

  if (targetMoved || !closeEnough) {
    return {
      target: safeTarget,
      stableFor: 0,
      settled: false,
    };
  }

  const stableFor = previous.stableFor + safeDelta;
  return {
    // Keep the last meaningful target as the anchor. Tiny per-frame changes
    // can then accumulate past targetEpsilon instead of being mistaken for a
    // stationary input forever.
    target: previous.target,
    stableFor,
    settled: stableFor >= TURN_SETTLE_TIMING.delay,
  };
}

export function selectFrontMouthWeights(input, vowel = "auto") {
  const resolvedVowel = MOUTH_VOWELS.includes(vowel) ? vowel : "auto";
  const weights = {
    closed: 0,
    micro: 0,
    small: 0,
    wide: 0,
    a: 0,
    i: 0,
    u: 0,
    e: 0,
    o: 0,
  };

  if (resolvedVowel === "auto") {
    return { ...weights, ...selectMouthWeights(input) };
  }

  const value = clamp(Number(input) || 0, 0, 1);
  const open = smoothstep(0.08, 0.32, value);
  weights.closed = 1 - open;
  weights[resolvedVowel] = open;
  return weights;
}

function normalizeTurnVariant(input) {
  return TURN_VARIANTS.includes(input) ? input : "full";
}

function normalizeTurnPose(input, fallback = "front") {
  return TURN_POSES.includes(input) ? input : fallback;
}

function rasterPoseProfile(variant) {
  const resolved = normalizeTurnVariant(variant);
  if (resolved === "full") {
    return {
      left: "left",
      right: "right",
      thresholds: TURN_SWAP_THRESHOLDS.full,
    };
  }
  if (resolved === "natural") {
    return {
      left: "natural-left",
      right: "natural-right",
      thresholds: TURN_SWAP_THRESHOLDS.natural,
    };
  }
  return null;
}

export function resolveParameterCutPose(
  input,
  previousRequestedPose = "front",
) {
  const source = input && typeof input === "object"
    ? input
    : { turn: input, headTurn: 0 };
  const turn = clamp(Number(source.turn) || 0, -1, 1);
  const headTurn = clamp(Number(source.headTurn) || 0, -1, 1);
  const previous = normalizeTurnPose(previousRequestedPose);
  const { full, natural } = TURN_SWAP_THRESHOLDS;
  const rightSequence = [
    "front",
    "right-step-25",
    "right-step-50",
    "natural-right",
    "right-step-80",
    "right",
  ];

  let desired = "front";
  if (previous === "left" && turn < -full.exit) {
    desired = "left";
  } else if (turn <= -full.enter) {
    desired = "left";
  } else if (turn >= full.enter) {
    desired = turn >= 0.9
      ? "right"
      : turn >= 0.7
        ? "right-step-80"
        : "natural-right";
  } else if (headTurn <= -natural.enter) {
    desired = "natural-left";
  } else if (headTurn >= 0.78) {
    desired = "natural-right";
  } else if (headTurn >= 0.46) {
    desired = "right-step-50";
  } else if (headTurn >= 0.18) {
    desired = "right-step-25";
  } else if (turn >= 0.5) {
    desired = "natural-right";
  } else if (turn >= 0.3) {
    desired = "right-step-50";
  } else if (turn >= 0.12) {
    desired = "right-step-25";
  } else if (
    previous === "natural-left" &&
    headTurn < -natural.exit
  ) {
    desired = "natural-left";
  }

  if (desired === previous) return previous;
  const previousDirection = poseDirection(previous);
  const desiredDirection = poseDirection(desired);
  if (
    previousDirection !== 0 &&
    desiredDirection !== 0 &&
    previousDirection !== desiredDirection
  ) {
    return "front";
  }

  const previousRightIndex = rightSequence.indexOf(previous);
  const desiredRightIndex = rightSequence.indexOf(desired);
  if (previousRightIndex >= 0 && desiredRightIndex >= 0) {
    return rightSequence[
      previousRightIndex + Math.sign(desiredRightIndex - previousRightIndex)
    ];
  }

  if (desired === "natural-left" && previous === "left") {
    return "natural-left";
  }
  if (desired === "left" && previous === "natural-left") return "left";
  if (desired === "front") return "front";
  if (previous === "front") return desired;
  return "front";
}

function poseDirection(pose) {
  if (pose === "left" || pose === "natural-left") return -1;
  if (
    pose === "right" ||
    pose === "right-step-25" ||
    pose === "right-step-50" ||
    pose === "natural-right" ||
    pose === "right-step-80"
  ) return 1;
  return 0;
}

function poseWeightKey(pose) {
  if (pose === "right-step-25") return "rightStep25";
  if (pose === "right-step-50") return "rightStep50";
  if (pose === "natural-left") return "naturalLeft";
  if (pose === "natural-right") return "naturalRight";
  if (pose === "right-step-80") return "rightStep80";
  return pose;
}

function emptyTurnWeights() {
  return {
    front: 0,
    rightStep25: 0,
    rightStep50: 0,
    naturalLeft: 0,
    naturalRight: 0,
    rightStep80: 0,
    left: 0,
    right: 0,
  };
}

function resolveTransitionTargetPose(displayPose, requestedPose) {
  const display = normalizeTurnPose(displayPose);
  const requested = normalizeTurnPose(requestedPose, display);
  if (
    poseDirection(display) !== 0 &&
    poseDirection(requested) !== 0 &&
    poseDirection(display) !== poseDirection(requested)
  ) {
    return "front";
  }
  return requested;
}

export function resolveRequestedTurnPose(
  input,
  previousRequestedPose = "front",
  variant = "full",
) {
  if (normalizeTurnVariant(variant) === "parameter") {
    return resolveParameterCutPose(input, previousRequestedPose);
  }
  const profile = rasterPoseProfile(variant);
  if (!profile) return "front";

  const turn = clamp(Number(input) || 0, -1, 1);
  const allowed = new Set(["front", profile.left, profile.right]);
  const normalizedPrevious = normalizeTurnPose(previousRequestedPose);
  const previous = allowed.has(normalizedPrevious)
    ? normalizedPrevious
    : "front";

  if (previous === profile.left) {
    return turn < -profile.thresholds.exit ? profile.left : "front";
  }
  if (previous === profile.right) {
    return turn > profile.thresholds.exit ? profile.right : "front";
  }
  if (turn <= -profile.thresholds.enter) return profile.left;
  if (turn >= profile.thresholds.enter) return profile.right;
  return "front";
}

export function selectTurnPoseWeights(displayPose, variant = "full") {
  const resolvedVariant = normalizeTurnVariant(variant);
  const profile = rasterPoseProfile(resolvedVariant);
  const candidate = normalizeTurnPose(displayPose);
  const pose = resolvedVariant === "parameter"
    ? candidate
    : profile && ["front", profile.left, profile.right].includes(candidate)
      ? candidate
      : "front";
  const weights = emptyTurnWeights();
  weights[poseWeightKey(pose)] = 1;
  return weights;
}

export function resolveTurnBridgeVisuals(inputState) {
  const state = normalizeTurnTransitionState(inputState);
  const active = state.phase === "bridge";
  const progress = active ? clamp(state.bridgeProgress, 0, 1) : 0;
  let direction = 1;

  const targetDirection = poseDirection(state.targetPose);
  const displayDirection = poseDirection(state.displayPose);
  if (targetDirection !== 0) direction = targetDirection;
  else if (displayDirection !== 0) direction = -displayDirection;

  return {
    active,
    progress,
    sourcePose: state.displayPose,
    targetPose: state.targetPose,
    direction,
    blurStrengthX: active ? Math.sin(progress * Math.PI) * 5 : 0,
    blurStrengthY: active ? Math.sin(progress * Math.PI) * 0.55 : 0,
  };
}

export function selectTurnTransitionPoseWeights(
  inputState,
  variant = "full",
) {
  const resolvedVariant = normalizeTurnVariant(variant);
  const state = normalizeTurnTransitionState(inputState);
  const supportsRasterPoses =
    resolvedVariant === "parameter" || Boolean(rasterPoseProfile(resolvedVariant));
  if (!supportsRasterPoses || state.phase !== "bridge") {
    return selectTurnPoseWeights(state.displayPose, resolvedVariant);
  }

  const progress = clamp(state.bridgeProgress, 0, 1);
  const weights = emptyTurnWeights();
  weights[poseWeightKey(state.displayPose)] += 1 - progress;
  weights[poseWeightKey(state.targetPose)] += progress;
  return weights;
}

function turnWipeAdvance(normalizedY) {
  const y = clamp(Number(normalizedY) || 0, 0, 1);
  const head = Math.exp(-Math.pow((y - 0.29) / 0.2, 4)) * 0.085;
  const shoulders = Math.exp(-Math.pow((y - 0.52) / 0.16, 4)) * 0.025;
  const lowerTorsoLag = smoothstep(0.62, 0.94, y) * 0.028;
  return head + shoulders - lowerTorsoLag;
}

export function resolveTurnWipeBoundary(
  progressInput,
  directionInput,
  normalizedY,
) {
  const progress = clamp(Number(progressInput) || 0, 0, 1);
  // The canvas center contains the face, moon, shoulders, and most opaque
  // pixels. Spend more frames there and cross the mostly empty outer margins
  // faster so no single bridge frame carries the whole visual change.
  const travelProgress = progress +
    (Math.sin(progress * Math.PI * 2) * 0.55) / (Math.PI * 2);
  const direction = Number(directionInput) < 0 ? -1 : 1;
  const margin = 0.14;
  const travel = 1 + margin * 2;
  const base = direction < 0
    ? -margin + travel * travelProgress
    : 1 + margin - travel * travelProgress;
  return base - direction * turnWipeAdvance(normalizedY);
}

export function selectTurnWeights(input, variant = "full") {
  const resolvedVariant = normalizeTurnVariant(variant);
  const requestedPose = resolveRequestedTurnPose(input, "front", resolvedVariant);
  return selectTurnPoseWeights(requestedPose, resolvedVariant);
}

export function createTurnTransitionState(displayPose = "front") {
  const display = normalizeTurnPose(displayPose);
  return {
    requestedPose: display,
    displayPose: display,
    targetPose: display,
    phase: "idle",
    phaseElapsed: 0,
    phaseStartBlink: 0,
    bridgeProgress: 0,
    blink: 0,
    didSwap: false,
  };
}

function normalizeTurnTransitionState(inputState) {
  const fallback = createTurnTransitionState();
  const source = inputState && typeof inputState === "object"
    ? inputState
    : fallback;
  const displayPose = normalizeTurnPose(source.displayPose);
  const requestedPose = normalizeTurnPose(source.requestedPose, displayPose);
  const targetPose = normalizeTurnPose(source.targetPose, displayPose);
  const phase = TURN_TRANSITION_PHASES.includes(source.phase)
    ? source.phase
    : "idle";

  return {
    requestedPose,
    displayPose,
    targetPose,
    phase,
    phaseElapsed: Math.max(0, Number(source.phaseElapsed) || 0),
    phaseStartBlink: clamp(Number(source.phaseStartBlink) || 0, 0, 1),
    bridgeProgress: clamp(Number(source.bridgeProgress) || 0, 0, 1),
    blink: clamp(Number(source.blink) || 0, 0, 1),
    didSwap: false,
  };
}

function beginClosing(state, targetPose) {
  return {
    ...state,
    targetPose: resolveTransitionTargetPose(state.displayPose, targetPose),
    phase: "closing",
    phaseElapsed: 0,
    phaseStartBlink: state.blink,
    bridgeProgress: 0,
  };
}

function beginSourceHold(state, targetPose) {
  return {
    ...state,
    targetPose: resolveTransitionTargetPose(state.displayPose, targetPose),
    phase: "source-hold",
    phaseElapsed: 0,
    phaseStartBlink: 1,
    bridgeProgress: 0,
    blink: 1,
  };
}

function beginOpening(state) {
  if (state.blink <= 1e-9) {
    return {
      ...state,
      targetPose: state.displayPose,
      phase: "idle",
      phaseElapsed: 0,
      phaseStartBlink: 0,
      bridgeProgress: 0,
      blink: 0,
    };
  }
  return {
    ...state,
    targetPose: state.displayPose,
    phase: "opening",
    phaseElapsed: 0,
    phaseStartBlink: state.blink,
    bridgeProgress: 0,
  };
}

export function advanceTurnTransitionState(
  inputState,
  turnInput,
  deltaSeconds,
  variant = "full",
) {
  let state = normalizeTurnTransitionState(inputState);
  const resolvedVariant = normalizeTurnVariant(variant);
  const requestedPose = resolveRequestedTurnPose(
    turnInput,
    resolvedVariant === "parameter" ? state.displayPose : state.requestedPose,
    resolvedVariant,
  );
  const delta = clamp(
    Number.isFinite(Number(deltaSeconds)) ? Number(deltaSeconds) : 0,
    0,
    0.25,
  );
  state = { ...state, requestedPose, didSwap: false };

  if (state.phase === "idle") {
    if (requestedPose === state.displayPose) {
      return {
        ...state,
        targetPose: state.displayPose,
        phaseElapsed: 0,
        phaseStartBlink: 0,
        bridgeProgress: 0,
        blink: 0,
      };
    }
    state = beginClosing(state, requestedPose);
  }

  if (state.phase === "closing") {
    if (requestedPose === state.displayPose) {
      return beginOpening(state);
    }

    const phaseElapsed = state.phaseElapsed + delta;
    const progress = clamp(
      phaseElapsed / TURN_TRANSITION_TIMING.closing,
      0,
      1,
    );
    const blink = state.phaseStartBlink +
      (1 - state.phaseStartBlink) * smoothstep(0, 1, progress);
    if (progress < 1) {
      return { ...state, phaseElapsed, blink };
    }

    return beginSourceHold(state, state.targetPose);
  }

  if (state.phase === "source-hold") {
    if (requestedPose === state.displayPose) {
      return beginOpening(state);
    }
    const targetPose = requestedPose !== state.targetPose
      ? resolveTransitionTargetPose(state.displayPose, requestedPose)
      : state.targetPose;
    const phaseElapsed = state.phaseElapsed + delta;
    if (phaseElapsed < TURN_TRANSITION_TIMING.sourceHold) {
      return { ...state, targetPose, phaseElapsed, blink: 1 };
    }
    return {
      ...state,
      targetPose,
      phase: "bridge",
      phaseElapsed: 0,
      phaseStartBlink: 1,
      bridgeProgress: 0,
      blink: 1,
    };
  }

  if (state.phase === "bridge") {
    const phaseElapsed = state.phaseElapsed + delta;
    const bridgeProgress = clamp(
      phaseElapsed / TURN_TRANSITION_TIMING.bridge,
      0,
      1,
    );
    if (bridgeProgress < 1) {
      return { ...state, phaseElapsed, bridgeProgress, blink: 1 };
    }
    return {
      ...state,
      displayPose: state.targetPose,
      phase: "target-hold",
      phaseElapsed: 0,
      phaseStartBlink: 1,
      bridgeProgress: 1,
      blink: 1,
      didSwap: state.displayPose !== state.targetPose,
    };
  }

  if (state.phase === "target-hold") {
    const phaseElapsed = state.phaseElapsed + delta;
    if (phaseElapsed < TURN_TRANSITION_TIMING.targetHold) {
      return { ...state, phaseElapsed, blink: 1 };
    }
    if (requestedPose !== state.displayPose) {
      return {
        ...beginSourceHold(state, requestedPose),
        didSwap: false,
      };
    }
    return beginOpening({ ...state, phaseElapsed: 0, blink: 1 });
  }

  if (requestedPose !== state.displayPose) {
    return beginClosing(state, requestedPose);
  }

  const phaseElapsed = state.phaseElapsed + delta;
  const progress = clamp(
    phaseElapsed / TURN_TRANSITION_TIMING.opening,
    0,
    1,
  );
  const blink = state.phaseStartBlink * (1 - smoothstep(0, 1, progress));
  if (progress < 1) {
    return { ...state, phaseElapsed, blink };
  }
  return {
    ...state,
    targetPose: state.displayPose,
    phase: "idle",
    phaseElapsed: 0,
    phaseStartBlink: 0,
    blink: 0,
  };
}

export function selectSideExpressionWeights(blinkInput, mouthInput) {
  const blink = clamp(Number(blinkInput) || 0, 0, 1);
  const mouth = clamp(Number(mouthInput) || 0, 0, 1);
  return {
    neutral: (1 - blink) * (1 - mouth),
    blink: blink * (1 - mouth),
    mouthSmall: (1 - blink) * mouth,
    blinkMouthSmall: blink * mouth,
  };
}

export function selectFrontBlinkWeights(input) {
  const blink = clamp(Number(input) || 0, 0, 1);
  const open = Math.max(0, 1 - 2 * blink);
  const half = 1 - Math.abs(2 * blink - 1);
  const closed = Math.max(0, 2 * blink - 1);
  return {
    open,
    half,
    closed,
    // The iris keeps the same transform and coordinates through the half key;
    // the opaque upper-lid cover clips it optically from above.
    iris: open + half,
  };
}

export function resolveSideBlinkBlend(input) {
  const blink = clamp(Number(input) || 0, 0, 1);
  // A long dissolve between two complete eye drawings produces double
  // eyelids. Keep the open art through most of the motion and finish the
  // visual swap only around the closed-eye peak.
  return smoothstep(0.68, 0.94, blink);
}

export function selectSideExpressionAlphas(inputWeights = {}) {
  const order = ["neutral", "blink", "mouthSmall", "blinkMouthSmall"];
  const sanitized = Object.fromEntries(
    order.map((key) => [key, clamp(Number(inputWeights[key]) || 0, 0, 1)]),
  );
  const total = order.reduce((sum, key) => sum + sanitized[key], 0) || 1;
  const logical = Object.fromEntries(
    order.map((key) => [key, sanitized[key] / total]),
  );
  const alphas = {};
  let remaining = 1;

  for (let index = order.length - 1; index >= 0; index -= 1) {
    const key = order[index];
    alphas[key] = remaining > 1e-9
      ? clamp(logical[key] / remaining, 0, 1)
      : 0;
    remaining = Math.max(0, remaining - logical[key]);
  }

  return alphas;
}

export function resolveSideMouthBlend(
  input,
  limit = QUIET_MOUTH_OPEN_LIMIT,
) {
  const resolvedLimit = clamp(Number(limit) || QUIET_MOUTH_OPEN_LIMIT, 0.001, 1);
  return clamp((Number(input) || 0) / resolvedLimit, 0, 1);
}

export function resolveHeadOnlyOffsets(input) {
  const turn = clamp(Number(input) || 0, -1, 1);
  return {
    headX: turn * 0.92,
    headTilt: turn * 0.12,
  };
}

function resolveEllipticalGazeOffset(
  gazeXInput,
  gazeYInput,
  horizontalRange,
  verticalRange,
) {
  let normalizedX = clamp(Number(gazeXInput) || 0, -1, 1);
  let normalizedY = clamp(Number(gazeYInput) || 0, -1, 1);
  const radius = Math.hypot(normalizedX, normalizedY);
  if (radius > 1) {
    normalizedX /= radius;
    normalizedY /= radius;
  }
  return {
    x: normalizedX * horizontalRange,
    y: normalizedY * verticalRange,
  };
}

export function resolveGazeOffset(gazeXInput, gazeYInput) {
  return resolveEllipticalGazeOffset(gazeXInput, gazeYInput, 12, 7);
}

export function resolveSideGazeOffset(gazeXInput, gazeYInput) {
  return resolveEllipticalGazeOffset(gazeXInput, gazeYInput, 5, 2);
}

export function resolveSideGazeLayerAlpha(gazeXInput, gazeYInput) {
  // Side poses always use the clean eye-base/iris/line split, including at
  // centered gaze.  Cross-fading it over the baked neutral iris caused both
  // drawings to coexist around the old 0.02-0.10 onset radius, exposing an
  // outline/noise halo as soon as the eye began to move.
  void gazeXInput;
  void gazeYInput;
  return 1;
}

export function resolveHairFollow(inputPose = {}) {
  const pose = normalizePose(inputPose);
  return clamp(
    pose.hairSway -
      pose.headTurn * 0.68 -
      pose.headX * 0.18 -
      pose.headTilt * 0.22 -
      pose.turn * 0.18,
    -1,
    1,
  );
}

export function resolveMouthOpen(
  inputPose,
  elapsedSeconds,
  audioLevel = 0,
  maxMouthOpen = 1,
) {
  const pose = normalizePose(inputPose);
  const time = Number.isFinite(elapsedSeconds) ? elapsedSeconds : 0;
  const limit = clamp(Number(maxMouthOpen) || 0, 0, 1);
  const rhythmicSpeech =
    pose.speech *
    (0.26 +
      Math.abs(Math.sin(time * 11.7)) * 0.48 +
      Math.abs(Math.sin(time * 7.1 + 0.9)) * 0.26);

  return clamp(
    Math.max(
      pose.mouthOpen,
      rhythmicSpeech,
      clamp(Number(audioLevel) || 0, 0, 1),
    ),
    0,
    limit,
  );
}

export function computeLayerTransforms(inputPose, elapsedSeconds = 0) {
  const pose = normalizePose(inputPose);
  const time = Number.isFinite(elapsedSeconds) ? elapsedSeconds : 0;
  const idle = Math.sin(time * 0.72);
  const breath = Math.sin(time * 1.34) * pose.breath;

  const gaze = resolveGazeOffset(pose.gazeX, pose.gazeY);
  return {
    base: {
      x: pose.headX * 5.2 + pose.shoulderSway * 1.2 + idle * 1.3,
      y: pose.headY * 3.5 + breath * -2.2,
      rotation:
        pose.headTilt * 0.025 +
        pose.shoulderSway * 0.004 +
        idle * 0.002,
      scaleX: 1 + breath * 0.0018,
      scaleY: 1 + breath * 0.0055,
    },
    iris: {
      x: gaze.x,
      y: gaze.y,
      rotation: 0,
      scaleX: 1,
      scaleY: 1,
    },
    brow: {
      x: 0,
      y: -pose.smile * 1.2,
      rotation: pose.headTilt * 0.002,
      scaleX: 1,
      scaleY: 1 - Math.max(0, pose.smile) * 0.025,
    },
  };
}
