// Mirrors apps/api/app/plan_derive.py rooms(); keep both implementations in step.
import type { PlanModel, Pt, Room, Wall, Node } from "./model";

const MIN_ROOM_PX2 = 400;

export function nodeMap(m: PlanModel): Map<string, Node> {
  return new Map(m.nodes.map((n) => [n.id, n]));
}
export function wallEnds(m: PlanModel, w: Wall, nodes = nodeMap(m)): [Pt, Pt] {
  return [nodes.get(w.a)!, nodes.get(w.b)!];
}
export function wallLength(m: PlanModel, w: Wall, nodes = nodeMap(m)): number {
  const [a, b] = wallEnds(m, w, nodes);
  return Math.hypot(b.x - a.x, b.y - a.y);
}
export function metersPerPixel(m: PlanModel): number | null {
  const r = m.scale.reference;
  if (!r) return null;
  const px = Math.hypot(r.p2.x - r.p1.x, r.p2.y - r.p1.y);
  return px >= 5 ? r.lengthMeters / px : null;
}
export const toM = (m: PlanModel, px: number) => {
  const s = metersPerPixel(m);
  return s ? px * s : null;
};
export const areaM2 = (m: PlanModel, px2: number) => {
  const s = metersPerPixel(m);
  return s ? px2 * s * s : null;
};
export function openingEnds(m: PlanModel, o: PlanModel["openings"][number], nodes = nodeMap(m)): [Pt, Pt] | null {
  const w = m.walls.find((x) => x.id === o.hostWallId);
  if (!w) return o.span;
  const [a, b] = wallEnds(m, w, nodes);
  const l = Math.hypot(b.x - a.x, b.y - a.y) || 1;
  const ux = (b.x - a.x) / l,
    uy = (b.y - a.y) / l;
  return [
    { x: a.x + ux * o.offsetPx, y: a.y + uy * o.offsetPx },
    { x: a.x + ux * (o.offsetPx + o.widthPx), y: a.y + uy * (o.offsetPx + o.widthPx) },
  ];
}

function signedArea(p: Pt[]): number {
  let s = 0;
  for (let i = 0; i < p.length; i++) {
    const q = p[(i + 1) % p.length];
    s += p[i].x * q.y - q.x * p[i].y;
  }
  return s / 2;
}

export function faces(m: PlanModel): { node: string; wall: string }[][] {
  const pos = nodeMap(m);
  const edges = new Map<string, [string, string]>();
  for (const w of m.walls) if (w.a !== w.b) edges.set(w.id, [w.a, w.b]);
  for (;;) {
    const deg = new Map<string, number>();
    for (const [a, b] of edges.values()) {
      deg.set(a, (deg.get(a) || 0) + 1);
      deg.set(b, (deg.get(b) || 0) + 1);
    }
    const loose = [...edges].filter(([, [a, b]]) => deg.get(a) === 1 || deg.get(b) === 1);
    if (!loose.length) break;
    for (const [k] of loose) edges.delete(k);
  }
  const out = new Map<string, [string, string][]>();
  for (const [id, [a, b]] of edges) {
    if (!out.has(a)) out.set(a, []);
    if (!out.has(b)) out.set(b, []);
    out.get(a)!.push([b, id]);
    out.get(b)!.push([a, id]);
  }
  for (const [n, items] of out) {
    const p = pos.get(n)!;
    items.sort(
      (i, j) =>
        Math.atan2(pos.get(i[0])!.y - p.y, pos.get(i[0])!.x - p.x) -
        Math.atan2(pos.get(j[0])!.y - p.y, pos.get(j[0])!.x - p.x),
    );
  }
  const seen = new Set<string>();
  const result: { node: string; wall: string }[][] = [];
  for (const [start, items] of out) {
    for (const [next, wid] of items) {
      if (seen.has(start + "|" + next + "|" + wid)) continue;
      const cycle: { node: string; wall: string }[] = [];
      let u = start,
        v = next,
        w = wid;
      while (!seen.has(u + "|" + v + "|" + w) && cycle.length <= edges.size * 2) {
        seen.add(u + "|" + v + "|" + w);
        cycle.push({ node: u, wall: w });
        const around = out.get(v)!;
        const i = around.findIndex(([n, e]) => n === u && e === w);
        const [nv, nw] = around[(i - 1 + around.length) % around.length];
        u = v;
        v = nv;
        w = nw;
      }
      const points = cycle.map((c) => pos.get(c.node)!);
      if (points.length >= 3 && signedArea(points) > 0) result.push(cycle);
    }
  }
  return result;
}

