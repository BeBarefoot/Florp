import * as THREE from "three";
import { GLTFExporter } from "three/examples/jsm/exporters/GLTFExporter.js";
import type { PlanModel } from "./plan/model";
import { metersPerPixel } from "./plan/derive";
import { floorOutlines, wallPieces } from "./plan/mesh";

/** Metric glTF (meters) with stable wall/room/opening IDs in node extras. */
export async function exportPlan3D(m: PlanModel) {
  if (!metersPerPixel(m)) throw Error("Set one measurement first");
  if (m.openings.some((o) => o.status === "proposed"))
    throw Error("Approve or reject every proposed door and window before exporting 3D.");
  const scene = new THREE.Scene();
  for (const piece of wallPieces(m)) {
    const group = new THREE.Group();
    group.name = piece.id;
    group.userData = {
      kind: "wall",
      id: piece.id,
      material: piece.material,
      openings: m.openings
        .filter((o) => o.hostWallId === piece.id && o.status === "confirmed")
        .map((o) => ({ id: o.id, kind: o.kind })),
    };
    group.position.set(piece.centre[0], 0, piece.centre[1]);
    group.rotation.y = piece.angle;
    for (const c of piece.chunks) {
      const mesh = new THREE.Mesh(
        new THREE.BoxGeometry(c.end - c.start, c.high - c.low, piece.thicknessM),
        new THREE.MeshStandardMaterial({ color: "#cbd9d5" }),
      );
      mesh.position.set((c.start + c.end - piece.lengthM) / 2, (c.low + c.high) / 2, 0);
      group.add(mesh);
    }
    scene.add(group);
  }
  for (const r of floorOutlines(m)) {
    const shape = new THREE.Shape();
    r.points.forEach((p, i) => (i ? shape.lineTo(p.x, -p.y) : shape.moveTo(p.x, -p.y)));
    shape.closePath();
    const mesh = new THREE.Mesh(
      new THREE.ShapeGeometry(shape),
      new THREE.MeshStandardMaterial({ color: "#e2e6e2", side: THREE.DoubleSide }),
    );
    mesh.name = r.id;
    mesh.userData = { kind: "room", id: r.id, label: r.label };
    mesh.rotation.x = -Math.PI / 2;
    scene.add(mesh);
  }
  const data = await new GLTFExporter().parseAsync(scene, { binary: true });
  const url = URL.createObjectURL(new Blob([data as ArrayBuffer], { type: "model/gltf-binary" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = "florp-plan.glb";
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
