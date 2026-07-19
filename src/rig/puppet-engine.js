import {
  Application,
  Assets,
  BlurFilter,
  Container,
  Graphics,
  MeshSimple,
  Rectangle,
  Sprite,
  Texture,
} from "pixi.js";

import {
  advanceTurnSettleState,
  advanceTurnTransitionState,
  computeLayerTransforms,
  createTurnSettleState,
  createTurnTransitionState,
  MOUTH_VOWELS,
  QUIET_MOUTH_OPEN_LIMIT,
  resolveHeadOnlyOffsets,
  resolveHairFollow,
  resolveGazeOffset,
  resolveSideGazeOffset,
  resolveSideGazeLayerAlpha,
  resolveMouthOpen,
  resolveSideBlinkBlend,
  resolveSideMouthBlend,
  resolveTurnBridgeVisuals,
  resolveTurnWipeBoundary,
  selectFrontMouthWeights,
  selectFrontBlinkWeights,
  selectBodyTurnFrameBlend,
  selectHeadTurnFrameBlend,
  selectSideExpressionAlphas,
  selectSideExpressionWeights,
  selectTurnTransitionPoseWeights,
  TURN_ATLAS_CENTER_EPSILON,
  TURN_VARIANTS,
} from "./layered-motion.js";
import {
  FACE_LAYOUT,
  BODY_TURN_ATLAS_LAYOUT,
  BODY_TURN_PATCH_LAYOUTS,
  HEAD_TURN_ATLAS_LAYOUT,
  HEAD_TURN_PATCH_LAYOUTS,
  SIDE_EXPRESSION_ROIS,
} from "../data/layered-assets.js";
import { createGrid, deformGrid } from "./deform.js";
import { blendPose, normalizePose } from "./pose.js";
import {
  normalizeDirectorScript,
  sampleDirectorScript,
} from "./timeline.js";

const CANVAS_WIDTH = 1086;
const CANVAS_HEIGHT = 1448;
const HEAD_ANCHOR = Object.freeze({ x: 532, y: 369 });
const MESH_COLUMNS = 33;
const MESH_ROWS = 45;
const BODY_TURN_SMOOTHING_RATE = 9;
const HEAD_TURN_SMOOTHING_RATE = 12;
const TURN_VARIANT_CENTER_EPSILON = 0.012;

function applyTransform(container, anchor, transform) {
  container.position.set(anchor.x + transform.x, anchor.y + transform.y);
  container.rotation = transform.rotation;
  container.scale.set(transform.scaleX, transform.scaleY);
}

export class PuppetEngine {
  constructor(container, assetUrls) {
    this.container = container;
    this.assetUrls = assetUrls;
    this.app = null;
    this.textures = {};
    this.layers = {};
    this.anchors = {};
    this.sceneGroup = null;
    this.frontGroup = null;
    this.faceGroup = null;
    this.rightStep25PoseGroup = null;
    this.rightStep50PoseGroup = null;
    this.naturalLeftPoseGroup = null;
    this.naturalRightPoseGroup = null;
    this.headTurnGroups = {};
    this.headTurnSlots = {};
    this.headTurnFrameTextures = {};
    this.headTurnSequenceActive = false;
    this.bodyTurnGroups = {};
    this.bodyTurnSlots = {};
    this.bodyTurnFrameTextures = {};
    this.bodyTurnSequenceActive = false;
    this.rightStep80PoseGroup = null;
    this.leftPoseGroup = null;
    this.rightPoseGroup = null;
    this.turnWipeMasks = {};
    this.turnBridgeFilter = null;
    this.turnBridgeFilterActive = false;
    this.frontGrid = null;
    this.frontBaseMesh = null;
    this.frontMeshIsDeformed = false;
    this.debugOverlay = null;
    this.framing = "short";
    this.script = null;
    this.playing = false;
    this.scriptElapsed = 0;
    this.scriptStartedAt = 0;
    this.sessionStartedAt = performance.now();
    this.currentPose = normalizePose();
    this.targetPose = normalizePose();
    this.manualPose = normalizePose();
    this.currentTurn = 0;
    this.currentHeadTurn = 0;
    this.turnVariant = "full";
    this.turnTransitionState = createTurnTransitionState();
    this.pendingTurnVariant = null;
    this.pendingTurnTarget = null;
    this.pendingHeadTurnTarget = null;
    this.mouthVowel = "auto";
    this.onUpdate = null;
    this.nextBlinkAt = 2.4;
    this.blinkStartedAt = null;
    this.debugGridVisible = false;
    this.lastLayoutSize = "";
    this.resizeObserver = null;
    this.audioLevelSource = null;
    this.lastAudioLevel = 0;
    this.lastMouthWeights = selectFrontMouthWeights(0, this.mouthVowel);
    this.lastFrontBlinkWeights = selectFrontBlinkWeights(0);
    this.lastSideExpressionWeights = selectSideExpressionWeights(0, 0);
    this.lastSideExpressionAlphas = selectSideExpressionAlphas(
      this.lastSideExpressionWeights,
    );
    this.lastTurnWeights = selectTurnTransitionPoseWeights(
      this.turnTransitionState,
      this.turnVariant,
    );
    this.lastTurnBridgeVisuals = resolveTurnBridgeVisuals(
      this.turnTransitionState,
    );
    this.lastHeadTurnFrameBlend = selectHeadTurnFrameBlend(0);
    this.lastBodyTurnFrameBlend = selectBodyTurnFrameBlend(0);
    this.headTurnSettleState = createTurnSettleState(0);
    this.bodyTurnSettleState = createTurnSettleState(0);
    this.sideMotionLocked = false;
    this.lastSideGazeOffset = { x: 0, y: 0 };
    this.lastSideGazeLayerAlpha = 0;
    this.lastHairFollow = 0;
  }

