function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

export function calculateRms(samples) {
  if (!samples?.length) return 0;
  let sumSquares = 0;
  for (const sample of samples) {
    const value = Number(sample) || 0;
    sumSquares += value * value;
  }
  return Math.sqrt(sumSquares / samples.length);
}

export function normalizeRms(rms) {
  const value = Number.isFinite(Number(rms)) ? Number(rms) : 0;
  return clamp((value - 0.015) * 7.5, 0, 1);
}

export class AudioRmsController {
  constructor() {
    this.context = null;
    this.analyser = null;
    this.source = null;
    this.audio = null;
    this.samples = null;
    this.objectUrl = null;
    this.smoothedLevel = 0;
    this.fileName = "";
  }

  async loadFile(file) {
    if (!(file instanceof Blob)) {
      throw new TypeError("audio file is required");
    }

    this.audio?.pause();
    if (this.objectUrl) URL.revokeObjectURL(this.objectUrl);
    if (this.context) await this.context.close();

    const AudioContextClass = window.AudioContext ?? window.webkitAudioContext;
    if (!AudioContextClass) {
      throw new Error("Web Audio API is not supported");
    }

    this.objectUrl = URL.createObjectURL(file);
    this.audio = new Audio();
    this.audio.preload = "auto";
    this.audio.src = this.objectUrl;
    this.audio.loop = true;

    await new Promise((resolve, reject) => {
      this.audio.addEventListener("loadedmetadata", resolve, { once: true });
      this.audio.addEventListener(
        "error",
        () => reject(new Error("音声ファイルを読み込めませんでした")),
        { once: true },
      );
      this.audio.load();
    });

    this.context = new AudioContextClass();
    this.analyser = this.context.createAnalyser();
    this.analyser.fftSize = 1024;
    this.analyser.smoothingTimeConstant = 0.32;
    this.source = this.context.createMediaElementSource(this.audio);
    this.source.connect(this.analyser);
    this.analyser.connect(this.context.destination);
    this.samples = new Float32Array(this.analyser.fftSize);
    this.smoothedLevel = 0;
    this.fileName = file.name || "AI voice";

    return {
      fileName: this.fileName,
      duration: Number.isFinite(this.audio.duration) ? this.audio.duration : 0,
    };
  }

  async play() {
    if (!this.audio || !this.context) return false;
    await this.context.resume();
    await this.audio.play();
    return true;
  }

  pause() {
    this.audio?.pause();
  }

  toggle() {
    return this.audio?.paused ? this.play() : Promise.resolve(this.pause());
  }

  get isPlaying() {
    return Boolean(this.audio && !this.audio.paused);
  }

  getLevel() {
    if (!this.analyser || !this.samples || !this.isPlaying) {
      this.smoothedLevel *= 0.72;
      return this.smoothedLevel;
    }

    this.analyser.getFloatTimeDomainData(this.samples);
    const target = normalizeRms(calculateRms(this.samples));
    const smoothing = target > this.smoothedLevel ? 0.48 : 0.18;
    this.smoothedLevel += (target - this.smoothedLevel) * smoothing;
    return this.smoothedLevel;
  }

  destroy() {
    this.audio?.pause();
    this.source?.disconnect();
    this.analyser?.disconnect();
    this.context?.close();
    if (this.objectUrl) URL.revokeObjectURL(this.objectUrl);
    this.context = null;
    this.analyser = null;
    this.source = null;
    this.audio = null;
    this.samples = null;
    this.objectUrl = null;
    this.smoothedLevel = 0;
  }
}