export function inset(points: Pt[], thickness: number[]): Pt[] {
  const n = points.length;
  const lines = points.map((p, i) => {
    const q = points[(i + 1) % n];
    const l = Math.hypot(q.x - p.x, q.y - p.y) || 1;
    const d = { x: (q.x - p.x) / l, y: (q.y - p.y) / l };
    const nrm = { x: -d.y, y: d.x };
    const off = thickness[i] / 2;
    return { p: { x: p.x + nrm.x * off, y: p.y + nrm.y * off }, d, nrm, off };
  });
  return points.map((v, i) => {
    const l1 = lines[(i - 1 + n) % n],
      l2 = lines[i];
    const det = l1.d.x * l2.d.y - l1.d.y * l2.d.x;
    if (Math.abs(det) < 1e-6) return { x: v.x + l2.nrm.x * l2.off, y: v.y + l2.nrm.y * l2.off };
    const rx = l2.p.x - l1.p.x,
      ry = l2.p.y - l1.p.y;
    const t = (rx * l2.d.y - ry * l2.d.x) / det;
    return { x: l1.p.x + t * l1.d.x, y: l1.p.y + t * l1.d.y };
  });
}

function inside(p: Pt, poly: Pt[]): boolean {
  let hit = false;
  for (let i = 0; i < poly.length; i++) {
    const a = poly[i],
      b = poly[(i + 1) % poly.length];
    if (a.y > p.y !== b.y > p.y && p.x < ((b.x - a.x) * (p.y - a.y)) / (b.y - a.y) + a.x) hit = !hit;
  }
  return hit;
}
const centroid = (p: Pt[]) => ({
  x: p.reduce((s, q) => s + q.x, 0) / p.length,
  y: p.reduce((s, q) => s + q.y, 0) / p.length,
});
function median(v: number[]) {
  const s = [...v].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

/** Rooms from closed wall cycles, inset to the inner wall faces. */
export function rooms(m: PlanModel): Room[] {
  const pos = nodeMap(m);
  const walls = new Map(m.walls.map((w) => [w.id, w]));
  const t = m.walls.length ? median(m.walls.map((w) => w.thicknessPx)) : 8;
  const labelled = m.rooms.filter((r) => r.label).map((r) => ({ label: r.label, c: centroid(r.polygon) }));
  const result: Room[] = [];
  for (const cycle of faces(m)) {
    const outline = cycle.map((c) => pos.get(c.node)!);
    const inner = inset(outline, cycle.map((c) => walls.get(c.wall)!.thicknessPx));
    const area = signedArea(inner);
    if (area < Math.max(MIN_ROOM_PX2, 9 * t * t)) continue;
    const ids = [...new Set(cycle.map((c) => c.wall))].sort();
    const prior = m.rooms.find((r) => r.wallIds.join(".") === ids.join("."));
    result.push({
      id: prior?.id || "r-" + ids.join("."),
      wallIds: ids,
      polygon: inner,
      areaPx2: area,
      label: labelled.find((l) => inside(l.c, inner))?.label ?? null,
    });
  }
  return result.sort(
    (a, b) =>
      Math.min(...a.polygon.map((p) => p.y)) - Math.min(...b.polygon.map((p) => p.y)) ||
      Math.min(...a.polygon.map((p) => p.x)) - Math.min(...b.polygon.map((p) => p.x)),
  );
}

/** Recompute everything derived from geometry; called after every local edit. */
export function withDerived(m: PlanModel): PlanModel {
  return { ...m, scale: { ...m.scale, metersPerPixel: metersPerPixel(m) }, rooms: rooms(m) };
}
