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

type Vec = [number, number];
type OpeningVoid = {
  centre: Vec;
  along: Vec;
  normal: Vec;
  halfLength: number;
  halfThickness: number;
  low: number;
  high: number;
};
const dot = (a: Vec, b: Vec) => a[0] * b[0] + a[1] * b[1];

function openingVoids(m: PlanModel, scale: number): OpeningVoid[] {
  const nodes = nodeMap(m);
  const walls = new Map(m.walls.map((w) => [w.id, w]));
  const out: OpeningVoid[] = [];
  for (const o of m.openings) {
    if (o.status !== "confirmed" || !o.hostWallId) continue;
    const w = walls.get(o.hostWallId);
    if (!w) continue;
    const [a, b] = wallEnds(m, w, nodes);
    const length = Math.hypot(b.x - a.x, b.y - a.y);
    if (length < 1e-9) continue;
    const lo = Math.max(0, Math.min(length, o.offsetPx));
    const hi = Math.min(length, lo + o.widthPx);
    if (hi <= lo) continue;
    const along: Vec = [(b.x - a.x) / length, (b.y - a.y) / length];
    const centre = (lo + hi) / 2;
    out.push({
      centre: [(a.x + along[0] * centre) * scale, (a.y + along[1] * centre) * scale],
      along, normal: [-along[1], along[0]],
      halfLength: (hi - lo) * scale / 2,
      halfThickness: w.thicknessPx * scale / 2,
      low: Math.max(0, o.sillM), high: Math.min(w.heightM, o.sillM + o.heightM),
    });
  }
  return out;
}

/** First contact of a moving wall end face with an opening's oriented footprint.
 * Separating-axis intervals handle sloping walls without a world-axis bbox
 * approximation. Only newly added cap material is limited; source geometry
 * and opening offsets remain untouched.
 */
function capReach(p: Vec, direction: Vec, normal: Vec, halfWidth: number, voids: OpeningVoid[], low: number, high: number): number {
  let reach = halfWidth;
  for (const hole of voids) {
    if (hole.high <= low + 1e-8 || hole.low >= high - 1e-8) continue;
    let enter = 0, exit = reach;
    for (const axis of [direction, normal, hole.along, hole.normal]) {
      const centre = dot(hole.centre, axis) - dot(p, axis);
      const radius = hole.halfLength * Math.abs(dot(hole.along, axis))
        + hole.halfThickness * Math.abs(dot(hole.normal, axis))
        + halfWidth * Math.abs(dot(normal, axis));
      const speed = dot(direction, axis);
      if (Math.abs(speed) < 1e-10) {
        if (Math.abs(centre) > radius + 1e-10) { exit = -1; break; }
      } else {
        const r1 = (centre - radius) / speed, r2 = (centre + radius) / speed;
        enter = Math.max(enter, Math.min(r1, r2));
        exit = Math.min(exit, Math.max(r1, r2));
      }
      if (enter > exit) break;
    }
    if (enter <= exit && exit >= 0) reach = Math.max(0, Math.min(reach, enter - 1e-6));
  }
  return reach;
}

/** Match the editor's square line caps on solid end slabs, never on opening cuts. */
function closeWallEnds(pieces: WallPiece[], voids: OpeningVoid[], straightSeams: Map<string, Set<boolean>>): WallPiece[] {
  return pieces.map((piece) => {
    const along: Vec = [Math.cos(piece.angle), -Math.sin(piece.angle)];
    const normal: Vec = [-along[1], along[0]];
    const caps: Chunk[] = [];
    for (const chunk of piece.chunks) {
      for (const start of [true, false]) {
        // These runs already meet on one face. Overlapping caps here put
        // coplanar faces into the viewer and GLB along every jamb seam.
        if (straightSeams.get(piece.id)?.has(start)) continue;
        if (start ? Math.abs(chunk.start) > 1e-8 : Math.abs(chunk.end - piece.lengthM) > 1e-8) continue;
        const sign = start ? -1 : 1;
        const direction: Vec = [sign * along[0], sign * along[1]];
        const p: Vec = [piece.centre[0] + direction[0] * piece.lengthM / 2,
          piece.centre[1] + direction[1] * piece.lengthM / 2];
        // A neighbouring door may block only the bottom of a cap, while its
        // lintel can still join. Split at opening heights before limiting reach.
        const heights = [...new Set([chunk.low, chunk.high, ...voids.flatMap((v) => [v.low, v.high])])]
          .filter((y) => y >= chunk.low && y <= chunk.high).sort((a, b) => a - b);
        for (let i = 0; i + 1 < heights.length; i++) {
          const low = heights[i], high = heights[i + 1];
          if (high - low <= 1e-6) continue;
          const reach = capReach(p, direction, normal, piece.thicknessM / 2, voids, low, high);
          if (reach <= 1e-6) continue;
          caps.push({ start: start ? -reach : piece.lengthM,
            end: start ? 0 : piece.lengthM + reach, low, high });
        }
      }
    }
    return { ...piece, chunks: [...piece.chunks, ...caps] };
  });
}

export function wallPieces(m: PlanModel): WallPiece[] {
  const s = metersPerPixel(m);
  if (!s) return [];
  const nodes = nodeMap(m);
  const pieces: WallPiece[] = m.walls.map((w): WallPiece => {
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
  const incident = new Map<string, { id: string; start: boolean; direction: Vec }[]>();
  for (const w of m.walls) {
    const [a, b] = wallEnds(m, w, nodes);
    const length = Math.hypot(b.x - a.x, b.y - a.y);
    if (length < 1e-8) continue;
    for (const start of [true, false]) {
      const sign = start ? 1 : -1;
      const id = start ? w.a : w.b;
      const list = incident.get(id) ?? [];
      list.push({ id: w.id, start, direction: [sign * (b.x - a.x) / length, sign * (b.y - a.y) / length] });
      incident.set(id, list);
    }
  }
  const straightSeams = new Map<string, Set<boolean>>();
  for (const edges of incident.values()) {
    if (edges.length !== 2 || dot(edges[0].direction, edges[1].direction) > -1 + 1e-10) continue;
    for (const edge of edges) {
      const ends = straightSeams.get(edge.id) ?? new Set<boolean>();
      ends.add(edge.start);
      straightSeams.set(edge.id, ends);
    }
  }
  return closeWallEnds(pieces, openingVoids(m, s), straightSeams);
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
