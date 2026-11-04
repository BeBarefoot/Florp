/** The plan's metric X/Z plane is the viewer's floor; positive Y is up. */
export type FloorPoint = [x: number, z: number];
export type CameraPoint = [x: number, y: number, z: number];

export const DEFAULT_EYE_HEIGHT_M = 1.6;
export const CAMERA_VERTICAL_FOV_DEG = 55;

export function eyeLevelPose(origin: FloorPoint, aim: FloorPoint, eyeHeightM: number) {
  const dx = aim[0] - origin[0], dz = aim[1] - origin[1];
  const length = Math.hypot(dx, dz);
  if (!Number.isFinite(length) || length < 0.1 || !Number.isFinite(eyeHeightM) || eyeHeightM < 0.8 || eyeHeightM > 2.2) {
    return null;
  }
  const position: CameraPoint = [origin[0], eyeHeightM, origin[1]];
  const direction: CameraPoint = [dx / length, 0, dz / length];
  return { position, direction, verticalFovDeg: CAMERA_VERTICAL_FOV_DEG };
}
