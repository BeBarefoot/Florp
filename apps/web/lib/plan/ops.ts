// Pure edits on PlanModel. Every op returns a new model with derived rooms refreshed.
import type { Opening, PlanModel, Pt, Wall } from "./model";
import { nodeMap, wallEnds, withDerived } from "./derive";

const uid = (p: string) => p + "-" + Math.random().toString(36).slice(2, 10);
const dist = (a: Pt, b: Pt) => Math.hypot(a.x - b.x, a.y - b.y);

function project(a: Pt, b: Pt, p: Pt) {
  const dx = b.x - a.x,
    dy = b.y - a.y,
    l2 = dx * dx + dy * dy || 1;
  const t = ((p.x - a.x) * dx + (p.y - a.y) * dy) / l2;
  const c = Math.max(0, Math.min(1, t));
  const q = { x: a.x + c * dx, y: a.y + c * dy };
  return { t, along: c * Math.sqrt(l2), point: q, distance: dist(p, q) };
}

function clampOpening(o: Opening, length: number): Opening {
  const width = Math.min(o.widthPx, length);
  return { ...o, widthPx: width, offsetPx: Math.max(0, Math.min(length - width, o.offsetPx)) };
}

function onWall(o: Opening, a: Pt, b: Pt): Opening {
  const length = dist(a, b);
  const next = clampOpening(o, length);
  const ux = length ? (b.x - a.x) / length : 0;
  const uy = length ? (b.y - a.y) / length : 0;
  return { ...next, span: [
    { x: a.x + ux * next.offsetPx, y: a.y + uy * next.offsetPx },
    { x: a.x + ux * (next.offsetPx + next.widthPx), y: a.y + uy * (next.offsetPx + next.widthPx) },
  ] };
}

export function moveNode(m: PlanModel, id: string, p: Pt): PlanModel {
  const before = nodeMap(m);
  if (!before.has(id)) return m;
  // A corner belongs to both wall axes. Propagate each coordinate only
  // through its parallel chain so moving a corner cannot tilt its neighbours.
  const connected = (vertical: boolean) => {
    const ids = new Set([id]);
    let changed = true;
    while (changed) {
      changed = false;
      for (const w of m.walls) {
        const [a, b] = wallEnds(m, w, before);
        if ((Math.abs(b.y - a.y) > Math.abs(b.x - a.x)) !== vertical) continue;
        if (!ids.has(w.a) && !ids.has(w.b)) continue;
        for (const end of [w.a, w.b]) if (!ids.has(end)) {
          ids.add(end);
          changed = true;
        }
      }
    }
    return ids;
  };
  const xs = connected(true), ys = connected(false);
  const x = Math.max(0, Math.min(m.imageTransform.width, p.x));
  const y = Math.max(0, Math.min(m.imageTransform.height, p.y));
  const next: PlanModel = {
    ...m,
    nodes: m.nodes.map((n) => ({ ...n, x: xs.has(n.id) ? x : n.x, y: ys.has(n.id) ? y : n.y })),
  };
  const after = nodeMap(next);
  const touched = new Map(m.walls.filter((w) =>
    [w.a, w.b].some((end) => xs.has(end) || ys.has(end)),
  ).map((w) => [w.id, w]));
  // Do not collapse or reverse a wall by dragging past its opposite end.
  for (const w of touched.values()) {
    const [a, b] = wallEnds(m, w, before), [na, nb] = wallEnds(next, w, after);
    const axis = Math.abs(b.x - a.x) >= Math.abs(b.y - a.y) ? "x" : "y";
    if ((nb[axis] - na[axis]) * Math.sign(b[axis] - a[axis]) < 1) return m;
  }
  next.openings = m.openings.map((o) => {
    const w = o.hostWallId ? touched.get(o.hostWallId) : undefined;
    if (!w) return o;
    const [a, b] = wallEnds(m, w, before);
    const [na, nb] = wallEnds(next, w, after);
    const old = dist(a, b);
    const along = o.offsetPx + o.widthPx / 2;
    const centre = old ? { x: a.x + (b.x - a.x) * along / old, y: a.y + (b.y - a.y) * along / old } : a;
    // Project the old image-space centre instead of moving the opening by a
    // fraction of host length when an endpoint is extended. Keep physical width.
    return onWall({ ...o, offsetPx: project(na, nb, centre).along - o.widthPx / 2 }, na, nb);
  });
  return withDerived(next);
}

export function splitWall(m: PlanModel, wallId: string, p: Pt): { model: PlanModel; nodeId: string } {
  const w = m.walls.find((x) => x.id === wallId)!;
  const [a, b] = wallEnds(m, w);
  const pr = project(a, b, p);
  const nodeId = uid("n");
  const first: Wall = { ...w, id: uid("w"), b: nodeId };
  const second: Wall = { ...w, id: uid("w"), a: nodeId };
  const cut = pr.along;
  const openings = m.openings.map((o) => {
    if (o.hostWallId !== wallId) return o;
    const centre = o.offsetPx + o.widthPx / 2;
    return centre <= cut
      ? onWall({ ...o, hostWallId: first.id }, a, pr.point)
      : onWall({ ...o, hostWallId: second.id, offsetPx: o.offsetPx - cut }, pr.point, b);
  });
  return {
    nodeId,
    model: {
      ...m,
      nodes: [...m.nodes, { id: nodeId, x: pr.point.x, y: pr.point.y }],
      walls: [...m.walls.filter((x) => x.id !== wallId), first, second],
      openings,
    },
  };
}