  async init() {
    this.app = new Application();
    await this.app.init({
      width: Math.max(1, this.container.clientWidth),
      height: Math.max(1, this.container.clientHeight),
      backgroundAlpha: 0,
      antialias: true,
      autoDensity: true,
      resolution: Math.min(window.devicePixelRatio || 1, 1.5),
      preference: "webgl",
      powerPreference: "high-performance",
    });
    this.app.canvas.setAttribute(
      "aria-label",
      "月詠ねむり Layered AI Puppet preview",
    );
    this.container.appendChild(this.app.canvas);

    const entries = await Promise.all(
      Object.entries(this.assetUrls).map(async ([key, url]) => [
        key,
        await Assets.load(url),
      ]),
    );
    this.textures = Object.fromEntries(entries);
    this.buildLayerTree();

    this.resizeObserver = new ResizeObserver(([entry]) => {
      const width = Math.max(1, Math.round(entry.contentRect.width));
      const height = Math.max(1, Math.round(entry.contentRect.height));
      this.app.renderer.resize(width, height);
      this.layout();
    });
    this.resizeObserver.observe(this.container);

    this.layout();
    this.app.ticker.add((ticker) => this.tick(ticker.deltaMS / 1000));
    return this;
  }

  createMotionContainer(parent, key, pivotX, pivotY) {
    const motionContainer = new Container();
    motionContainer.label = key;
    motionContainer.pivot.set(pivotX, pivotY);
    motionContainer.position.set(pivotX, pivotY);
    parent.addChild(motionContainer);
    this.anchors[key] = { x: pivotX, y: pivotY };
    return motionContainer;
  }

  createSprite(parent, key, textureKey = key) {
    const sprite = new Sprite(this.textures[textureKey]);
    sprite.label = key;
    sprite.eventMode = "none";
    parent.addChild(sprite);
    this.layers[key] = sprite;
    return sprite;
  }

  createSideExpressionMask(parent, key, regions) {
    const mask = new Graphics();
    for (const [left, top, right, bottom] of regions) {
      mask.rect(left, top, right - left, bottom - top);
    }
    mask.fill(0xffffff);
    mask.label = key;
    mask.eventMode = "none";
    parent.addChild(mask);
    return mask;
  }

  createTurnWipeMask(key) {
    const mask = new Graphics();
    mask.label = key;
    mask.eventMode = "none";
    this.sceneGroup.addChild(mask);
    return mask;
  }

  createHeadTurnFrameTexture(
    atlasTexture,
    index,
    label,
    layout = HEAD_TURN_ATLAS_LAYOUT,
  ) {
    const column = index % layout.columns;
    const row = Math.floor(index / layout.columns);
    return new Texture({
      source: atlasTexture.source,
      label,
      frame: new Rectangle(
        column * layout.frameWidth,
        row * layout.frameHeight,
        layout.frameWidth,
        layout.frameHeight,
      ),
      orig: new Rectangle(
        0,
        0,
        layout.displayWidth,
        layout.displayHeight,
      ),
      trim: layout.trim
        ? new Rectangle(
            layout.trim[0],
            layout.trim[1],
            layout.trim[2] - layout.trim[0],
            layout.trim[3] - layout.trim[1],
          )
        : undefined,
    });
  }

  buildHeadTurnFrameTextures() {
    const states = {
      neutral: "Neutral",
      blink: "Blink",
      mouthSmall: "MouthSmall",
      eyeBase: "EyeBase",
      irises: "Irises",
      eyeLine: "EyeLine",
    };
    for (const direction of ["left", "right"]) {
      const prefix = direction[0].toUpperCase() + direction.slice(1);
      this.headTurnFrameTextures[direction] = {};
      for (const [state, suffix] of Object.entries(states)) {
        const atlasKey = `headTurn${prefix}${suffix}Atlas`;
        const layout = state === "neutral"
          ? HEAD_TURN_ATLAS_LAYOUT
          : {
              ...HEAD_TURN_PATCH_LAYOUTS[direction][state],
              columns: HEAD_TURN_ATLAS_LAYOUT.columns,
              displayWidth: HEAD_TURN_ATLAS_LAYOUT.displayWidth,
              displayHeight: HEAD_TURN_ATLAS_LAYOUT.displayHeight,
            };
        this.headTurnFrameTextures[direction][state] = Array.from(
          { length: HEAD_TURN_ATLAS_LAYOUT.frameCount },
          (_, index) => this.createHeadTurnFrameTexture(
            this.textures[atlasKey],
            index,
            `${atlasKey}Frame${index}`,
            layout,
          ),
        );
      }
    }
  }

  createHeadTurnSlot(parent, direction, slotName) {
    const slot = new Container();
    const title = slotName[0].toUpperCase() + slotName.slice(1);
    const directionTitle = direction[0].toUpperCase() + direction.slice(1);
    slot.label = `headTurn${directionTitle}${title}Slot`;
    parent.addChild(slot);

    const createLayer = (state, stateTitle) => {
      const key = `headTurn${directionTitle}${title}${stateTitle}`;
      const sprite = new Sprite(this.headTurnFrameTextures[direction][state][0]);
      sprite.label = key;
      sprite.eventMode = "none";
      slot.addChild(sprite);
      this.layers[key] = sprite;
      return sprite;
    };
    const layers = {
      neutral: createLayer("neutral", "Neutral"),
      eyeBase: createLayer("eyeBase", "EyeBase"),
      irises: createLayer("irises", "Irises"),
      eyeLine: createLayer("eyeLine", "EyeLine"),
      blink: createLayer("blink", "Blink"),
      mouthSmall: createLayer("mouthSmall", "MouthSmall"),
    };
    layers.blink.alpha = 0;
    layers.mouthSmall.alpha = 0;
    slot.alpha = 0;
    return { group: slot, layers, frameIndex: -1 };
  }

