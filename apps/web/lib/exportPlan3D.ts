import * as THREE from "three";
import { GLTFExporter } from "three/examples/jsm/exporters/GLTFExporter.js";
import { geometry, PlanDoc, Workspace } from "./planWorkspace";
export async function exportPlan3D(
  doc: PlanDoc,
  rooms: Workspace["derived"]["rooms"],
) {
  const g = geometry(doc, rooms),
    scale = g.px_per_meter;
  if (!scale) throw Error("Set one measurement first");
  const scene = new THREE.Scene();
  for (const wall of g.walls) {
    const dx = wall.end.x - wall.start.x,
      dz = wall.end.y - wall.start.y,
      l = Math.hypot(dx, dz) / scale;
    const group = new THREE.Group();
    group.position.set(
      (wall.start.x + wall.end.x) / (2 * scale),
      0,
      (wall.start.y + wall.end.y) / (2 * scale),
    );
    group.rotation.y = -Math.atan2(dz, dx);
    const cuts = g.openings
      .filter((o) => o.wall_id === wall.id)
      .sort((a, b) => a.offset_m - b.offset_m);
    const chunks: { a: number; b: number; low: number; high: number }[] = [];
    let cursor = 0;
    for (const o of cuts) {
      const a = Math.max(cursor, o.offset_m),
        b = Math.min(l, o.offset_m + o.width_m);
      if (a > cursor)
        chunks.push({ a: cursor, b: a, low: 0, high: wall.height_m });
      if (o.sill_m > 0) chunks.push({ a, b, low: 0, high: o.sill_m });
      if (o.sill_m + o.height_m < wall.height_m)
        chunks.push({ a, b, low: o.sill_m + o.height_m, high: wall.height_m });
      cursor = Math.max(cursor, b);
    }
    if (cursor < l)
      chunks.push({ a: cursor, b: l, low: 0, high: wall.height_m });
    for (const c of chunks) {
      if (c.b <= c.a || c.high <= c.low) continue;
      const mesh = new THREE.Mesh(
        new THREE.BoxGeometry(c.b - c.a, c.high - c.low, wall.thickness_m),
        new THREE.MeshStandardMaterial({ color: "#cbd9d5" }),
      );
      mesh.position.set((c.a + c.b - l) / 2, (c.low + c.high) / 2, 0);
      group.add(mesh);
    }
    scene.add(group);
  }
  for (const r of rooms) {
    const shape = new THREE.Shape();
    r.points.forEach((p, i) =>
      i
        ? shape.lineTo(p.x / scale, -p.y / scale)
        : shape.moveTo(p.x / scale, -p.y / scale),
    );
    shape.closePath();
    const mesh = new THREE.Mesh(
      new THREE.ShapeGeometry(shape),
      new THREE.MeshStandardMaterial({
        color: "#e2e6e2",
        side: THREE.DoubleSide,
      }),
    );
    mesh.rotation.x = -Math.PI / 2;
    scene.add(mesh);
  }
  const data = await new GLTFExporter().parseAsync(scene, { binary: true });
  const url = URL.createObjectURL(
    new Blob([data as ArrayBuffer], { type: "model/gltf-binary" }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = "florp-plan.glb";
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
