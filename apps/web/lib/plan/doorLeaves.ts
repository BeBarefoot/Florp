import {openingEnds} from "./derive";
import type {PlanModel} from "./model";

export function doorLeaves(plan: PlanModel, scale: number, closedIds?: string[]) {
  return plan.openings.flatMap(opening => {
    if (opening.status !== "confirmed" || opening.kind !== "door" || opening.passage) return [];
    const closed = closedIds?.includes(opening.id);
    if (!opening.swing && !closed) return [];
    const ends = openingEnds(plan, opening);
    if (!ends) return [];
    const [a, b] = ends;
    const length = Math.hypot(b.x - a.x, b.y - a.y) * scale;
    const angle = Math.atan2(b.y - a.y, b.x - a.x);
    const end = opening.hinge === "end";
    const hinge = end ? b : a;
    const swing = closed ? (end ? Math.PI : 0) : (opening.swing === "left" ? 1 : -1) * Math.PI / 2;
    return [{id: opening.id, x: hinge.x * scale, z: hinge.y * scale, angle: -(angle + swing),
      length, height: opening.heightM}];
  });
}