  createHeadTurnDirectionGroup(direction) {
    const directionTitle = direction[0].toUpperCase() + direction.slice(1);
    const key = `headTurn${directionTitle}Group`;
    const group = this.createMotionContainer(this.sceneGroup, key, 543, 620);
    this.headTurnGroups[direction] = group;
    this.headTurnSlots[direction] = {
      lower: this.createHeadTurnSlot(group, direction, "lower"),
      upper: this.createHeadTurnSlot(group, direction, "upper"),
    };
    group.alpha = 0;
    group.visible = false;
    return group;
  }

  buildBodyTurnFrameTextures() {
    const states = {
      neutral: "Neutral",
      blink: "Blink",
      mouthSmall: "MouthSmall",
      eyeBase: "EyeBase",
      irises: "Irises",
      eyeLine: "EyeLine",
    };
    for (const direction of ["left", "right"]) {
      const prefix = direction[0].toUpperCase() + direction.slice(1);
      this.bodyTurnFrameTextures[direction] = {};
      for (const [state, suffix] of Object.entries(states)) {
        const atlasKey = `bodyTurn${prefix}${suffix}Atlas`;
        const layout = state === "neutral"
          ? BODY_TURN_ATLAS_LAYOUT
          : {
              ...BODY_TURN_PATCH_LAYOUTS[direction][state],
              columns: BODY_TURN_ATLAS_LAYOUT.columns,
              displayWidth: BODY_TURN_ATLAS_LAYOUT.displayWidth,
              displayHeight: BODY_TURN_ATLAS_LAYOUT.displayHeight,
            };
        this.bodyTurnFrameTextures[direction][state] = Array.from(
          { length: BODY_TURN_ATLAS_LAYOUT.frameCount },
          (_, index) => this.createHeadTurnFrameTexture(
            this.textures[atlasKey],
            index,
            `${atlasKey}Frame${index}`,
            layout,
          ),
        );
      }
    }
  }

  createBodyTurnSlot(parent, direction, slotName) {
    const slot = new Container();
    const title = slotName[0].toUpperCase() + slotName.slice(1);
    const directionTitle = direction[0].toUpperCase() + direction.slice(1);
    slot.label = `bodyTurn${directionTitle}${title}Slot`;
    parent.addChild(slot);

    const createLayer = (state, stateTitle) => {
      const key = `bodyTurn${directionTitle}${title}${stateTitle}`;
      const sprite = new Sprite(this.bodyTurnFrameTextures[direction][state][0]);
      sprite.label = key;
      sprite.eventMode = "none";
      slot.addChild(sprite);
      this.layers[key] = sprite;
      return sprite;
    };
    const layers = {
      neutral: createLayer("neutral", "Neutral"),
      eyeBase: createLayer("eyeBase", "EyeBase"),
      irises: createLayer("irises", "Irises"),
      eyeLine: createLayer("eyeLine", "EyeLine"),
      blink: createLayer("blink", "Blink"),
      mouthSmall: createLayer("mouthSmall", "MouthSmall"),
    };
    layers.blink.alpha = 0;
    layers.mouthSmall.alpha = 0;
    slot.alpha = 0;
    return { group: slot, layers, frameIndex: -1 };
  }

  createBodyTurnDirectionGroup(direction) {
    const directionTitle = direction[0].toUpperCase() + direction.slice(1);
    const key = `bodyTurn${directionTitle}Group`;
    const group = this.createMotionContainer(this.sceneGroup, key, 543, 620);
    this.bodyTurnGroups[direction] = group;
    this.bodyTurnSlots[direction] = {
      lower: this.createBodyTurnSlot(group, direction, "lower"),
      upper: this.createBodyTurnSlot(group, direction, "upper"),
    };
    group.alpha = 0;
    group.visible = false;
    return group;
  }

  createExpressionPoseGroup(groupKey, layerPrefix, roiKey) {
    const group = this.createMotionContainer(
      this.sceneGroup,
      groupKey,
      543,
      620,
    );
    this.createSprite(group, `pose${layerPrefix}`);
    const blink = this.createSprite(group, `pose${layerPrefix}Blink`);
    const mouth = this.createSprite(group, `pose${layerPrefix}MouthSmall`);
    const combined = this.createSprite(
      group,
      `pose${layerPrefix}BlinkMouthSmall`,
    );
    blink.alpha = 0;
    mouth.alpha = 0;
    combined.alpha = 0;
    blink.mask = this.createSideExpressionMask(
      group,
      `${groupKey}BlinkRoiMask`,
      SIDE_EXPRESSION_ROIS[roiKey],
    );
    mouth.mask = this.createSideExpressionMask(
      group,
      `${groupKey}MouthRoiMask`,
      SIDE_EXPRESSION_ROIS[roiKey],
    );
    combined.mask = this.createSideExpressionMask(
      group,
      `${groupKey}CombinedRoiMask`,
      SIDE_EXPRESSION_ROIS[roiKey],
    );
    group.alpha = 0;
    return group;
  }

