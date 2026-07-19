export const DEFAULT_POSE = Object.freeze({
  headX: 0,
  headY: 0,
  headTurn: 0,
  headTilt: 0,
  blink: 0,
  gazeX: 0,
  gazeY: 0,
  mouthOpen: 0,
  smile: 0.12,
  breath: 0.35,
  shoulderSway: 0,
  handAccent: 0,
  bookBob: 0,
  hairSway: 0,
  speech: 0,
  turn: 0,
});

const POSE_LIMITS = Object.freeze({
  headX: [-1, 1],
  headY: [-1, 1],
  headTurn: [-1, 1],
  headTilt: [-1, 1],
  blink: [0, 1],
  gazeX: [-1, 1],
  gazeY: [-1, 1],
  mouthOpen: [0, 1],
  smile: [-1, 1],
  breath: [0, 1],
  shoulderSway: [-1, 1],
  handAccent: [-1, 1],
  bookBob: [-1, 1],
  hairSway: [-1, 1],
  speech: [0, 1],
  turn: [-1, 1],
});

export const POSE_KEYS = Object.freeze(Object.keys(DEFAULT_POSE));

export function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

export function normalizePose(input = {}) {
  const result = {};

  for (const key of POSE_KEYS) {
    const fallback = DEFAULT_POSE[key];
    const candidate = Number(input[key]);
    const value = Number.isFinite(candidate) ? candidate : fallback;
    const [min, max] = POSE_LIMITS[key];
    result[key] = clamp(value, min, max);
  }

  return result;
}

export function blendPose(from, to, amount) {
  const start = normalizePose(from);
  const end = normalizePose(to);
  const t = clamp(Number.isFinite(amount) ? amount : 0, 0, 1);
  const result = {};

  for (const key of POSE_KEYS) {
    result[key] = start[key] + (end[key] - start[key]) * t;
  }

  return normalizePose(result);
}

export function addPose(base, additions) {
  const result = { ...normalizePose(base) };
  for (const key of POSE_KEYS) {
    if (Number.isFinite(additions?.[key])) {
      result[key] += additions[key];
    }
  }
  return normalizePose(result);
}
