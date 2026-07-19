import { normalizePose } from "./pose.js";

const LANDMARKS = Object.freeze({
  head: { x: 0.49, y: 0.255, rx: 0.285, ry: 0.245 },
  eyeScreenLeft: { x: 0.421, y: 0.27, rx: 0.078, ry: 0.04 },
  eyeScreenRight: { x: 0.543, y: 0.26, rx: 0.078, ry: 0.04 },
  mouth: { x: 0.483, y: 0.312, rx: 0.07, ry: 0.028 },
  torso: { x: 0.49, y: 0.61, rx: 0.33, ry: 0.34 },
  shoulderScreenLeft: { x: 0.29, y: 0.48, rx: 0.2, ry: 0.13 },
  shoulderScreenRight: { x: 0.69, y: 0.46, rx: 0.19, ry: 0.14 },
  raisedHand: { x: 0.125, y: 0.525, rx: 0.12, ry: 0.16 },
  bookHand: { x: 0.39, y: 0.655, rx: 0.16, ry: 0.14 },
  hairScreenLeft: { x: 0.25, y: 0.52, rx: 0.23, ry: 0.38 },
  hairScreenRight: { x: 0.73, y: 0.52, rx: 0.23, ry: 0.38 },
  hairCrown: { x: 0.49, y: 0.19, rx: 0.3, ry: 0.17 },
});

export function createGrid(width, height, columns, rows) {
  if (columns < 2 || rows < 2) {
    throw new RangeError("grid needs at least 2 columns and 2 rows");
  }

  const positions = new Float32Array(columns * rows * 2);
  const uvs = new Float32Array(columns * rows * 2);
  const indices = new Uint32Array((columns - 1) * (rows - 1) * 6);
  let vertexOffset = 0;

  for (let row = 0; row < rows; row += 1) {
    const v = row / (rows - 1);
    for (let column = 0; column < columns; column += 1) {
      const u = column / (columns - 1);
      positions[vertexOffset] = u * width;
      positions[vertexOffset + 1] = v * height;
      uvs[vertexOffset] = u;
      uvs[vertexOffset + 1] = v;
      vertexOffset += 2;
    }
  }

  let indexOffset = 0;
  for (let row = 0; row < rows - 1; row += 1) {
    for (let column = 0; column < columns - 1; column += 1) {
      const topLeft = row * columns + column;
      const topRight = topLeft + 1;
      const bottomLeft = topLeft + columns;
      const bottomRight = bottomLeft + 1;

      indices[indexOffset] = topLeft;
      indices[indexOffset + 1] = topRight;
      indices[indexOffset + 2] = bottomRight;
      indices[indexOffset + 3] = topLeft;
      indices[indexOffset + 4] = bottomRight;
      indices[indexOffset + 5] = bottomLeft;
      indexOffset += 6;
    }
  }

  return { positions, uvs, indices, columns, rows, width, height };
}

function regionWeight(nx, ny, region) {
  const dx = (nx - region.x) / region.rx;
  const dy = (ny - region.y) / region.ry;
  const distanceSquared = dx * dx + dy * dy;
  if (distanceSquared >= 1) return 0;
  const remainder = 1 - distanceSquared;
  return remainder * remainder;
}

function smoothstep(edge0, edge1, value) {
  const normalized = Math.min(
    1,
    Math.max(0, (value - edge0) / (edge1 - edge0)),
  );
  return normalized * normalized * (3 - 2 * normalized);
}

function edgePinWeight(nx, ny) {
  return (
    smoothstep(0, 0.075, nx) *
    smoothstep(0, 0.075, ny) *
    smoothstep(0, 0.075, 1 - nx) *
    smoothstep(0, 0.075, 1 - ny)
  );
}

function rotateAround(x, y, cx, cy, radians) {
  const dx = x - cx;
  const dy = y - cy;
  const cosine = Math.cos(radians);
  const sine = Math.sin(radians);
  return {
    x: cx + dx * cosine - dy * sine,
    y: cy + dx * sine + dy * cosine,
  };
}

function applyEyeMotion(nx, ny, pose, eye, height) {
  const weight = regionWeight(nx, ny, eye);
  if (weight === 0) return { dx: 0, dy: 0 };

  const centerLine = eye.y;
  const closeDelta =
    (centerLine - ny) * height * pose.blink * 0.82 * weight;
  return {
    dx: pose.gazeX * 4.2 * weight,
    dy: closeDelta + pose.gazeY * 2.8 * weight,
  };
}

