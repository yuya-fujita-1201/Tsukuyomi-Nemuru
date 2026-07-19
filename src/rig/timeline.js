import { blendPose, clamp, normalizePose } from "./pose.js";

const EMOTION_PRESETS = Object.freeze({
  calm: {
    smile: 0.12,
    breath: 0.35,
    headTilt: 0,
  },
  gentle: {
    smile: 0.42,
    breath: 0.48,
    headTilt: 0.12,
    headY: -0.04,
  },
  sleepy: {
    smile: 0.18,
    breath: 0.7,
    headTilt: -0.16,
    headY: 0.1,
    blink: 0.12,
  },
  focused: {
    smile: 0.02,
    breath: 0.28,
    headTilt: -0.04,
    gazeY: -0.08,
  },
  surprised: {
    smile: 0.05,
    breath: 0.62,
    headY: -0.16,
    mouthOpen: 0.48,
  },
});

const GESTURE_PRESETS = Object.freeze({
  none: {},
  present: {
    handAccent: 0.78,
    shoulderSway: -0.18,
    headTilt: 0.08,
  },
  nod: {
    headY: 0.52,
    bookBob: 0.12,
  },
  book: {
    bookBob: 0.55,
    gazeY: 0.34,
    headY: 0.12,
  },
  settle: {
    handAccent: -0.2,
    shoulderSway: 0.15,
    headTilt: -0.12,
  },
});

const DEFAULT_TRANSITION_SECONDS = 0.36;

function smoothstep(value) {
  const t = clamp(value, 0, 1);
  return t * t * (3 - 2 * t);
}

function normalizeCue(cue, index) {
  if (!cue || typeof cue !== "object") {
    throw new TypeError(`cue ${index} must be an object`);
  }

  const at = Number(cue.at);
  const duration = Number(cue.duration);
  if (!Number.isFinite(at) || at < 0) {
    throw new RangeError(`cue ${index} has an invalid at value`);
  }
  if (!Number.isFinite(duration) || duration <= 0) {
    throw new RangeError(`cue ${index} has an invalid duration`);
  }

  const emotion = String(cue.emotion ?? "calm");
  if (!(emotion in EMOTION_PRESETS)) {
    throw new RangeError(`cue ${index} has unknown emotion: ${emotion}`);
  }

  const gesture = String(cue.gesture ?? "none");
  if (!(gesture in GESTURE_PRESETS)) {
    throw new RangeError(`cue ${index} has unknown gesture: ${gesture}`);
  }

  const look = Array.isArray(cue.look) ? cue.look : [0, 0];
  const lookX = Number(look[0]);
  const lookY = Number(look[1]);

  return {
    at,
    duration,
    emotion,
    gesture,
    speech: clamp(Number.isFinite(Number(cue.speech)) ? Number(cue.speech) : 0, 0, 1),
    emphasis: clamp(
      Number.isFinite(Number(cue.emphasis)) ? Number(cue.emphasis) : 0,
      0,
      1,
    ),
    look: [
      clamp(Number.isFinite(lookX) ? lookX : 0, -1, 1),
      clamp(Number.isFinite(lookY) ? lookY : 0, -1, 1),
    ],
    turn: clamp(
      Number.isFinite(Number(cue.turn)) ? Number(cue.turn) : 0,
      -1,
      1,
    ),
    note: String(cue.note ?? ""),
  };
}

export function normalizeDirectorScript(input) {
  if (!input || typeof input !== "object") {
    throw new TypeError("director script must be an object");
  }
  if (Number(input.version) !== 1) {
    throw new RangeError("director script version must be 1");
  }
  if (!Array.isArray(input.cues) || input.cues.length === 0) {
    throw new RangeError("director script needs at least one cue");
  }

  const cues = input.cues.map(normalizeCue).sort((a, b) => a.at - b.at);
  for (let index = 1; index < cues.length; index += 1) {
    const previous = cues[index - 1];
    if (cues[index].at < previous.at + previous.duration - 1e-6) {
      throw new RangeError(`cue ${index} overlap detected`);
    }
  }

  return {
    version: 1,
    title: String(input.title ?? "Untitled performance"),
    cues,
    duration: Math.max(...cues.map((cue) => cue.at + cue.duration)),
  };
}

export function poseForCue(cue) {
  const emotion = EMOTION_PRESETS[cue?.emotion] ?? EMOTION_PRESETS.calm;
  const gesture = GESTURE_PRESETS[cue?.gesture] ?? GESTURE_PRESETS.none;
  const emphasis = clamp(Number(cue?.emphasis) || 0, 0, 1);
  const speech = clamp(Number(cue?.speech) || 0, 0, 1);
  const look = Array.isArray(cue?.look) ? cue.look : [0, 0];
  const turn = clamp(Number(cue?.turn) || 0, -1, 1);

  return normalizePose({
    ...emotion,
    ...gesture,
    gazeX: Number(look[0]) || 0,
    gazeY: (Number(look[1]) || 0) + (gesture.gazeY ?? emotion.gazeY ?? 0),
    speech,
    turn,
    headTurn: turn * 0.72,
    mouthOpen: Math.max(emotion.mouthOpen ?? 0, speech * (0.18 + emphasis * 0.14)),
    smile: (emotion.smile ?? 0) + emphasis * 0.08,
    headX: emphasis * 0.08,
    headY: (gesture.headY ?? emotion.headY ?? 0) - emphasis * 0.08,
    headTilt: (gesture.headTilt ?? emotion.headTilt ?? 0) + emphasis * 0.06,
    breath: Math.max(emotion.breath ?? 0.35, speech * 0.42),
    shoulderSway: (gesture.shoulderSway ?? 0) + emphasis * 0.16,
    handAccent: (gesture.handAccent ?? 0) + emphasis * 0.16,
    bookBob: gesture.bookBob ?? 0,
    hairSway: (gesture.headTilt ?? emotion.headTilt ?? 0) * 0.6,
  });
}

export function sampleDirectorScript(script, elapsedSeconds) {
  const normalized = script?.duration ? script : normalizeDirectorScript(script);
  const time = clamp(Number(elapsedSeconds) || 0, 0, normalized.duration);
  let activeIndex = 0;

  for (let index = 0; index < normalized.cues.length; index += 1) {
    if (normalized.cues[index].at <= time) {
      activeIndex = index;
    } else {
      break;
    }
  }

  const currentCue = normalized.cues[activeIndex];
  const currentPose = poseForCue(currentCue);
  if (activeIndex === 0) {
    return currentPose;
  }

  const transition = Math.min(
    DEFAULT_TRANSITION_SECONDS,
    currentCue.duration * 0.5,
  );
  const progress = (time - currentCue.at) / transition;
  if (progress >= 1) {
    return currentPose;
  }

  const previousPose = poseForCue(normalized.cues[activeIndex - 1]);
  return blendPose(previousPose, currentPose, smoothstep(progress));
}

export const DIRECTOR_OPTIONS = Object.freeze({
  emotions: Object.keys(EMOTION_PRESETS),
  gestures: Object.keys(GESTURE_PRESETS),
});
