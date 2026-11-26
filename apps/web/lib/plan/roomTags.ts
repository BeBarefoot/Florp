import type { PlanModel, Pt } from "./model";
import { contains } from "./scene";

function labelPosition(polygon: Pt[]): Pt | undefined {
  // Center the label on an inside span, including for L-shaped rooms.
  const ys = polygon.map(p => p.y);
  const y = (Math.min(...ys) + Math.max(...ys)) / 2;
  const crossings: number[] = [];
  polygon.forEach((a, i) => {
    const b = polygon[(i + 1) % polygon.length];
    if ((a.y > y) !== (b.y > y)) crossings.push(a.x + (y - a.y) * (b.x - a.x) / (b.y - a.y));
  });
  crossings.sort((a, b) => a - b);
  let width = 0, position: Pt | undefined;
  for (let i = 1; i < crossings.length; i += 2) {
    const span = crossings[i] - crossings[i - 1];
    if (span > width) {
      width = span;
      position = { x: crossings[i - 1] + span / 2, y };
    }
  }
  return position;
}

export function roomTags(plan: PlanModel) {
  const tags: { key: string; text: string; position: Pt }[] = [];
  const rooms = [...plan.rooms, ...(plan.roomZones ?? [])];
  for (const room of rooms) {
    if (!room.label) continue;
    const position = labelPosition(room.polygon);
    if (position) tags.push({ key: room.id, text: room.label, position });
  }
  for (const [index, symbol] of (plan.roomSymbols ?? []).entries()) {
    const labels = {car:"Car", bed:"Bed", sofa:"Sofa", dining_table:"Dining table", bar_stools:"Bar stools", cooktop:"Cooktop", coffee_table:"Coffee table", tree:"Tree", sink:"Sink", toilet:"Toilet", cabinets:"Cabinets", patio_set:"Patio dining set", bar_counter:"Bar counter", tv_console:"TV console", fridge:"Fridge"};
    if ((symbol.kind !== "car" && symbol.kind !== "bed") || !rooms.some(room => contains(symbol.position, room.polygon))) {
      tags.push({key: "symbol-" + index, text: labels[symbol.kind], position: symbol.position});
    }
  }
  return tags;
}