type WallTarget = { point: Pt; nodeId?: string; wallId?: string };

/** Resolve snapping without mutation, shared by the preview and committed edit. */
function wallTarget(m: PlanModel, p: Pt, radius: number, from?: Pt): WallTarget {
  const horizontal = from ? Math.abs(p.x - from.x) >= Math.abs(p.y - from.y) : false;
  const axis = horizontal ? "x" : "y", cross = horizontal ? "y" : "x";
  const onAxis = (q: Pt) => !from || Math.abs(q[cross] - from[cross]) < 1e-7;
  const near = m.nodes
    .map((n) => ({ n, d: dist(n, p) }))
    .filter((x) => x.d <= radius && onAxis(x.n))
    .sort((a, b) => a.d - b.d)[0];
  if (near) return { point: near.n, nodeId: near.n.id };
  const nodes = nodeMap(m);
  const host = m.walls
    .flatMap((w) => {
      const [a, b] = wallEnds(m, w, nodes);
      if (!from) return [{ w, pr: project(a, b, p) }];
      // Intersect the host with the locked axis. Nearest-point projection can
      // move the endpoint off that axis and reintroduce a diagonal wall.
      const dc = b[cross] - a[cross];
      if (Math.abs(dc) < 1e-7) return onAxis(a) ? [{ w, pr: project(a, b, p) }] : [];
      const t = (from[cross] - a[cross]) / dc;
      const point = { ...p, [axis]: a[axis] + t * (b[axis] - a[axis]), [cross]: from[cross] };
      return [{ w, pr: { t, point, distance: dist(p, point), along: t * dist(a, b) } }];
    })
    .filter(({ w, pr }) => pr.t > 0 && pr.t < 1 &&
      pr.distance <= (radius <= 1e-7 ? radius : Math.max(radius, w.thicknessPx / 2)) &&
      !m.openings.some((o) => o.hostWallId === w.id && o.status !== "rejected" &&
        pr.along > o.offsetPx + 1e-7 && pr.along < o.offsetPx + o.widthPx - 1e-7))
    .sort((a, b) => a.pr.distance - b.pr.distance)[0];
  if (host) return { point: host.pr.point, wallId: host.w.id };
  return { point: p };
}

export function wallPlacement(m: PlanModel, p1: Pt, p2: Pt, radius = 10) {
  const start = wallTarget(m, p1, radius);
  const horizontal = Math.abs(p2.x - start.point.x) >= Math.abs(p2.y - start.point.y);
  const p = horizontal ? { x: p2.x, y: start.point.y } : { x: start.point.x, y: p2.y };
  const end = wallTarget(m, p, radius, start.point);
  return { start, end };
}

function materializeTarget(m: PlanModel, target: WallTarget): { model: PlanModel; nodeId: string } {
  if (target.nodeId && m.nodes.some((n) => n.id === target.nodeId)) return { model: m, nodeId: target.nodeId };
  if (target.wallId && m.walls.some((w) => w.id === target.wallId)) return splitWall(m, target.wallId, target.point);
  const nodeId = uid("n");
  return { model: { ...m, nodes: [...m.nodes, { id: nodeId, ...target.point }] }, nodeId };
}

export function addWall(m: PlanModel, p1: Pt, p2: Pt, thicknessPx: number, snap = 10): { model: PlanModel; wallId: string } {
  const placement = wallPlacement(m, p1, p2, snap);
  if (dist(placement.start.point, placement.end.point) < 3) return { model: m, wallId: "" };
  const first = materializeTarget(m, placement.start);
  // Re-resolve against any host segments created by the first T-junction.
  const target = wallTarget(first.model, placement.end.point, 1e-7, placement.start.point);
  const second = materializeTarget(first.model, target);
  const wallId = uid("w");
  if (first.nodeId === second.nodeId) return { model: m, wallId: "" };
  return {
    wallId,
    model: withDerived({
      ...second.model,
      walls: [
        ...second.model.walls,
        {
          id: wallId,
          a: first.nodeId,
          b: second.nodeId,
          thicknessPx,
          heightM: 2.8,
          material: "block",
          exterior: null,
          confidence: 1,
          source: "user",
        },
      ],
    }),
  };
}

function dropOrphanNodes(m: PlanModel): PlanModel {
  const used = new Set(m.walls.flatMap((w) => [w.a, w.b]));
  return { ...m, nodes: m.nodes.filter((n) => used.has(n.id)) };
}

export function deleteWall(m: PlanModel, id: string): PlanModel {
  return withDerived(
    dropOrphanNodes({
      ...m,
      walls: m.walls.filter((w) => w.id !== id),
      openings: m.openings.filter((o) => o.hostWallId !== id),
    }),
  );
}

