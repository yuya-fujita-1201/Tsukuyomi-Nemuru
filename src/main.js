import "./styles.css";

import { AudioRmsController } from "./audio/audio-rms.js";
import {
  LAYERED_ASSET_COUNT,
  LAYERED_ASSET_URLS,
} from "./data/layered-assets.js";
import { PERFORMANCE_SCRIPTS } from "./data/performance-scripts.js";
import { POSE_KEYS, normalizePose } from "./rig/pose.js";
import { MOUTH_VOWELS } from "./rig/layered-motion.js";
import { PuppetEngine } from "./rig/puppet-engine.js";

const stage = document.querySelector("#puppet-stage");
const stageShell = document.querySelector("#stage-shell");
const loading = document.querySelector("#stage-loading");
const playButton = document.querySelector("#play-toggle");
const restartButton = document.querySelector("#restart-button");
const blinkButton = document.querySelector("#blink-button");
const meshToggle = document.querySelector("#mesh-toggle");
const scenarioSelect = document.querySelector("#scenario-select");
const turnVariantSelect = document.querySelector("#turn-variant-select");
const titleLabel = document.querySelector("#script-title");
const elapsedLabel = document.querySelector("#elapsed-time");
const totalLabel = document.querySelector("#total-time");
const cueList = document.querySelector("#cue-list");
const cueNote = document.querySelector("#cue-note");
const timelineProgress = document.querySelector("#timeline-progress");
const systemLabel = document.querySelector("#system-label");
const modePill = document.querySelector("#mode-pill");
const stageMode = document.querySelector("#stage-mode");
const stageFps = document.querySelector("#stage-fps");
const assetState = document.querySelector("#asset-state");
const scriptJson = document.querySelector("#script-json");
const applyJsonButton = document.querySelector("#apply-json");
const jsonStatus = document.querySelector("#json-status");
const audioFile = document.querySelector("#audio-file");
const audioFileName = document.querySelector("#audio-file-name");
const audioToggle = document.querySelector("#audio-toggle");
const audioStatus = document.querySelector("#audio-status");
const audioMeterFill = document.querySelector("#audio-meter-fill");
const formatButtons = [...document.querySelectorAll("[data-format]")];
const poseInputs = [...document.querySelectorAll("[data-pose]")];
const poseOutputs = new Map(
  [...document.querySelectorAll("[data-output]")].map((element) => [
    element.dataset.output,
    element,
  ]),
);
const presetButtons = [...document.querySelectorAll("[data-review-preset]")];
const resetParametersButton = document.querySelector("#reset-parameters");
const copyParameterUrlButton = document.querySelector("#copy-parameter-url");
const eyeTrackingState = document.querySelector("#eye-tracking-state");
const hairLinkState = document.querySelector("#hair-link-state");
const poseLinkState = document.querySelector("#pose-link-state");
const vowelButtons = [...document.querySelectorAll("[data-mouth-vowel]")];

const REVIEW_PRESETS = Object.freeze({
  neutral: Object.freeze({}),
  gaze: Object.freeze({ gazeX: 0.78, gazeY: -0.32 }),
  "neck-left": Object.freeze({ headTurn: -1 }),
  "neck-right": Object.freeze({ headTurn: 1 }),
  "body-left": Object.freeze({ turn: -1 }),
  "body-right": Object.freeze({ turn: 1 }),
});

let engine;
let activeScript;
let lastCueIndex = -1;
let lastUiUpdate = 0;
let parameterUrlTimer = null;
let manualPose = normalizePose();
let manualVowel = "auto";
const audioController = new AudioRmsController();

const initialParams = new URLSearchParams(window.location.search);
const initialPose = {};
for (const key of POSE_KEYS) {
  if (initialParams.has(key)) initialPose[key] = initialParams.get(key);
}
if (Object.keys(initialPose).length > 0) manualPose = normalizePose(initialPose);
const initialVariant = initialParams.get("variant");
if (
  initialVariant &&
  [...turnVariantSelect.options].some((option) => option.value === initialVariant)
) {
  turnVariantSelect.value = initialVariant;
}
const initialVowel = initialParams.get("vowel");
if (MOUTH_VOWELS.includes(initialVowel)) {
  manualVowel = initialVowel;
  if (manualVowel !== "auto" && !initialParams.has("mouthOpen")) {
    manualPose = normalizePose({ ...manualPose, mouthOpen: 0.5 });
  }
}

function formatTime(value) {
  return Number(value || 0).toFixed(1).padStart(4, "0");
}