  buildLayerTree() {
    this.sceneGroup = new Container();
    this.sceneGroup.label = "tsukuyomi_nemuri_scene";
    this.app.stage.addChild(this.sceneGroup);

    this.buildHeadTurnFrameTextures();
    this.createHeadTurnDirectionGroup("left");
    this.createHeadTurnDirectionGroup("right");
    this.buildBodyTurnFrameTextures();
    this.createBodyTurnDirectionGroup("left");
    this.createBodyTurnDirectionGroup("right");

    this.frontGroup = this.createMotionContainer(
      this.sceneGroup,
      "base",
      543,
      780,
    );
    this.frontGroup.label = "front_coherent_avatar";
    this.frontGrid = createGrid(
      CANVAS_WIDTH,
      CANVAS_HEIGHT,
      MESH_COLUMNS,
      MESH_ROWS,
    );
    this.frontBaseMesh = new MeshSimple({
      texture: this.textures.frontBase,
      vertices: this.frontGrid.positions.slice(),
      uvs: this.frontGrid.uvs,
      indices: this.frontGrid.indices,
    });
    this.frontBaseMesh.label = "frontBase";
    this.frontBaseMesh.eventMode = "none";
    this.frontGroup.addChild(this.frontBaseMesh);
    this.layers.frontBase = this.frontBaseMesh;

    this.faceGroup = this.createMotionContainer(
      this.frontGroup,
      "face",
      HEAD_ANCHOR.x,
      HEAD_ANCHOR.y,
    );
    this.layers.eyeOpen = this.createSprite(this.faceGroup, "eyeOpen");

    this.irisGroup = this.createMotionContainer(
      this.faceGroup,
      "iris",
      FACE_LAYOUT.irisAnchor.x,
      FACE_LAYOUT.irisAnchor.y,
    );
    this.layers.irises = this.createSprite(this.irisGroup, "irises");
    this.eyeMask = new Graphics();
    for (const mask of FACE_LAYOUT.eyeMasks) {
      this.eyeMask.ellipse(
        mask.x,
        mask.y,
        mask.radiusX,
        mask.radiusY,
      );
    }
    this.eyeMask.fill(0xffffff);
    this.eyeMask.label = "iris_sclera_mask";
    this.faceGroup.addChild(this.eyeMask);
    this.irisGroup.mask = this.eyeMask;

    this.layers.eyesHalf = this.createSprite(
      this.faceGroup,
      "eyesHalf",
    );
    this.layers.eyesHalf.alpha = 0;

    this.layers.eyesClosed = this.createSprite(
      this.faceGroup,
      "eyesClosed",
    );
    this.layers.eyesClosed.alpha = 0;

    this.browGroup = this.createMotionContainer(
      this.faceGroup,
      "brow",
      FACE_LAYOUT.browAnchor.x,
      FACE_LAYOUT.browAnchor.y,
    );
    this.layers.brows = this.createSprite(this.browGroup, "brows");

    this.layers.mouthClosed = this.createSprite(
      this.faceGroup,
      "mouthClosed",
    );
    this.layers.mouthMicro = this.createSprite(
      this.faceGroup,
      "mouthMicro",
    );
    this.layers.mouthSmall = this.createSprite(
      this.faceGroup,
      "mouthSmall",
    );
    this.layers.mouthWide = this.createSprite(
      this.faceGroup,
      "mouthWide",
    );
    for (const vowel of ["A", "I", "U", "E", "O"]) {
      const key = `mouth${vowel}`;
      this.layers[key] = this.createSprite(this.faceGroup, key);
      this.layers[key].alpha = 0;
    }
    this.layers.mouthSmall.alpha = 0;
    this.layers.mouthMicro.alpha = 0;
    this.layers.mouthWide.alpha = 0;

    this.debugOverlay = new Graphics();
    this.debugOverlay.label = "part_motion_guides";
    this.debugOverlay.visible = false;
    this.sceneGroup.addChild(this.debugOverlay);
    this.drawDebugGuides();

    this.turnWipeMasks = {};
    this.turnBridgeFilter = null;
  }

  fillTurnMask(graphics, points = null) {
    graphics.clear();
    if (points?.length) graphics.poly(points).fill(0xffffff);
    else {
      const padding = 220;
      graphics
        .rect(
          -padding,
          -padding,
          CANVAS_WIDTH + padding * 2,
          CANVAS_HEIGHT + padding * 2,
        )
        .fill(0xffffff);
    }
  }

  drawFullTurnWipeMasks() {
    for (const mask of Object.values(this.turnWipeMasks)) {
      this.fillTurnMask(mask);
    }
  }

  buildTurnWipePolygons(visuals) {
    const padding = 220;
    const samples = 18;
    const boundaries = [];
    for (let index = 0; index <= samples; index += 1) {
      const normalizedY = index / samples;
      boundaries.push({
        x: resolveTurnWipeBoundary(
          visuals.progress,
          visuals.direction,
          normalizedY,
        ) * CANVAS_WIDTH,
        y: normalizedY * CANVAS_HEIGHT,
      });
    }

    const left = [-padding, -padding, boundaries[0].x, -padding];
    for (let index = 1; index < boundaries.length; index += 1) {
      left.push(boundaries[index].x, boundaries[index].y);
    }
    left.push(-padding, CANVAS_HEIGHT + padding);

    const right = [
      boundaries[0].x,
      -padding,
      CANVAS_WIDTH + padding,
      -padding,
      CANVAS_WIDTH + padding,
      CANVAS_HEIGHT + padding,
      boundaries.at(-1).x,
      CANVAS_HEIGHT + padding,
    ];
    for (let index = boundaries.length - 2; index >= 0; index -= 1) {
      right.push(boundaries[index].x, boundaries[index].y);
    }

    return { left, right };
  }

  applyTurnPoseVisibility() {
    this.frontGroup.alpha = 1;
    this.headTurnSequenceActive = false;
    this.bodyTurnSequenceActive = false;
    for (const groups of [this.headTurnGroups, this.bodyTurnGroups]) {
      for (const group of Object.values(groups)) {
        group.alpha = 0;
        group.visible = false;
      }
    }
  }