export function deformGrid(
  basePositions,
  columns,
  rows,
  width,
  height,
  inputPose,
  elapsedSeconds = 0,
  options = {},
) {
  if (basePositions.length !== columns * rows * 2) {
    throw new RangeError("basePositions length does not match grid dimensions");
  }

  const pose = normalizePose(inputPose);
  const lockBody = Boolean(options?.lockBody);
  const deformHair = options?.deformHair !== false;
  const output = new Float32Array(basePositions.length);
  const seconds = Number.isFinite(elapsedSeconds) ? elapsedSeconds : 0;
  const idleSway = Math.sin(seconds * 0.72) * 0.16;
  const breathing = Math.sin(seconds * 1.34) * pose.breath;
  const speechPulse =
    pose.speech *
    (0.22 +
      Math.abs(Math.sin(seconds * 11.7)) * 0.5 +
      Math.abs(Math.sin(seconds * 7.1 + 0.9)) * 0.28);
  const mouthOpen = Math.min(1, Math.max(pose.mouthOpen, speechPulse));

  for (let index = 0; index < columns * rows; index += 1) {
    const sourceX = basePositions[index * 2];
    const sourceY = basePositions[index * 2 + 1];
    const nx = sourceX / width;
    const ny = sourceY / height;
    let dx = 0;
    let dy = 0;

    const torsoWeight = regionWeight(nx, ny, LANDMARKS.torso);
    dx +=
      ((lockBody ? 0 : pose.headX * 1.5) + idleSway * 2.3) *
      torsoWeight;
    dy += breathing * -4.1 * torsoWeight;

    const headWeight = regionWeight(nx, ny, LANDMARKS.head);
    if (headWeight > 0) {
      const headCenterX = LANDMARKS.head.x * width;
      const headCenterY = LANDMARKS.head.y * height;
      const angle = (pose.headTilt * 0.035 + idleSway * 0.012) * headWeight;
      const rotated = rotateAround(
        sourceX,
        sourceY,
        headCenterX,
        headCenterY,
        angle,
      );
      dx +=
        (rotated.x - sourceX) +
        (pose.headX * 8.5 + idleSway * 2.4) * headWeight;
      dy +=
        (rotated.y - sourceY) +
        (pose.headY * 6.2 + breathing * -1.4) * headWeight;
    }

    const leftShoulderWeight = regionWeight(
      nx,
      ny,
      LANDMARKS.shoulderScreenLeft,
    );
    const rightShoulderWeight = regionWeight(
      nx,
      ny,
      LANDMARKS.shoulderScreenRight,
    );
    dy += pose.shoulderSway * 3.4 * leftShoulderWeight;
    dy -= pose.shoulderSway * 3.4 * rightShoulderWeight;
    if (!lockBody) {
      dy -= pose.turn * 3.8 * leftShoulderWeight;
      dy += pose.turn * 3.8 * rightShoulderWeight;
      dx += pose.turn * (ny - LANDMARKS.torso.y) * 8 * torsoWeight;
    }

    const handWeight = regionWeight(nx, ny, LANDMARKS.raisedHand);
    dx += pose.handAccent * -2.4 * handWeight;
    dy += pose.handAccent * -8.2 * handWeight;

    const bookWeight = regionWeight(nx, ny, LANDMARKS.bookHand);
    dy += pose.bookBob * -5.5 * bookWeight;
    dx += pose.bookBob * 1.4 * bookWeight;

    if (deformHair) {
      const linkedHairSway = Math.max(
        -1,
        Math.min(
          1,
          pose.hairSway -
            pose.headTurn * 0.68 -
            pose.headX * 0.18 -
            pose.headTilt * 0.22 -
            pose.turn * 0.18,
        ),
      );
      const leftHairWeight = regionWeight(nx, ny, LANDMARKS.hairScreenLeft);
      const rightHairWeight = regionWeight(nx, ny, LANDMARKS.hairScreenRight);
      const hairWeight = Math.max(leftHairWeight, rightHairWeight);
      const crownWeight = regionWeight(nx, ny, LANDMARKS.hairCrown);
      const hairWave =
        linkedHairSway * 11.5 + Math.sin(seconds * 1.08 + ny * 7) * 1.1;
      const tailWeight = smoothstep(0.22, 0.72, ny);
      dx += hairWave * hairWeight * tailWeight;
      dy += Math.abs(linkedHairSway) * 2.1 * hairWeight * tailWeight;
      dx += linkedHairSway * 2.8 * crownWeight;
    }

    const leftEyeMotion = applyEyeMotion(
      nx,
      ny,
      pose,
      LANDMARKS.eyeScreenLeft,
      height,
    );
    const rightEyeMotion = applyEyeMotion(
      nx,
      ny,
      pose,
      LANDMARKS.eyeScreenRight,
      height,
    );
    dx += leftEyeMotion.dx + rightEyeMotion.dx;
    dy += leftEyeMotion.dy + rightEyeMotion.dy;

    const mouthWeight = regionWeight(nx, ny, LANDMARKS.mouth);
    if (mouthWeight > 0) {
      const mouthCenterY = LANDMARKS.mouth.y * height;
      const signedDistance = sourceY - mouthCenterY;
      dy += signedDistance * mouthOpen * 0.62 * mouthWeight;
      dy -= pose.smile * 2.4 * mouthWeight;
      dx +=
        Math.sign(sourceX - LANDMARKS.mouth.x * width) *
        pose.smile *
        1.7 *
        mouthWeight;
    }

    const pin = edgePinWeight(nx, ny);
    output[index * 2] = sourceX + dx * pin;
    output[index * 2 + 1] = sourceY + dy * pin;
  }

  return output;
}

export function findNearestVertex(
  positions,
  columns,
  rows,
  targetX,
  targetY,
) {
  let nearestIndex = 0;
  let nearestDistance = Number.POSITIVE_INFINITY;
  const count = columns * rows;

  for (let index = 0; index < count; index += 1) {
    const dx = positions[index * 2] - targetX;
    const dy = positions[index * 2 + 1] - targetY;
    const distance = dx * dx + dy * dy;
    if (distance < nearestDistance) {
      nearestDistance = distance;
      nearestIndex = index;
    }
  }

  return nearestIndex;
}

export const RIG_LANDMARKS = LANDMARKS;