export function patchWall(m: PlanModel, id: string, values: Partial<Wall>): PlanModel {
  return withDerived({ ...m, walls: m.walls.map((w) => (w.id === id ? { ...w, ...values } : w)) });
}

/** Host an opening span on the nearest parallel wall; returns null if none is close. */
export function hostSpan(m: PlanModel, p1: Pt, p2: Pt, wallId?: string) {
  const nodes = nodeMap(m);
  const mid = { x: (p1.x + p2.x) / 2, y: (p1.y + p2.y) / 2 };
  const best = m.walls
    .filter((w) => !wallId || w.id === wallId)
    .map((w) => {
      const [a, b] = wallEnds(m, w, nodes);
      return { w, a, b, pr: project(a, b, mid), length: dist(a, b) };
    })
    .filter((c) => wallId || c.pr.distance <= c.w.thicknessPx / 2 + 12)
    .sort((x, y) => x.pr.distance - y.pr.distance)[0];
  if (!best) return null;
  const s = project(best.a, best.b, p1).along,
    e = project(best.a, best.b, p2).along;
  const lo = Math.min(s, e),
    hi = Math.max(s, e);
  if (hi - lo < 2) return null;
  return { wallId: best.w.id, offsetPx: lo, widthPx: hi - lo };
}

export function addOpening(m: PlanModel, kind: "door" | "window", p1: Pt, p2: Pt): { model: PlanModel; openingId: string } | null {
  const host = hostSpan(m, p1, p2);
  if (!host) return null;
  const id = uid("o");
  const wall = m.walls.find((w) => w.id === host.wallId)!;
  const opening: Opening = {
    id,
    kind,
    hostWallId: host.wallId,
    offsetPx: host.offsetPx,
    widthPx: host.widthPx,
    span: [p1, p2],
    heightM: Math.min(kind === "door" ? 2.1 : 1.2, wall.heightM - (kind === "window" ? 0.9 : 0)),
    sillM: kind === "window" ? 0.9 : 0,
    swing: null,
    hinge: "start",
    confidence: 1,
    status: "confirmed",
  };
  const [a, b] = wallEnds(m, wall);
  return { openingId: id, model: { ...m, openings: [...m.openings, onWall(opening, a, b)] } };
}

export function patchOpening(m: PlanModel, id: string, values: Partial<Opening>): PlanModel {
  return {
    ...m,
    openings: m.openings.map((o) => {
      if (o.id !== id) return o;
      const next = { ...o, ...values };
      const w = m.walls.find((x) => x.id === next.hostWallId);
      if (!w) return next;
      const [a, b] = wallEnds(m, w);
      return onWall(next, a, b);
    }),
  };
}

export function attachOpening(m: PlanModel, id: string, wallId: string): PlanModel | null {
  const o = m.openings.find((x) => x.id === id)!;
  const nodes = nodeMap(m);
  let ends = o.span;
  if (o.hostWallId) {
    const w = m.walls.find((x) => x.id === o.hostWallId)!;
    const [a, b] = wallEnds(m, w, nodes);
    const l = dist(a, b) || 1;
    const u = { x: (b.x - a.x) / l, y: (b.y - a.y) / l };
    ends = [
      { x: a.x + u.x * o.offsetPx, y: a.y + u.y * o.offsetPx },
      { x: a.x + u.x * (o.offsetPx + o.widthPx), y: a.y + u.y * (o.offsetPx + o.widthPx) },
    ];
  }
  if (!ends) return null;
  const host = hostSpan(m, ends[0], ends[1], wallId);
  if (!host) return null;
  return patchOpening(m, id, { hostWallId: wallId, offsetPx: host.offsetPx, widthPx: host.widthPx });
}

const resolveFinding = (m: PlanModel, openingId: string): PlanModel => ({
  ...m,
  findings: m.findings.filter(
    (f) => !(f.category === "opening_needs_approval" && f.targetIds.includes(openingId)),
  ),
});

export function decideOpening(m: PlanModel, id: string, decision: "confirm" | "reject"): PlanModel | null {
  const o = m.openings.find((x) => x.id === id);
  if (!o) return null;
  if (decision === "confirm" && !o.hostWallId) return null;
  return resolveFinding(
    patchOpening(m, id, { status: decision === "confirm" ? "confirmed" : "rejected" }),
    id,
  );
}

export function deleteOpening(m: PlanModel, id: string): PlanModel {
  return resolveFinding({ ...m, openings: m.openings.filter((o) => o.id !== id) }, id);
}

export function setReference(m: PlanModel, p1: Pt, p2: Pt, lengthMeters: number): PlanModel {
  return withDerived({ ...m, scale: { metersPerPixel: null, reference: { p1, p2, lengthMeters } } });
}

export function dismissFinding(m: PlanModel, id: string): PlanModel {
  return {
    ...m,
    dismissedFindings: [...new Set([...m.dismissedFindings, id])],
    findings: m.findings.filter((f) => f.id !== id),
  };
}

export function setRoomLabel(m: PlanModel, id: string, label: string): PlanModel {
  return { ...m, rooms: m.rooms.map((r) => (r.id === id ? { ...r, label: label || null } : r)) };
}
