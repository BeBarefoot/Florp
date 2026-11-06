import { Shape } from "three";
import { metersPerPixel } from "./derive";
import type { PlanModel } from "./model";

/** Identical measured tread footprints and rises in the viewer and GLB. */
export function stairPieces(model: PlanModel) {
  const scale = metersPerPixel(model);
  if (!scale) return [];
  return (model.stairs ?? []).map((stair) => ({
    id: stair.id,
    steps: stair.treads.map((tread, i) => {
      const shape = new Shape();
      tread.forEach((p, j) => j ? shape.lineTo(p.x * scale, -p.y * scale) : shape.moveTo(p.x * scale, -p.y * scale));
      shape.closePath();
      return { shape, height: (i + 1) * stair.riseM };
    }),
  }));
}
