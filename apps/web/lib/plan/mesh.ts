// Metric 3D wall pieces from a PlanModel. Shared by the live viewer and glTF export.
import type { PlanModel, Pt } from "./model";
import { metersPerPixel, nodeMap, wallEnds } from "./derive";

export type Chunk = { start: number; end: number; low: number; high: number };
export type WallPiece = {
  id: string;
  centre: [number, number];
  angle: number;
  lengthM: number;
  thicknessM: number;
  heightM: number;
  material: "block" | "concrete";
  chunks: Chunk[];
};

export function wallPieces(m: PlanModel): WallPiece[] {
  const s = metersPerPixel(m);
  if (!s) return [];
  const nodes = nodeMap(m);
  return m.walls.map((w) => {
    const [a, b] = wallEnds(m, w, nodes);
    const dx = b.x - a.x,
      dz = b.y - a.y;
    const length = Math.hypot(dx, dz) * s;
    const cuts = m.openings
      .filter((o) => o.hostWallId === w.id && o.status === "confirmed")
      .sort((x, y) => x.offsetPx - y.offsetPx);
    const chunks: Chunk[] = [];
    let cursor = 0;
    for (const o of cuts) {
      const start = Math.max(cursor, Math.min(length, o.offsetPx * s));
      const end = Math.min(length, start + o.widthPx * s);
      if (start > cursor + 0.001) chunks.push({ start: cursor, end: start, low: 0, high: w.heightM });
      if (end > start) {
        if (o.sillM > 0.001) chunks.push({ start, end, low: 0, high: Math.min(o.sillM, w.heightM) });
        const top = o.sillM + o.heightM;
        if (top < w.heightM - 0.001) chunks.push({ start, end, low: top, high: w.heightM });
      }
      cursor = Math.max(cursor, end);
    }
    if (cursor < length - 0.001) chunks.push({ start: cursor, end: length, low: 0, high: w.heightM });
    return {
      id: w.id,
      centre: [((a.x + b.x) / 2) * s, ((a.y + b.y) / 2) * s],
      angle: -Math.atan2(dz, dx),
      lengthM: length,
      thicknessM: w.thicknessPx * s,
      heightM: w.heightM,
      material: w.material,
      chunks: chunks.filter((c) => c.end - c.start > 0.001 && c.high - c.low > 0.001),
    };
  });
}

export function floorOutlines(m: PlanModel): { id: string; label: string | null; points: Pt[] }[] {
  const s = metersPerPixel(m);
  if (!s) return [];
  return m.rooms.map((r) => ({
    id: r.id,
    label: r.label,
    points: r.polygon.map((p) => ({ x: p.x * s, y: p.y * s })),
  }));
}

/** Compact, test-visible signature of the extruded geometry. */
export const meshSignature = (pieces: WallPiece[]) =>
  pieces.map((p) => p.lengthM.toFixed(3) + ":" + p.chunks.length).join(",");