function renderCueList(script) {
  cueList.replaceChildren(
    ...script.cues.map((cue, index) => {
      const item = document.createElement("li");
      item.dataset.cueIndex = String(index);
      const direction =
        cue.turn < -0.25 ? "LEFT 3/4" : cue.turn > 0.25 ? "RIGHT 3/4" : "FRONT";
      item.innerHTML = `
        <span class="cue-time">${formatTime(cue.at)}</span>
        <span class="cue-copy">
          <strong>${cue.emotion} / ${direction}</strong>
          <small>${cue.note || cue.gesture}</small>
        </span>
      `;
      return item;
    }),
  );
}

function setActiveCue(index) {
  if (index === lastCueIndex) return;
  lastCueIndex = index;
  for (const item of cueList.children) {
    item.classList.toggle(
      "is-active",
      Number(item.dataset.cueIndex) === index,
    );
  }
  cueNote.textContent =
    activeScript?.cues[index]?.note ?? "待機モーションを再生中";
}

function updatePlayButton(playing) {
  playButton.dataset.state = playing ? "playing" : "paused";
  playButton.querySelector(".action-icon").textContent = playing ? "Ⅱ" : "▶";
  playButton.querySelector(".action-label").textContent = playing
    ? "AI演技を一時停止"
    : "AI演技を開始";
}

function updateAudioButton() {
  audioToggle.textContent = audioController.isPlaying
    ? "音声を一時停止"
    : "音声を再生";
  audioToggle.dataset.state = audioController.isPlaying ? "playing" : "paused";
}

function setMode(mode) {
  const isAuto = mode === "auto";
  modePill.textContent = isAuto ? "AUTO" : "MANUAL";
  modePill.dataset.mode = mode;
  stageMode.textContent = isAuto ? "AI DIRECTOR" : "MANUAL TUNE";
}

function loadScript(script, { autoplay = true } = {}) {
  activeScript = engine.setScript(script, { autoplay });
  if (autoplay) {
    manualVowel = "auto";
    markVowel();
  }
  titleLabel.textContent = activeScript.title;
  totalLabel.textContent = formatTime(activeScript.duration);
  scriptJson.value = JSON.stringify(activeScript, null, 2);
  jsonStatus.textContent = "有効なキュー";
  jsonStatus.dataset.state = "valid";
  renderCueList(activeScript);
  setActiveCue(0);
  setMode(autoplay ? "auto" : "manual");
  updatePlayButton(engine.playing);
}

function syncManualControls(pose) {
  for (const input of poseInputs) {
    const key = input.dataset.pose;
    input.value = String(pose[key]);
    poseOutputs.get(key).value = Number(pose[key]).toFixed(2);
  }
}

function writeParameterUrl() {
  const url = new URL(window.location.href);
  url.search = "";
  url.searchParams.set("variant", turnVariantSelect.value);
  if (manualVowel !== "auto") {
    url.searchParams.set("vowel", manualVowel);
  }
  const defaults = normalizePose();
  for (const key of POSE_KEYS) {
    if (Math.abs(manualPose[key] - defaults[key]) > 0.0001) {
      url.searchParams.set(key, manualPose[key].toFixed(2));
    }
  }
  window.history.replaceState({}, "", url);
}

function syncParameterUrl({ immediate = false } = {}) {
  if (parameterUrlTimer !== null) {
    window.clearTimeout(parameterUrlTimer);
    parameterUrlTimer = null;
  }
  if (immediate) {
    writeParameterUrl();
    return;
  }
  parameterUrlTimer = window.setTimeout(() => {
    parameterUrlTimer = null;
    writeParameterUrl();
  }, 90);
}

function markVowel(activeVowel = manualVowel) {
  for (const button of vowelButtons) {
    const active = button.dataset.mouthVowel === activeVowel;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", String(active));
  }
}

function markPreset(activeName = null) {
  for (const button of presetButtons) {
    button.classList.toggle("is-active", button.dataset.reviewPreset === activeName);
  }
}

function applyReviewPose(input, presetName = null) {
  manualPose = normalizePose(input);
  manualVowel = "auto";
  engine.setTurnVariant("parameter");
  engine.setMouthVowel(manualVowel);
  turnVariantSelect.value = "parameter";
  engine.setManualPose(manualPose);
  syncManualControls(manualPose);
  setMode("manual");
  updatePlayButton(false);
  markPreset(presetName);
  markVowel();
  syncParameterUrl();
}