  applySequenceSlot(frameTextures, layout, direction, slot, frameIndex, alpha) {
    const resolvedIndex = Math.max(
      0,
      Math.min(layout.frameCount - 1, frameIndex),
    );
    if (slot.frameIndex !== resolvedIndex) {
      for (const [state, sprite] of Object.entries(slot.layers)) {
        sprite.texture = frameTextures[direction][state][resolvedIndex];
      }
      slot.frameIndex = resolvedIndex;
    }
    const blink =
      this.lastSideExpressionWeights.blink +
      this.lastSideExpressionWeights.blinkMouthSmall;
    const mouth =
      this.lastSideExpressionWeights.mouthSmall +
      this.lastSideExpressionWeights.blinkMouthSmall;
    slot.layers.neutral.alpha = 1;
    slot.layers.eyeBase.alpha = this.lastSideGazeLayerAlpha;
    slot.layers.irises.alpha =
      this.lastSideGazeLayerAlpha * (1 - blink);
    slot.layers.irises.position.set(
      this.lastSideGazeOffset.x,
      this.lastSideGazeOffset.y,
    );
    slot.layers.eyeLine.alpha =
      this.lastSideGazeLayerAlpha * (1 - blink);
    slot.layers.blink.alpha = blink;
    slot.layers.mouthSmall.alpha = mouth;
    slot.group.alpha = alpha;
  }

  applyHeadTurnSlot(direction, slot, frameIndex, alpha) {
    this.applySequenceSlot(
      this.headTurnFrameTextures,
      HEAD_TURN_ATLAS_LAYOUT,
      direction,
      slot,
      frameIndex,
      alpha,
    );
  }

  applyBodyTurnSlot(direction, slot, frameIndex, alpha) {
    this.applySequenceSlot(
      this.bodyTurnFrameTextures,
      BODY_TURN_ATLAS_LAYOUT,
      direction,
      slot,
      frameIndex,
      alpha,
    );
  }

  applyHeadTurnSequence() {
    const blend = this.lastHeadTurnFrameBlend;
    if (
      !["parameter", "natural"].includes(this.turnVariant) ||
      (this.turnVariant === "parameter" &&
        Math.abs(this.currentTurn) > TURN_ATLAS_CENTER_EPSILON) ||
      !blend.active
    ) {
      return false;
    }

    const direction = blend.direction < 0 ? "left" : "right";
    const slots = this.headTurnSlots[direction];
    this.applyHeadTurnSlot(direction, slots.lower, blend.lowerIndex, 1);
    this.applyHeadTurnSlot(
      direction,
      slots.upper,
      blend.upperIndex,
      blend.upperIndex === blend.lowerIndex ? 0 : blend.upperAlpha,
    );
    this.headTurnGroups[direction].visible = true;
    this.headTurnGroups[direction].alpha = 1;
    this.frontGroup.alpha = 0;
    this.headTurnSequenceActive = true;
    return true;
  }

  applyBodyTurnSequence() {
    const blend = this.lastBodyTurnFrameBlend;
    if (
      !["parameter", "full"].includes(this.turnVariant) ||
      !blend.active
    ) {
      return false;
    }

    const direction = blend.direction < 0 ? "left" : "right";
    const slots = this.bodyTurnSlots[direction];
    this.applyBodyTurnSlot(direction, slots.lower, blend.lowerIndex, 1);
    this.applyBodyTurnSlot(
      direction,
      slots.upper,
      blend.upperIndex,
      blend.upperIndex === blend.lowerIndex ? 0 : blend.upperAlpha,
    );
    this.bodyTurnGroups[direction].visible = true;
    this.bodyTurnGroups[direction].alpha = 1;
    this.frontGroup.alpha = 0;
    this.bodyTurnSequenceActive = true;
    return true;
  }

  drawDebugGuides() {
    this.debugOverlay
      .clear()
      .rect(370, 300, 346, 360)
      .stroke({ color: 0xf3ddc5, width: 2, alpha: 0.6 })
      .rect(348, 390, 368, 128)
      .stroke({ color: 0xd4b6ee, width: 2, alpha: 0.7 })
      .rect(490, 520, 106, 90)
      .stroke({ color: 0xf1a8bd, width: 2, alpha: 0.7 })
      .circle(543, 780, 8)
      .fill({ color: 0xf3ddc5, alpha: 0.8 });
  }

  setScript(input, { autoplay = false } = {}) {
    this.script = normalizeDirectorScript(input);
    this.scriptElapsed = 0;
    this.targetPose = sampleDirectorScript(this.script, 0);
    if (autoplay) this.play();
    else this.pause();
    return this.script;
  }

  play() {
    if (!this.script) return;
    this.mouthVowel = "auto";
    this.scriptStartedAt = performance.now() - this.scriptElapsed * 1000;
    this.playing = true;
  }

  pause() {
    if (this.playing) {
      this.scriptElapsed = this.getScriptElapsed(performance.now());
    }
    this.playing = false;
  }

  restart() {
    this.scriptElapsed = 0;
    this.scriptStartedAt = performance.now();
    if (this.script) {
      this.mouthVowel = "auto";
      this.targetPose = sampleDirectorScript(this.script, 0);
      this.playing = true;
    }
  }

  setManualPose(input) {
    this.pause();
    this.manualPose = normalizePose({ ...this.manualPose, ...input });
    this.targetPose = this.manualPose;
    if (this.pendingTurnVariant) {
      this.pendingTurnTarget = this.manualPose.turn;
      this.pendingHeadTurnTarget = this.manualPose.headTurn;
    }
  }

  setMouthVowel(vowel) {
    this.mouthVowel = MOUTH_VOWELS.includes(vowel) ? vowel : "auto";
    return this.mouthVowel;
  }

  setAudioLevelSource(source) {
    this.audioLevelSource = typeof source === "function" ? source : null;
  }

  triggerBlink() {
    this.blinkStartedAt = this.getSessionElapsed();
  }

  setFraming(mode) {
    if (!["short", "wide"].includes(mode)) return;
    this.framing = mode;
    this.layout();
  }

