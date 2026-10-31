// Pure edits on PlanModel. Every op returns a new model with derived rooms refreshed.
import type { Opening, PlanModel, Pt, Wall } from "./model";
import { nodeMap, wallEnds, wallLength, withDerived } from "./derive";

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

export function moveNode(m: PlanModel, id: string, p: Pt): PlanModel {
  const before = nodeMap(m);
  const next: PlanModel = {
    ...m,
    nodes: m.nodes.map((n) =>
      n.id === id
        ? {
            ...n,
            x: Math.max(0, Math.min(m.imageTransform.width, p.x)),
            y: Math.max(0, Math.min(m.imageTransform.height, p.y)),
          }
        : n,
    ),
  };
  const after = nodeMap(next);
  const touched = new Map(m.walls.filter((w) => w.a === id || w.b === id).map((w) => [w.id, w]));
  next.openings = m.openings.map((o) => {
    const w = o.hostWallId ? touched.get(o.hostWallId) : undefined;
    if (!w) return o;
    const old = wallLength(m, w, before),
      now = wallLength(next, w, after);
    // Keep the opening's centre at the same fraction along its host; width is physical.
    const centre = old ? (o.offsetPx + o.widthPx / 2) / old : 0.5;
    return clampOpening({ ...o, offsetPx: centre * now - o.widthPx / 2 }, now);
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
  const total = dist(a, b);
  const openings = m.openings.map((o) => {
    if (o.hostWallId !== wallId) return o;
    const centre = o.offsetPx + o.widthPx / 2;
    return centre <= cut
      ? clampOpening({ ...o, hostWallId: first.id }, cut)
      : clampOpening({ ...o, hostWallId: second.id, offsetPx: o.offsetPx - cut }, total - cut);
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

/** Snap to an existing node, else T-split a nearby wall, else create a free node. */
function snapNode(m: PlanModel, p: Pt, radius: number): { model: PlanModel; nodeId: string } {
  const near = m.nodes
    .map((n) => ({ n, d: dist(n, p) }))
    .filter((x) => x.d <= radius)
    .sort((a, b) => a.d - b.d)[0];
  if (near) return { model: m, nodeId: near.n.id };
  const nodes = nodeMap(m);
  const host = m.walls
    .map((w) => {
      const [a, b] = wallEnds(m, w, nodes);
      return { w, pr: project(a, b, p) };
    })
    .filter(({ w, pr }) => pr.t > 0 && pr.t < 1 && pr.distance <= Math.max(radius, w.thicknessPx / 2))
    .sort((a, b) => a.pr.distance - b.pr.distance)[0];
  if (host) return splitWall(m, host.w.id, p);
  const nodeId = uid("n");
  return { model: { ...m, nodes: [...m.nodes, { id: nodeId, x: p.x, y: p.y }] }, nodeId };
}

export function addWall(m: PlanModel, p1: Pt, p2: Pt, thicknessPx: number, snap = 10): { model: PlanModel; wallId: string } {
  const first = snapNode(m, p1, snap);
  const second = snapNode(first.model, p2, snap);
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
  return { openingId: id, model: { ...m, openings: [...m.openings, opening] } };
}

export function patchOpening(m: PlanModel, id: string, values: Partial<Opening>): PlanModel {
  return {
    ...m,
    openings: m.openings.map((o) => {
      if (o.id !== id) return o;
      const next = { ...o, ...values };
      const w = m.walls.find((x) => x.id === next.hostWallId);
      return w ? clampOpening(next, wallLength(m, w)) : next;
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
