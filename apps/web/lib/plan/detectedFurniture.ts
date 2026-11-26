import type {PlanModel} from "./model";
import {dimensions, type ObjectKind} from "./furnitureCatalog";
import {contains, footprint, type Item} from "./scene";

type Symbol = NonNullable<PlanModel["roomSymbols"]>[number];
export const detectedKinds = {
  car: "car", tree: "tree", bed: "bed", sofa: "sofa", bar_stools: "bar_stools",
  cooktop: "cooktop", dining_table: "dining_6", coffee_table: "coffee_table",
  sink: "sink", toilet: "toilet", patio_set: "patio_set", cabinets: "cabinets",
  bathtub: "bathtub", shower: "shower", wardrobe: "wardrobe",
  tv_console: "console_standing", bar_counter: "island", fridge: "fridge",
} satisfies Record<Symbol["kind"], ObjectKind>;

export function hasDetectedFootprint(symbol: Symbol) {
  return (symbol.widthPx ?? 0) > 0 && (symbol.depthPx ?? 0) > 0;
}

export function detectedPreviewItems(plan: PlanModel, scale: number): Item[] {
  return (plan.roomSymbols ?? []).flatMap(symbol => {
    if (!hasDetectedFootprint(symbol)) return [];
    const kind = detectedKinds[symbol.kind];
    const {x, y} = symbol.position;
    return [{
      id: `detection-${kind}-${Math.round(x * 10)}-${Math.round(y * 10)}`,
      kind, position: symbol.position, rotation: symbol.rotation ?? 0,
      width: symbol.widthPx! * scale, depth: symbol.depthPx! * scale,
      height: dimensions(kind).height,
    }];
  });
}

export function visibleDetections(items: Item[], placed: Item[], scale: number, hidden: string[] = []) {
  return items.filter(item => !hidden.includes(item.id) && !placed.some(object =>
    object.id === item.id || (object.kind === item.kind &&
      contains(item.position, footprint(object, scale)) && contains(object.position, footprint(item, scale)))));
}