  setTurnVariant(variant) {
    if (!TURN_VARIANTS.includes(variant)) return this.turnVariant;

    if (variant === this.turnVariant) {
      this.pendingTurnVariant = null;
      this.pendingTurnTarget = null;
      this.pendingHeadTurnTarget = null;
      return this.turnVariant;
    }
    if (variant === this.pendingTurnVariant) return this.turnVariant;

    if (
      Math.abs(this.currentTurn) <= TURN_VARIANT_CENTER_EPSILON &&
      Math.abs(this.currentHeadTurn) <= TURN_VARIANT_CENTER_EPSILON &&
      this.turnTransitionState.displayPose === "front" &&
      this.turnTransitionState.phase === "idle"
    ) {
      this.currentTurn = 0;
      this.currentHeadTurn = 0;
      this.turnVariant = variant;
      this.pendingTurnVariant = null;
      this.pendingTurnTarget = null;
      this.pendingHeadTurnTarget = null;
      return this.turnVariant;
    }

    this.pendingTurnVariant = variant;
    this.pendingTurnTarget = this.targetPose.turn;
    this.pendingHeadTurnTarget = this.targetPose.headTurn;
    return this.turnVariant;
  }

  advanceTurnTransition(deltaSeconds) {
    const safeDelta = Math.max(
      0,
      Math.min(Number.isFinite(deltaSeconds) ? deltaSeconds : 0, 0.25),
    );
    const bodyTurnSmoothing =
      1 - Math.exp(-safeDelta * BODY_TURN_SMOOTHING_RATE);
    const headTurnSmoothing =
      1 - Math.exp(-safeDelta * HEAD_TURN_SMOOTHING_RATE);

    if (this.pendingTurnVariant) {
      this.pendingTurnTarget = this.targetPose.turn;
      this.pendingHeadTurnTarget = this.targetPose.headTurn;
    }
    const effectiveTarget = this.pendingTurnVariant ? 0 : this.targetPose.turn;
    const effectiveHeadTarget = this.pendingTurnVariant
      ? 0
      : this.targetPose.headTurn;
    this.currentTurn +=
      (effectiveTarget - this.currentTurn) * bodyTurnSmoothing;
    this.currentHeadTurn +=
      (effectiveHeadTarget - this.currentHeadTurn) * headTurnSmoothing;

    this.bodyTurnSettleState = advanceTurnSettleState(
      this.bodyTurnSettleState,
      this.currentTurn,
      effectiveTarget,
      safeDelta,
    );
    this.headTurnSettleState = advanceTurnSettleState(
      this.headTurnSettleState,
      this.currentHeadTurn,
      effectiveHeadTarget,
      safeDelta,
    );
    if (this.bodyTurnSettleState.settled) {
      this.currentTurn = effectiveTarget;
    }
    if (this.headTurnSettleState.settled) {
      this.currentHeadTurn = effectiveHeadTarget;
    }

    this.turnTransitionState = ["parameter", "full", "natural"].includes(
      this.turnVariant,
    )
      ? createTurnTransitionState("front")
      : advanceTurnTransitionState(
          this.turnTransitionState,
          this.currentTurn,
          safeDelta,
          this.turnVariant,
        );

    if (
      this.pendingTurnVariant &&
      Math.abs(this.currentTurn) <= TURN_VARIANT_CENTER_EPSILON &&
      Math.abs(this.currentHeadTurn) <= TURN_VARIANT_CENTER_EPSILON &&
      this.turnTransitionState.displayPose === "front" &&
      this.turnTransitionState.phase === "idle"
    ) {
      const nextVariant = this.pendingTurnVariant;
      const returnTarget = this.pendingTurnTarget ?? this.targetPose.turn;
      const returnHeadTarget =
        this.pendingHeadTurnTarget ?? this.targetPose.headTurn;
      this.currentTurn = 0;
      this.currentHeadTurn = 0;
      this.turnVariant = nextVariant;
      this.pendingTurnVariant = null;
      this.pendingTurnTarget = null;
      this.pendingHeadTurnTarget = null;
      this.targetPose = normalizePose({
        ...this.targetPose,
        turn: returnTarget,
        headTurn: returnHeadTarget,
      });
      if (!this.playing) {
        this.manualPose = normalizePose({
          ...this.manualPose,
          turn: returnTarget,
          headTurn: returnHeadTarget,
        });
      }
    }

    return this.currentTurn;
  }

  setDebugGrid(visible) {
    this.debugGridVisible = Boolean(visible);
    this.debugOverlay.visible = this.debugGridVisible;
  }

  getSessionElapsed() {
    return (performance.now() - this.sessionStartedAt) / 1000;
  }

  getScriptElapsed(now) {
    if (!this.script) return 0;
    const raw = (now - this.scriptStartedAt) / 1000;
    if (this.script.duration <= 0) return 0;
    return ((raw % this.script.duration) + this.script.duration) %
      this.script.duration;
  }

  getActiveCueIndex(elapsed) {
    if (!this.script) return -1;
    let active = 0;
    for (let index = 0; index < this.script.cues.length; index += 1) {
      if (this.script.cues[index].at <= elapsed) active = index;
      else break;
    }
    return active;
  }

  getAutoBlink(elapsed) {
    if (this.blinkStartedAt === null && elapsed >= this.nextBlinkAt) {
      this.blinkStartedAt = elapsed;
    }
    if (this.blinkStartedAt === null) return 0;

    const phase = elapsed - this.blinkStartedAt;
    const duration = 0.18;
    if (phase >= duration) {
      this.blinkStartedAt = null;
      this.nextBlinkAt = elapsed + 2.7 + Math.random() * 3.1;
      return 0;
    }
    return Math.sin((phase / duration) * Math.PI);
  }

