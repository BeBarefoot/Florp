"use client";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Canvas, type ThreeEvent } from "@react-three/fiber";
import { OrbitControls, Grid, Line, PerspectiveCamera } from "@react-three/drei";
import * as THREE from "three";
import type { PlanModel } from "../../lib/plan/model";
import { metersPerPixel } from "../../lib/plan/derive";
import { floorOutlines, meshSignature, wallPieces } from "../../lib/plan/mesh";
import { stairPieces } from "../../lib/plan/stairs";
import { DEFAULT_EYE_HEIGHT_M, eyeLevelPose, type FloorPoint } from "../../lib/plan/camera";

type Pose = NonNullable<ReturnType<typeof eyeLevelPose>>;
function EyeCamera({ pose }: { pose: Pose }) {
  const ref = useRef<THREE.PerspectiveCamera>(null);
  useLayoutEffect(() => {
    const [x, y, z] = pose.position, [dx, dy, dz] = pose.direction;
    ref.current?.lookAt(x + dx, y + dy, z + dz);
    ref.current?.updateMatrixWorld();
  }, [pose]);
  return <PerspectiveCamera ref={ref} makeDefault position={pose.position} fov={pose.verticalFovDeg} near={0.03} far={100} />;
}

export default function Plan3D({ model }: { model: PlanModel }) {
  const [step, setStep] = useState<"position" | "aim" | null>(null);
  const [origin, setOrigin] = useState<FloorPoint | null>(null);
  const [aim, setAim] = useState<FloorPoint | null>(null);
  const [heightText, setHeightText] = useState(String(DEFAULT_EYE_HEIGHT_M));
  const eyeHeight = Number(heightText);
  const [preview, setPreview] = useState(false);
  const pose = useMemo(() => origin && aim ? eyeLevelPose(origin, aim, eyeHeight) : null, [origin, aim, eyeHeight]);
  useEffect(() => {
    // Keep camera experiments separate from edits to authoritative geometry.
    setOrigin(null);
    setAim(null);
    setStep(null);
    setPreview(false);
  }, [model]);

  function floorClick(e: ThreeEvent<MouseEvent>) {
    if (!step) return;
    e.stopPropagation();
    const point: FloorPoint = [e.point.x, e.point.z];
    if (step === "position") {
      setOrigin(point);
      setAim(null);
      setStep("aim");
    } else if (origin && eyeLevelPose(origin, point, DEFAULT_EYE_HEIGHT_M)) {
      setAim(point);
      setStep(null);
    }
  }

  const pieces = useMemo(() => wallPieces(model), [model]);
  const stairs = useMemo(() => stairPieces(model), [model]);
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
    <div className="plan3d" data-testid="plan-3d" data-wall-lengths={meshSignature(pieces)} data-stair-count={stairs.length}>
      <Canvas camera={{ position: [w / 2 + Math.max(6, w * 0.6), Math.max(7, h * 0.9), h / 2 + Math.max(8, h)], fov: 55 }}>
        <ambientLight intensity={1.7} />
        <directionalLight position={[5, 10, 3]} intensity={2} />
        {!preview && <Grid infiniteGrid cellSize={1} sectionSize={5} />}
        {floors.map((f) => (
          <mesh key={f.id} geometry={f.geometry} position={[0, 0.015, 0]} onClick={floorClick}>
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
        {stairs.map((stair) => (
          <group key={stair.id}>
            {stair.steps.map((step, i) => (
              <mesh key={i} rotation={[-Math.PI / 2, 0, 0]}>
                <extrudeGeometry args={[step.shape, { depth: step.height, bevelEnabled: false }]} />
                <meshStandardMaterial color="#a9b9b2" />
              </mesh>
            ))}
          </group>
        ))}
        {!preview && origin && (
          <mesh position={[origin[0], 0.07, origin[1]]}>
            <sphereGeometry args={[0.075, 16, 12]} />
            <meshBasicMaterial color="#007c70" />
          </mesh>
        )}
        {!preview && origin && aim && <Line points={[[origin[0], 0.07, origin[1]], [aim[0], 0.07, aim[1]]]} color="#007c70" lineWidth={3} />}
        {preview && pose ? <EyeCamera pose={pose} /> : <OrbitControls makeDefault target={target} />}
      </Canvas>
      <section className="plan3d-camera" aria-label="Interior camera">
        <div className="plan3d-camera-actions">
          <button type="button" disabled={!floors.length} onClick={() => {
            setPreview(false);
            setOrigin(null);
            setAim(null);
            setStep("position");
          }}>Place camera</button>
          <button type="button" disabled={!pose} aria-pressed={preview} onClick={() => setPreview((p) => !p)}>
            {preview ? "Back to orbit" : "Preview view"}
          </button>
          <label>Eye height <input type="number" min="0.8" max="2.2" step="0.05" value={heightText}
            onChange={(e) => {
              setHeightText(e.currentTarget.value);
              if (!(e.currentTarget.valueAsNumber >= 0.8 && e.currentTarget.valueAsNumber <= 2.2)) setPreview(false);
            }} /> m</label>
        </div>
        <p aria-live="polite">
          {!floors.length ? "A closed room is needed to place a camera."
            : step === "position" ? "Click a room floor to place the camera."
            : step === "aim" ? "Click a second point on a room floor to aim."
            : origin && aim && !pose ? "Enter an eye height between 0.8 and 2.2 m."
            : preview ? "Eye-level view of the measured model."
            : origin && aim ? "Camera ready to preview."
            : "Place a camera to preview the room from inside."}
        </p>
      </section>
      {ghosts > 0 && (
        <p className="plan3d-note">
          {ghosts} proposed opening{ghosts > 1 ? "s are" : " is"} not cut into walls until you approve
          {ghosts > 1 ? " them" : " it"}.
        </p>
      )}
    </div>
  );
}
