import type { Geometry, Pt } from "./api";
export type Object2D = {
  id: string;
  exterior?: boolean | null;
  material?: "block" | "concrete";
  kind: "wall" | "door" | "window";
  start: Pt;
  end: Pt;
  thickness_px: number;
  host_id: string | null;
  reviewed: boolean;
  uncertain: boolean;
  height_m: number;
  sill_m: number;
};
export type PlanDoc = {
  width: number;
  height: number;
  objects: Object2D[];
  reference: {
    start: [number, number];
    end: [number, number];
    length_cm: number;
  } | null;
  warnings: string[];
};
export type Workspace = {
  version: number;
  document: PlanDoc;
  derived: {
    px_per_meter: number | null;
    footprint_area_m2?: number | null;
    rooms: {
      id: string;
      points: Pt[];
      area_m2: number | null;
      width_m: number | null;
      depth_m: number | null;
    }[];
    bounds_px: number[] | null;
    margin_px: number | null;
  };
};
export const length = (o: Object2D) =>
  Math.hypot(o.end.x - o.start.x, o.end.y - o.start.y);
export const ppm = (d: PlanDoc) =>
  d.reference
    ? Math.hypot(
        d.reference.end[0] - d.reference.start[0],
        d.reference.end[1] - d.reference.start[1],
      ) /
      (d.reference.length_cm / 100)
    : null;
export function geometry(
  d: PlanDoc,
  rooms: Workspace["derived"]["rooms"],
): Geometry {
  const scale = ppm(d);
  return {
    width_px: d.width,
    height_px: d.height,
    px_per_meter: scale,
    scale_source: scale ? "user_confirmed" : "unknown",
    walls: d.objects
      .filter((o) => o.kind === "wall")
      .map((o) => ({
        id: o.id,
        start: o.start,
        end: o.end,
        thickness_m: o.thickness_px / (scale || 60),
        height_m: o.height_m,
        inferred: !o.reviewed,
      })),
    rooms: rooms.map((r) => ({ ...r, label: "Room", confidence: 0 })),
    openings: scale
      ? d.objects
          .filter((o) => o.kind !== "wall" && o.host_id)
          .flatMap((o) => {
            const host = d.objects.find(
              (w) => w.id === o.host_id && w.kind === "wall",
            );
            if (!host) return [];
            const dx = host.end.x - host.start.x,
              dy = host.end.y - host.start.y,
              l = length(host);
            const project = (p: Pt) =>
              ((p.x - host.start.x) * dx + (p.y - host.start.y) * dy) / l;
            const a = Math.max(
                0,
                Math.min(l, Math.min(project(o.start), project(o.end))),
              ),
              b = Math.max(
                a,
                Math.min(l, Math.max(project(o.start), project(o.end))),
              );
            return b > a
              ? [
                  {
                    id: o.id,
                    kind: o.kind as "door" | "window",
                    wall_id: host.id,
                    offset_m: a / scale,
                    width_m: (b - a) / scale,
                    height_m: Math.min(o.height_m, host.height_m - o.sill_m),
                    sill_m: o.kind === "door" ? 0 : o.sill_m,
                    inferred: !o.reviewed,
                  },
                ]
              : [];
          })
      : [],
    warnings: d.warnings,
  };
}
export function moveEndpoint(
  doc: PlanDoc,
  id: string,
  end: "start" | "end",
  point: Pt,
): PlanDoc {
  const before = doc.objects.find((o) => o.id === id);
  if (!before) return doc;
  const old = before[end];
  const next = structuredClone(doc);
  const changed = new Set<string>();
  next.objects.forEach((o) => {
    if (o.kind !== "wall" && o.id !== id) return;
    (["start", "end"] as const).forEach((k) => {
      if (
        (o.id === id && k === end) ||
        (before.kind === "wall" &&
          Math.hypot(o[k].x - old.x, o[k].y - old.y) < 0.5)
      ) {
        o[k] = point;
        changed.add(o.id);
      }
    });
  });
  next.objects.forEach((o) => {
    if (o.kind === "wall" || !o.host_id || !changed.has(o.host_id)) return;
    const a = doc.objects.find((w) => w.id === o.host_id)!,
      b = next.objects.find((w) => w.id === o.host_id)!;
    const dx = a.end.x - a.start.x,
      dy = a.end.y - a.start.y,
      l2 = dx * dx + dy * dy;
    (["start", "end"] as const).forEach((k) => {
      const t = ((o[k].x - a.start.x) * dx + (o[k].y - a.start.y) * dy) / l2;
      o[k] = {
        x: b.start.x + t * (b.end.x - b.start.x),
        y: b.start.y + t * (b.end.y - b.start.y),
      };
    });
  });
  return next;
}
export function attach(o: Object2D, wall: Object2D): Object2D {
  const dx = wall.end.x - wall.start.x,
    dy = wall.end.y - wall.start.y,
    l2 = dx * dx + dy * dy;
  const project = (p: Pt) => {
    const t = Math.max(
      0,
      Math.min(1, ((p.x - wall.start.x) * dx + (p.y - wall.start.y) * dy) / l2),
    );
    return { x: wall.start.x + t * dx, y: wall.start.y + t * dy };
  };
  return {
    ...o,
    host_id: wall.id,
    start: project(o.start),
    end: project(o.end),
    thickness_px: wall.thickness_px,
  };
}