  layout() {
    if (!this.app || !this.sceneGroup) return;
    const viewportWidth = this.app.screen.width;
    const viewportHeight = this.app.screen.height;
    if (viewportWidth <= 0 || viewportHeight <= 0) return;

    const zoom = this.framing === "short" ? 1.05 : 1.04;
    const focusY = this.framing === "short" ? 0.43 : 0.4;
    const targetY = this.framing === "short" ? 0.48 : 0.5;
    const scale =
      Math.max(
        viewportWidth / CANVAS_WIDTH,
        viewportHeight / CANVAS_HEIGHT,
      ) * zoom;

    this.sceneGroup.scale.set(scale);
    this.sceneGroup.position.set(
      viewportWidth * 0.5 - CANVAS_WIDTH * 0.5 * scale,
      viewportHeight * targetY - CANVAS_HEIGHT * focusY * scale,
    );
  }

  applyPose(renderPose, elapsed, audioLevel) {
    const isHeadOnly = this.turnVariant === "head-only";
    const isParameterReview = this.turnVariant === "parameter";
    const usesBodyAtlas = ["parameter", "full"].includes(this.turnVariant);
    const usesNeckAtlas = ["parameter", "natural"].includes(this.turnVariant);
    this.lastTurnBridgeVisuals = resolveTurnBridgeVisuals(
      this.turnTransitionState,
    );
    this.lastTurnWeights = selectTurnTransitionPoseWeights(
      this.turnTransitionState,
      this.turnVariant,
    );
    this.lastHeadTurnFrameBlend = selectHeadTurnFrameBlend(
      isParameterReview
        ? this.currentHeadTurn
        : this.turnVariant === "natural"
          ? this.currentTurn
          : 0,
      HEAD_TURN_ATLAS_LAYOUT.frameCount,
      this.headTurnSettleState.settled,
    );
    this.lastBodyTurnFrameBlend = selectBodyTurnFrameBlend(
      usesBodyAtlas ? this.currentTurn : 0,
      BODY_TURN_ATLAS_LAYOUT.frameCount,
      this.bodyTurnSettleState.settled,
    );
    this.lastSideGazeOffset = resolveSideGazeOffset(
      renderPose.gazeX,
      renderPose.gazeY,
    );
    this.lastSideGazeLayerAlpha = resolveSideGazeLayerAlpha(
      renderPose.gazeX,
      renderPose.gazeY,
    );
    this.lastHairFollow = usesBodyAtlas || usesNeckAtlas
      ? 0
      : resolveHairFollow(renderPose);
    const localizedStrength = isHeadOnly
      ? 1
      : this.turnVariant === "natural"
        ? 0.72
      : this.turnVariant === "soft"
        ? 0.4
        : 0.58;
    const localizedOffsets = resolveHeadOnlyOffsets(
      renderPose.turn * localizedStrength + renderPose.headTurn,
    );
    const usesLocalizedHead =
      isHeadOnly || this.turnVariant === "soft";
    const localizesManualHead = isHeadOnly;
    const basePose = localizesManualHead
      ? normalizePose({
          ...renderPose,
          headX: 0,
          headY: 0,
          headTilt: 0,
        })
      : renderPose;
    const transforms = computeLayerTransforms(basePose, elapsed);
    applyTransform(
      this.frontGroup,
      this.anchors.base,
      transforms.base,
    );

    if (usesLocalizedHead) {
      const localizedPose = normalizePose({
        ...renderPose,
        headX:
          (localizesManualHead ? renderPose.headX : 0) + localizedOffsets.headX,
        headY: localizesManualHead ? renderPose.headY : 0,
        headTilt:
          (localizesManualHead ? renderPose.headTilt : 0) +
          localizedOffsets.headTilt,
        blink: 0,
        gazeX: 0,
        gazeY: 0,
        mouthOpen: 0,
        smile: 0,
        speech: 0,
        breath: 0,
        shoulderSway:
          isParameterReview
            ? renderPose.shoulderSway
            : this.turnVariant === "natural"
              ? renderPose.turn * 0.32
              : 0,
        handAccent: 0,
        bookBob: 0,
        hairSway: renderPose.hairSway,
      });
      this.frontBaseMesh.vertices = deformGrid(
        this.frontGrid.positions,
        this.frontGrid.columns,
        this.frontGrid.rows,
        this.frontGrid.width,
        this.frontGrid.height,
        localizedPose,
        elapsed,
        {
          lockBody:
            this.turnVariant !== "natural" && !isParameterReview,
          deformHair: !isParameterReview,
        },
      );
      this.frontMeshIsDeformed = true;
      applyTransform(this.faceGroup, this.anchors.face, {
        x: localizedPose.headX * 8.5,
        y: localizedPose.headY * 6.2,
        rotation: localizedPose.headTilt * 0.035,
        scaleX: 1,
        scaleY: 1,
      });
    } else {
      if (this.frontMeshIsDeformed) {
        this.frontBaseMesh.vertices = this.frontGrid.positions.slice();
        this.frontMeshIsDeformed = false;
      }
      applyTransform(this.faceGroup, this.anchors.face, {
        x: 0,
        y: 0,
        rotation: 0,
        scaleX: 1,
        scaleY: 1,
      });
    }

    applyTransform(
      this.irisGroup,
      this.anchors.iris,
      transforms.iris,
    );
    applyTransform(
      this.browGroup,
      this.anchors.brow,
      transforms.brow,
    );

    const blink = Math.max(
      renderPose.blink,
      this.turnTransitionState.blink,
    );
    this.lastFrontBlinkWeights = selectFrontBlinkWeights(blink);
    this.layers.eyeOpen.alpha = this.lastFrontBlinkWeights.iris;
    this.irisGroup.alpha = this.lastFrontBlinkWeights.iris;
    this.layers.eyesHalf.alpha = this.lastFrontBlinkWeights.half;
    this.layers.eyesClosed.alpha = this.lastFrontBlinkWeights.closed;

    const hasManualWideOverride =
      !this.playing && this.manualPose.mouthOpen > QUIET_MOUTH_OPEN_LIMIT;
    const usesAutomaticSpeech =
      !hasManualWideOverride &&
      (this.playing || renderPose.speech > 0 || audioLevel > 0);
    const mouthOpen = resolveMouthOpen(
      renderPose,
      elapsed,
      audioLevel,
      usesAutomaticSpeech ? QUIET_MOUTH_OPEN_LIMIT : 1,
    );
    this.lastMouthWeights = selectFrontMouthWeights(
      mouthOpen,
      this.mouthVowel,
    );
    this.layers.mouthClosed.alpha = this.lastMouthWeights.closed;
    this.layers.mouthMicro.alpha = this.lastMouthWeights.micro;
    this.layers.mouthSmall.alpha = this.lastMouthWeights.small;
    this.layers.mouthWide.alpha = this.lastMouthWeights.wide;
    for (const vowel of ["A", "I", "U", "E", "O"]) {
      this.layers[`mouth${vowel}`].alpha =
        this.lastMouthWeights[vowel.toLowerCase()];
    }

    const sideMouthOpen = resolveSideMouthBlend(mouthOpen);
    this.lastSideExpressionWeights = selectSideExpressionWeights(
      resolveSideBlinkBlend(blink),
      sideMouthOpen,
    );
    this.lastSideExpressionAlphas = selectSideExpressionAlphas(
      this.lastSideExpressionWeights,
    );
    this.applyTurnPoseVisibility();
    const bodySequenceApplied = this.applyBodyTurnSequence();
    const headSequenceApplied = bodySequenceApplied
      ? false
      : this.applyHeadTurnSequence();

    this.sideMotionLocked =
      (bodySequenceApplied && this.bodyTurnSettleState.settled) ||
      (headSequenceApplied && this.headTurnSettleState.settled);

    const sideMotion = this.sideMotionLocked
      ? { x: 0, y: 0, rotation: 0, scaleX: 1, scaleY: 1 }
      : {
          x: transforms.base.x * 0.35,
          y: transforms.base.y * 0.55,
          rotation: transforms.base.rotation * 0.32,
          scaleX: 1 + (transforms.base.scaleX - 1) * 0.5,
          scaleY: 1 + (transforms.base.scaleY - 1) * 0.5,
        };
    for (const [group, anchorKey] of [
      [this.headTurnGroups.left, "headTurnLeftGroup"],
      [this.headTurnGroups.right, "headTurnRightGroup"],
      [this.bodyTurnGroups.left, "bodyTurnLeftGroup"],
      [this.bodyTurnGroups.right, "bodyTurnRightGroup"],
    ]) {
      applyTransform(group, this.anchors[anchorKey], sideMotion);
    }
  }

