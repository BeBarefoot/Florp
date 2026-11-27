import type { Alignment, PlanModel } from "./model";
import type { Scene } from "./scene";
import { metersPerPixel, wallFootprint } from "./derive";

type Level = { plan: PlanModel; scene: Scene };
export type HouseOverview = { ground: Level; upper: Level; alignment?: Alignment | null; provisionalOrder: boolean };

export function housePlacement({ ground, upper, alignment }: HouseOverview) {
  const groundScale = metersPerPixel(ground.plan)!;
  const upperScale = metersPerPixel(upper.plan)!;
  const groundBounds = wallFootprint(ground.plan, groundScale);
  const upperBounds = wallFootprint(upper.plan, upperScale);
  const groundImage = ground.plan.imageTransform;
  const upperImage = upper.plan.imageTransform;
  const upperCenter = [upperImage.width * upperScale / 2, upperImage.height * upperScale / 2] as const;
  const approximate = {
    centerX: groundImage.width / 2, centerY: groundImage.height / 2, rotationDeg: 0, scale: upperScale / groundScale,
  };
  if (groundBounds && upperBounds) {
    approximate.centerX = (groundBounds.left + groundBounds.right) / 2
      + (upperImage.width - upperBounds.left - upperBounds.right) / 2 * approximate.scale;
    approximate.centerY = (groundBounds.top + groundBounds.bottom) / 2
      + (upperImage.height - upperBounds.top - upperBounds.bottom) / 2 * approximate.scale;
  }
  const fit = alignment ?? approximate;
  const rotation = fit.rotationDeg * Math.PI / 180;
  const horizontalScale = fit.scale * groundScale / upperScale;
  const elevation = Math.max(0, ...ground.plan.walls.map(wall => wall.heightM),
    ...ground.plan.rooms.map(room => room.ceilingHeightM ?? 0)) || 2.8;
  const center = [fit.centerX * groundScale, elevation, fit.centerY * groundScale] as const;
  const upperCorners = [
    [upperBounds?.left ?? 0, upperBounds?.top ?? 0], [upperBounds?.right ?? upperImage.width, upperBounds?.top ?? 0],
    [upperBounds?.right ?? upperImage.width, upperBounds?.bottom ?? upperImage.height], [upperBounds?.left ?? 0, upperBounds?.bottom ?? upperImage.height],
  ].map(([px, py]) => {
    const x = (px * upperScale - upperCenter[0]) * horizontalScale;
    const z = (py * upperScale - upperCenter[1]) * horizontalScale;
    return [center[0] + x * Math.cos(rotation) - z * Math.sin(rotation),
      center[2] + x * Math.sin(rotation) + z * Math.cos(rotation)];
  });
  const xs = [0, groundImage.width * groundScale, ...upperCorners.map(point => point[0])];
  const zs = [0, groundImage.height * groundScale, ...upperCorners.map(point => point[1])];
  const left = Math.min(...xs), right = Math.max(...xs), top = Math.min(...zs), bottom = Math.max(...zs);
  return { center, elevation, upperCenter, horizontalScale, rotation,
    target: [(left + right) / 2, elevation, (top + bottom) / 2] as const,
    span: Math.max(right - left, bottom - top, elevation * 2) };
}