function applyManualVowel(vowel) {
  manualVowel = MOUTH_VOWELS.includes(vowel) ? vowel : "auto";
  if (manualVowel !== "auto") {
    manualPose = normalizePose({
      ...manualPose,
      mouthOpen: 0.5,
      speech: 0,
    });
  }
  engine.setTurnVariant("parameter");
  turnVariantSelect.value = "parameter";
  engine.setMouthVowel(manualVowel);
  engine.setManualPose(manualPose);
  syncManualControls(manualPose);
  setMode("manual");
  updatePlayButton(false);
  markPreset();
  markVowel();
  syncParameterUrl();
}

function enterManualMode(changedKey, changedValue) {
  manualPose = normalizePose({
    ...manualPose,
    [changedKey]: changedValue,
    speech: 0,
  });
  engine.setManualPose(manualPose);
  setMode("manual");
  updatePlayButton(false);
  markPreset();
  syncParameterUrl();
}

function setFormat(format) {
  stageShell.dataset.format = format;
  for (const button of formatButtons) {
    button.classList.toggle("is-active", button.dataset.format === format);
  }
  engine.setFraming(format);
}

async function boot() {
  try {
    engine = new PuppetEngine(stage, LAYERED_ASSET_URLS);
    await engine.init();
    engine.setTurnVariant(turnVariantSelect.value);
    engine.setAudioLevelSource(() => audioController.getLevel());
    window.__PUPPET__ = engine;
    window.__AUDIO_RMS__ = audioController;

    engine.onUpdate = (state) => {
      const now = performance.now();
      if (now - lastUiUpdate < 80) return;
      lastUiUpdate = now;
      elapsedLabel.textContent = formatTime(state.elapsed);
      const progress =
        state.duration > 0 ? (state.elapsed / state.duration) * 100 : 0;
      timelineProgress.style.width = `${progress}%`;
      setActiveCue(state.cueIndex);
      updatePlayButton(state.playing);
      stageFps.textContent = `${state.fps || "--"} FPS`;
      audioMeterFill.style.width = `${state.audioLevel * 100}%`;
      audioMeterFill.dataset.level = state.audioLevel.toFixed(3);
      stage.dataset.mouth = Object.entries(state.mouthWeights)
        .sort((a, b) => b[1] - a[1])[0][0];
      const headFramePosition =
        state.headTurnFrameBlend.lowerIndex +
        state.headTurnFrameBlend.upperAlpha;
      const headFrameDirection = state.headTurnFrameBlend.direction < 0
        ? "LEFT"
        : "RIGHT";
      const bodyFramePosition =
        state.bodyTurnFrameBlend.lowerIndex +
        state.bodyTurnFrameBlend.upperAlpha;
      const bodyFrameDirection = state.bodyTurnFrameBlend.direction < 0
        ? "LEFT"
        : "RIGHT";
      stage.dataset.view = state.bodyTurnSequenceActive
        ? `body-turn-${bodyFrameDirection.toLowerCase()}`
        : state.headTurnSequenceActive
          ? `head-turn-${headFrameDirection.toLowerCase()}`
          : "front";
      stage.dataset.turnVariant = state.turnVariant;
      stage.dataset.mouthVowel = state.mouthVowel;
      eyeTrackingState.textContent =
        `X ${state.pose.gazeX.toFixed(2)} / Y ${state.pose.gazeY.toFixed(2)}`;
      hairLinkState.textContent = state.bodyTurnSequenceActive
        ? "体キー追従 / メッシュ変形なし"
        : state.headTurnSequenceActive
          ? "首キー追従 / メッシュ変形なし"
          : "固定 / 変形なし";
      poseLinkState.textContent = state.bodyTurnSequenceActive
        ? `BODY ${bodyFrameDirection} ${bodyFramePosition.toFixed(1)} / 15`
        : state.headTurnSequenceActive
          ? `NECK ${headFrameDirection} ${headFramePosition.toFixed(1)} / 15`
        : state.turnVariant === "parameter"
          ? "FRONT"
          : Object.entries(state.turnWeights)
            .sort((a, b) => b[1] - a[1])[0][0]
            .replace(/([A-Z])/g, "-$1")
            .toUpperCase();
      stage.dataset.gaze = `${state.pose.gazeX.toFixed(2)},${state.pose.gazeY.toFixed(2)}`;
      stage.dataset.hairFollow = state.hairFollow.toFixed(2);
      if (state.playing) {
        manualPose = state.pose;
        manualVowel = state.mouthVowel;
        markVowel();
      }
    };

    loadScript(PERFORMANCE_SCRIPTS.whisper, { autoplay: false });
    engine.setMouthVowel(manualVowel);
    engine.setManualPose(manualPose);
    syncManualControls(manualPose);
    markVowel();
    markPreset(
      Object.keys(initialPose).length === 0 && turnVariantSelect.value === "parameter"
        && manualVowel === "auto"
        ? "neutral"
        : null,
    );
    syncParameterUrl();
    loading.classList.add("is-hidden");
    systemLabel.textContent = `${LAYERED_ASSET_COUNT}素材 / レイヤー駆動`;
    assetState.textContent = `${LAYERED_ASSET_COUNT} RASTER ASSETS`;
    document.body.dataset.ready = "true";
    document.body.dataset.engine = "layered";
    playButton.disabled = false;
    restartButton.disabled = false;
    blinkButton.disabled = false;
  } catch (error) {
    console.error(error);
    loading.textContent = "初期化に失敗しました";
    systemLabel.textContent = "初期化エラー";
    document.body.dataset.ready = "error";
  }
}

