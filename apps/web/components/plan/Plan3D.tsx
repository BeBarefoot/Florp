"use client";
import { useMemo } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, Grid } from "@react-three/drei";
import * as THREE from "three";
import type { PlanModel } from "../../lib/plan/model";
import { metersPerPixel } from "../../lib/plan/derive";
import { floorOutlines, meshSignature, wallPieces } from "../../lib/plan/mesh";

export default function Plan3D({ model }: { model: PlanModel }) {
  const pieces = useMemo(() => wallPieces(model), [model]);
  const floors = useMemo(
    () =>
      floorOutlines(model).map((r) => {
        const shape = new THREE.Shape();
        r.points.forEach((p, i) => (i ? shape.lineTo(p.x, -p.y) : shape.moveTo(p.x, -p.y)));
        shape.closePath();
        const g = new THREE.ShapeGeometry(shape);
        g.rotateX(-Math.PI / 2);
        return { id: r.id, geometry: g };
      }),
    [model],
  );
  const s = metersPerPixel(model) || 1;
  const w = model.imageTransform.width * s,
    h = model.imageTransform.height * s;
  const target: [number, number, number] = [w / 2, 0, h / 2];
  const ghosts = model.openings.filter((o) => o.status === "proposed").length;
  return (
    <div className="plan3d" data-testid="plan-3d" data-wall-lengths={meshSignature(pieces)}>
      <Canvas camera={{ position: [w / 2 + Math.max(6, w * 0.6), Math.max(7, h * 0.9), h / 2 + Math.max(8, h)], fov: 55 }}>
        <ambientLight intensity={1.7} />
        <directionalLight position={[5, 10, 3]} intensity={2} />
        <Grid infiniteGrid cellSize={1} sectionSize={5} />
        {floors.map((f) => (
          <mesh key={f.id} geometry={f.geometry} position={[0, 0.015, 0]}>
            <meshStandardMaterial color="#dceae2" side={THREE.DoubleSide} />
          </mesh>
        ))}
        {pieces.map((p) => (
          <group key={p.id} position={[p.centre[0], 0, p.centre[1]]} rotation={[0, p.angle, 0]}>
            {p.chunks.map((c, i) => (
              <mesh key={i} position={[(c.start + c.end - p.lengthM) / 2, (c.low + c.high) / 2, 0]}>
                <boxGeometry args={[c.end - c.start, c.high - c.low, p.thicknessM]} />
                <meshStandardMaterial color={p.material === "concrete" ? "#7d93a8" : "#c9d6db"} />
              </mesh>
            ))}
          </group>
        ))}
        <OrbitControls makeDefault target={target} />
      </Canvas>
      {ghosts > 0 && (
        <p className="plan3d-note">
          {ghosts} proposed opening{ghosts > 1 ? "s are" : " is"} not cut into walls until you approve
          {ghosts > 1 ? " them" : " it"}.
        </p>
      )}
    </div>
  );
}
