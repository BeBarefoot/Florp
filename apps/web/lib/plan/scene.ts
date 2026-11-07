import type { Pt } from "./model";

export type View = { id: string; name: string; position: Pt; yaw: number; pitch: number;
  horizontalFov: number; eyeHeight: number };
export type ObjectKind = "bed" | "wardrobe" | "toilet" | "vanity" | "shower" | "bathtub";
export type Item = { id: string; kind: ObjectKind; position: Pt; rotation: number;
  width: number; depth: number; height: number; mattressWidth?: number | null; mattressDepth?: number | null };
export type Scene = { views: View[]; objects: Item[]; style: string; closedDoorIds?: string[]; dismissedFixtureIds?: string[] };
export type Saved = { revision: number; planRevision: number | null; config: Scene };
export type Frame = { width: number; height: number; configured: boolean; model: string; provider: string };
export type Job = { id: string; viewId: string; name: string; prompt: string; model: string;
  sceneRevision: number; planRevision: number; status: string; error: string | null };
export type Capture = { preview: string; depth: string; mask: string; coverage: Record<number, number>; fingerprint: string };

export const catalog: Record<ObjectKind, [number, number, number]> = {
  bed: [1.9, 2.12, .9], toilet: [.38, .68, .8], shower: [.9, .9, 2],
  bathtub: [.75, 1.7, .56], wardrobe: [1.8, .62, 2.2], vanity: [.8, .5, .86],
};
export function newItem(kind: ObjectKind, position: Pt): Item {
  const [width, depth, height] = catalog[kind];
  return { id: crypto.randomUUID(), kind, position, rotation: 0, width, depth, height,
    mattressWidth:kind==="bed"?1.8:null, mattressDepth:kind==="bed"?2:null };
}

type Block = { position: [number, number, number]; size: [number, number, number]; color: string };
export function blocks(o: Item): Block[] {
  const {width: w, depth: d, height: h} = o;
  const part = (x: number, y: number, z: number, a: number, b: number, c: number, color: string): Block =>
    ({ position: [x*w,y*h,z*d], size: [a*w,b*h,c*d], color });
  switch (o.kind) {
    case "bed": return [
      part(0,.16,0,1,.32,1,"#87694f"), part(0,.5,-.48,1,1,.04,"#87694f"),
      part(0,.46,.02,(o.mattressWidth ?? w)/w,.28,(o.mattressDepth ?? d*.95)/d,"#eee7d4"),
      part(-.22,.64,-.31,.34,.08,.19,"#faf5e8"), part(.22,.64,-.31,.34,.08,.19,"#faf5e8"),
    ];
    case "toilet": return [part(0,.22,.1,.7,.44,.63,"#f5f7f4"),part(0,.55,-.31,1,.9,.32,"#f5f7f4"),part(0,.54,.1,1,.18,.74,"#fafcfb")];
    case "shower": return [part(0,.025,0,1,.05,1,"#dbebe5"),part(-.48,.5,0,.04,1,1,"#8eb7bd"),part(.48,.5,.46,.04,1,.08,"#8eb7bd")];
    case "bathtub": return [part(0,.08,0,1,.16,1,"#fafcfb"),...[-.45,.45].flatMap(v=>[
      part(v,.56,0,.1,.88,1,"#edf4ef"),part(0,.56,v,.8,.88,.1,"#edf4ef")])];
    case "vanity": return [part(0,.44,0,1,.88,1,"#927861"),part(0,.94,0,1,.12,1,"#f2efea"),part(0,.986,0,.48,.028,.52,"#b0c7c6")];
    default: return [part(0,.5,0,1,1,1,"#b59b83"),part(0,.5,.497,.01,.95,.008,"#806956")];
  }
}

export function promptFor(view: View, facts: string[], style: string) {
  return [
    "Scene facts: Photorealistic interior from the supplied depth view.",
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

export function intersects(a: Pt[], b: Pt[]) {
  return [a,b].every(poly => poly.every((p,i) => {
    const q = poly[(i+1)%poly.length], x = q.y-p.y, y = p.x-q.x;
    const aa = a.map(r=>r.x*x+r.y*y), bb = b.map(r=>r.x*x+r.y*y);
    return Math.max(...aa)>Math.min(...bb) && Math.max(...bb)>Math.min(...aa);
  }));
}
