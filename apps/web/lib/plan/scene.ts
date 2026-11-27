import type { HomePreset } from "./homePresets";
import { newUuid } from "../uuid";
import type { Pt } from "./model";
import { dimensions, tvDimensions, type ObjectKind } from "./furnitureCatalog";
export type { ObjectKind } from "./furnitureCatalog";

export type View = { id: string; name: string; position: Pt; yaw: number; pitch: number;
  horizontalFov: number; eyeHeight: number };
export type Item = { id: string; kind: ObjectKind; position: Pt; rotation: number;
  width: number; depth: number; height: number; mattressWidth?: number | null; mattressDepth?: number | null };
export const floorFinishes = {
  default: {name:"Original",color:"#dbe2d8",roughness:1},
  oak: {name:"Warm oak",color:"#bf946d",roughness:.65},
  slate: {name:"Dark slate",color:"#535c63",roughness:.83},
  limestone: {name:"Pale limestone",color:"#e4dac6",roughness:.74},
};
export type FloorFinish = keyof typeof floorFinishes;
export type FloorMaterial = { kind: "wood" | "concrete" | "marble" | "tile"; color: string; widthM: number; lengthM: number };
export type WallSide = "a" | "b";
export type WallMaterial = {kind:"paint"|"tile";color:string};
export type Scene = {
  designPreset?: HomePreset | null;
  floorFinish?: FloorFinish;
  floorMaterial?: FloorMaterial | null;
  roomFloorMaterials?: Record<string, FloorMaterial>;
  wallFinishes?: Record<string, Partial<Record<WallSide,WallMaterial|null>>>;
  views: View[]; objects: Item[]; style: string; closedDoorIds?: string[]; dismissedFixtureIds?: string[];
};
export type Saved = { revision: number; planRevision: number | null; config: Scene };
export type Frame = { width: number; height: number; configured: boolean; model: string; provider: string };
export type Job = { id: string; viewId: string; name: string; prompt: string; model: string;
  sceneRevision: number; compatibleSceneRevision?: number; planRevision: number; status: string; error: string | null };
export type VisibleRegion = { pixels:number; boundsXY:[number,number,number,number]; depthMm:[number,number] };
export type Capture = { preview: string; depth: string; mask: string; coverage: Record<number, number>; visibleRegions:Record<number,VisibleRegion>; fingerprint: string };

export function newItem(kind: ObjectKind, position: Pt): Item {
  const size = dimensions(kind);
  return { id: newUuid(), kind, position, rotation: 0, ...size,
    ...(kind==="tv"?tvDimensions(55):{}),
    mattressWidth:kind==="bed"?1.8:null, mattressDepth:kind==="bed"?2:null };
}

export function itemBottom(item: Pick<Item,"kind"|"height">) {
  if (item.kind==="cooktop") return .91;
  if (item.kind==="tv") return 1.27-item.height/2;
  if (item.kind==="console_floating") return .26;
  return 0;
}

export function obstructsMovement(item: Item) {
  return item.kind!=="rug" && item.kind!=="tv" && item.kind!=="cooktop";
}

export function promptFor(view: View, facts: string[], style: string) {
  return [
    "Scene facts: Photorealistic interior from the supplied camera view.",
    `Eye height ${view.eyeHeight.toFixed(2)} m; horizontal field of view ${view.horizontalFov} degrees.`,
    ...facts,
    "Preserve the camera, walls, existing openings, visible object positions and proportions. Do not add architectural openings or reveal objects behind walls.",
    "Apply each requested finish only to the named visible room or object. Do not bring an out-of-view room or fixture into the image to satisfy the design request.",
    `Style: ${style.trim() || "Warm natural finishes, soft daylight, realistic materials."}`,
  ].join("\n");
}

export function contains(p: Pt, polygon: Pt[]) {
  let hit = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const a = polygon[i], b = polygon[j];
    if ((a.y > p.y) !== (b.y > p.y) && p.x < (b.x - a.x) * (p.y - a.y) / (b.y - a.y) + a.x) hit = !hit;
  }
  return hit;
}
export function footprint(o: Item, scale: number): Pt[] {
  const a = o.rotation * Math.PI / 180;
  return [[-1,-1],[1,-1],[1,1],[-1,1]].map(([x,y]) => {
    const u=x*o.width/2/scale, v=y*o.depth/2/scale;
    return {x:o.position.x+u*Math.cos(a)-v*Math.sin(a),y:o.position.y+u*Math.sin(a)+v*Math.cos(a)};
  });
}

export function groundFootprint(item:Item,scale:number) {
  return footprint(item.kind==="parasol"?{...item,width:item.width*.19,depth:item.depth*.19}:item,scale);
}

export function intersects(a: Pt[], b: Pt[]) {
  return [a,b].every(poly => poly.every((p,i) => {
    const q = poly[(i+1)%poly.length], x = q.y-p.y, y = p.x-q.x;
    const aa = a.map(r=>r.x*x+r.y*y), bb = b.map(r=>r.x*x+r.y*y);
    return Math.max(...aa)>Math.min(...bb) && Math.max(...bb)>Math.min(...aa);
  }));
}