playButton.addEventListener("click", () => {
  if (engine.playing) {
    engine.pause();
  } else {
    if (!activeScript) return;
    engine.play();
    manualVowel = "auto";
    markVowel();
    syncParameterUrl();
    setMode("auto");
  }
  updatePlayButton(engine.playing);
});

restartButton.addEventListener("click", () => {
  engine.restart();
  manualVowel = "auto";
  markVowel();
  syncParameterUrl();
  setMode("auto");
  updatePlayButton(true);
});

blinkButton.addEventListener("click", () => {
  engine.triggerBlink();
});

meshToggle.addEventListener("change", () => {
  engine.setDebugGrid(meshToggle.checked);
});

scenarioSelect.addEventListener("change", () => {
  loadScript(PERFORMANCE_SCRIPTS[scenarioSelect.value], { autoplay: true });
});

turnVariantSelect.addEventListener("change", () => {
  engine.setTurnVariant(turnVariantSelect.value);
  stage.dataset.turnVariant = engine.turnVariant;
  syncParameterUrl();
});

for (const button of presetButtons) {
  button.addEventListener("click", () => {
    applyReviewPose(REVIEW_PRESETS[button.dataset.reviewPreset], button.dataset.reviewPreset);
  });
}

for (const button of vowelButtons) {
  button.addEventListener("click", () => {
    applyManualVowel(button.dataset.mouthVowel);
  });
}

resetParametersButton.addEventListener("click", () => {
  applyReviewPose({}, "neutral");
});

copyParameterUrlButton.addEventListener("click", async () => {
  syncParameterUrl({ immediate: true });
  try {
    await navigator.clipboard.writeText(window.location.href);
    copyParameterUrlButton.textContent = "コピー済み";
  } catch {
    copyParameterUrlButton.textContent = "URL反映済み";
  }
  window.setTimeout(() => {
    copyParameterUrlButton.textContent = "URLをコピー";
  }, 1200);
});

for (const button of formatButtons) {
  button.addEventListener("click", () => setFormat(button.dataset.format));
}

for (const input of poseInputs) {
  input.addEventListener("input", () => {
    const key = input.dataset.pose;
    const value = Number(input.value);
    poseOutputs.get(key).value = value.toFixed(2);
    enterManualMode(key, value);
  });
}

audioFile.addEventListener("change", async () => {
  const file = audioFile.files?.[0];
  if (!file) return;
  audioStatus.textContent = "解析準備中";
  audioStatus.dataset.state = "loading";
  try {
    const result = await audioController.loadFile(file);
    audioFileName.textContent = result.fileName;
    audioStatus.textContent = `${formatTime(result.duration)} sec`;
    audioStatus.dataset.state = "ready";
    audioToggle.disabled = false;
    updateAudioButton();
  } catch (error) {
    audioStatus.textContent = error.message;
    audioStatus.dataset.state = "invalid";
    audioToggle.disabled = true;
  }
});

audioToggle.addEventListener("click", async () => {
  try {
    await audioController.toggle();
    audioStatus.textContent = audioController.isPlaying ? "RMS駆動中" : "一時停止";
    audioStatus.dataset.state = audioController.isPlaying ? "playing" : "ready";
    updateAudioButton();
  } catch (error) {
    audioStatus.textContent = error.message;
    audioStatus.dataset.state = "invalid";
  }
});

applyJsonButton.addEventListener("click", () => {
  try {
    const parsed = JSON.parse(scriptJson.value);
    loadScript(parsed, { autoplay: true });
    jsonStatus.textContent = "反映済み";
    jsonStatus.dataset.state = "valid";
  } catch (error) {
    jsonStatus.textContent = error.message;
    jsonStatus.dataset.state = "invalid";
  }
});

window.addEventListener("beforeunload", () => {
  audioController.destroy();
  engine?.destroy();
});

boot();