  tick(deltaSeconds) {
    const now = performance.now();
    const elapsed = this.getSessionElapsed();
    const layoutSize = `${this.app.screen.width}x${this.app.screen.height}`;
    if (layoutSize !== this.lastLayoutSize) {
      this.lastLayoutSize = layoutSize;
      this.layout();
    }

    if (this.script && this.playing) {
      this.scriptElapsed = this.getScriptElapsed(now);
      this.targetPose = sampleDirectorScript(this.script, this.scriptElapsed);
    }

    const smoothing = 1 - Math.exp(-Math.min(deltaSeconds, 0.05) * 8.5);
    this.currentPose = blendPose(
      this.currentPose,
      this.targetPose,
      smoothing,
    );
    this.advanceTurnTransition(deltaSeconds);
    const renderPose = normalizePose({
      ...this.currentPose,
      turn: this.currentTurn,
      headTurn: this.currentHeadTurn,
      blink: Math.max(this.currentPose.blink, this.getAutoBlink(elapsed)),
    });

    this.lastAudioLevel = Math.max(
      0,
      Math.min(1, Number(this.audioLevelSource?.()) || 0),
    );
    this.applyPose(renderPose, elapsed, this.lastAudioLevel);

    this.onUpdate?.({
      pose: renderPose,
      elapsed: this.scriptElapsed,
      duration: this.script?.duration ?? 0,
      playing: this.playing,
      cueIndex: this.getActiveCueIndex(this.scriptElapsed),
      audioLevel: this.lastAudioLevel,
      mouthWeights: this.lastMouthWeights,
      sideExpressionWeights: this.lastSideExpressionWeights,
      sideExpressionAlphas: this.lastSideExpressionAlphas,
      turnWeights: this.lastTurnWeights,
      headTurnFrameBlend: this.lastHeadTurnFrameBlend,
      headTurnSequenceActive: this.headTurnSequenceActive,
      bodyTurnFrameBlend: this.lastBodyTurnFrameBlend,
      bodyTurnSequenceActive: this.bodyTurnSequenceActive,
      headTurnSettled: this.headTurnSettleState.settled,
      bodyTurnSettled: this.bodyTurnSettleState.settled,
      sideMotionLocked: this.sideMotionLocked,
      sideGazeOffset: this.lastSideGazeOffset,
      sideGazeLayerAlpha: this.lastSideGazeLayerAlpha,
      hairFollow: this.lastHairFollow,
      mouthVowel: this.mouthVowel,
      turnVariant: this.turnVariant,
      pendingTurnVariant: this.pendingTurnVariant,
      pendingTurnTarget: this.pendingTurnTarget,
      pendingHeadTurnTarget: this.pendingHeadTurnTarget,
      turnTransition: { ...this.turnTransitionState },
      fps: Math.round(this.app.ticker.FPS || 0),
    });
  }

  destroy() {
    this.resizeObserver?.disconnect();
    this.app?.destroy(true, {
      children: true,
      texture: false,
      textureSource: false,
    });
  }
}
