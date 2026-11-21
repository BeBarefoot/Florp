import { useLayoutEffect, useMemo, useRef } from "react";
import { useThree } from "@react-three/fiber";
import { MathUtils, Vector3 } from "three";
import type { Pt } from "../../lib/plan/model";
import type { Frame, View } from "../../lib/plan/scene";
import { makeCamera } from "./SceneMesh";

export function WalkCamera({view, scale, frame, canMove, pose}: {
  pose: {current: View|null}; view: View; scale: number; frame: Frame; canMove: (p: Pt) => boolean;
}) {
  const camera = useMemo(() => makeCamera(view, scale, frame), [view, scale, frame]);
  const {gl, get, set, invalidate} = useThree();
  const walkable = useRef(canMove);
  useLayoutEffect(() => { walkable.current = canMove; }, [canMove]);

  useLayoutEffect(() => {
    const previous = get().camera;
    set({camera});
    const canvas = gl.domElement;
    const pointers = new Map<number, Pt>();
    const target = new Vector3();
    let yaw = MathUtils.degToRad(view.yaw);
    const pitch = MathUtils.degToRad(view.pitch);

    const halfFov = Math.tan(MathUtils.degToRad(view.horizontalFov/2));
    function remember() {
      pose.current = {...view,position:{x:camera.position.x/scale,y:camera.position.z/scale},
        yaw:((MathUtils.radToDeg(yaw)%360+540)%360)-180,
        horizontalFov:MathUtils.clamp(2*MathUtils.radToDeg(Math.atan(halfFov/camera.zoom)),55,110)};
    }
    remember();
    function zoom(factor: number) {
      camera.zoom = MathUtils.clamp(camera.zoom * factor, halfFov/Math.tan(MathUtils.degToRad(55)), halfFov/Math.tan(MathUtils.degToRad(27.5)));
      camera.updateProjectionMatrix();
      remember();
      invalidate();
    }

    function down(event: PointerEvent) {
      if (event.button !== 0 || pointers.size === 2) return;
      pointers.set(event.pointerId, {x: event.clientX, y: event.clientY});
      canvas.setPointerCapture(event.pointerId);
    }

    function move(event: PointerEvent) {
      const before = pointers.get(event.pointerId);
      if (!before) return;
      const after = {x: event.clientX, y: event.clientY};
      pointers.set(event.pointerId, after);
      if (pointers.size === 2) {
        const other = [...pointers].find(([id]) => id !== event.pointerId)![1];
        const initial = Math.hypot(before.x - other.x, before.y - other.y);
        const distance = Math.hypot(after.x - other.x, after.y - other.y);
        if (initial > 0 && distance > 0) zoom(distance / initial);
        return;
      }
      yaw += (after.x - before.x) * .007;
      const distance = MathUtils.clamp((before.y - after.y) * .012, -.6, .6);
      // Check the path in short steps so fast drags cannot skip through walls.
      const steps = Math.ceil(Math.abs(distance) / .05);
      const headingX = Math.cos(yaw), headingZ = Math.sin(yaw);
      for (let i = 0; i < steps; i++) {
        const x = camera.position.x + headingX * distance / steps;
        const z = camera.position.z + headingZ * distance / steps;
        if (!walkable.current({x: x / scale, y: z / scale})) break;
        camera.position.x = x;
        camera.position.z = z;
      }
      target.set(headingX * Math.cos(pitch), Math.sin(pitch), headingZ * Math.cos(pitch));
      camera.lookAt(target.add(camera.position));
      remember();
      invalidate();
    }

    function end(event: PointerEvent) {
      pointers.delete(event.pointerId);
    }

    function wheel(event: WheelEvent) {
      event.preventDefault();
      const units = event.deltaMode === WheelEvent.DOM_DELTA_PIXEL ? 1 :
        event.deltaMode === WheelEvent.DOM_DELTA_LINE ? 16 : canvas.clientHeight;
      zoom(Math.exp(-event.deltaY * units * .002));
    }

    canvas.addEventListener("pointerdown", down);
    canvas.addEventListener("pointermove", move);
    canvas.addEventListener("pointerup", end);
    canvas.addEventListener("pointercancel", end);
    canvas.addEventListener("lostpointercapture", end);
    canvas.addEventListener("wheel", wheel, {passive: false});
    return () => {
      canvas.removeEventListener("pointerdown", down);
      canvas.removeEventListener("pointermove", move);
      canvas.removeEventListener("pointerup", end);
      canvas.removeEventListener("pointercancel", end);
      canvas.removeEventListener("lostpointercapture", end);
      canvas.removeEventListener("wheel", wheel);
      pointers.forEach((_, id) => { if (canvas.hasPointerCapture(id)) canvas.releasePointerCapture(id); });
      set({camera: previous});
    };
  }, [camera, frame, get, gl, invalidate, pose, scale, set, view]);
  return null;
}
