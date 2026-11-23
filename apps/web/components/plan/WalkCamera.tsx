import { useLayoutEffect, useMemo, useRef } from "react";
import { useThree } from "@react-three/fiber";
import { MathUtils, Vector3 } from "three";
import type { Pt } from "../../lib/plan/model";
import type { Frame, View } from "../../lib/plan/scene";
import { makeCamera } from "./SceneMesh";

const movementKeys = new Map([
  ["w",[1,0]], ["arrowup",[1,0]], ["s",[-1,0]], ["arrowdown",[-1,0]],
  ["a",[0,-1]], ["arrowleft",[0,-1]], ["d",[0,1]], ["arrowright",[0,1]],
]);

export function WalkCamera({view, scale, frame, canMove, pose, keyboard}: {
  keyboard?: boolean;
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
    let pitch = MathUtils.degToRad(view.pitch);

    const halfFov = Math.tan(MathUtils.degToRad(view.horizontalFov/2));
    function remember() {
      pose.current = {...view,position:{x:camera.position.x/scale,y:camera.position.z/scale},
        yaw:((MathUtils.radToDeg(yaw)%360+540)%360)-180, pitch:MathUtils.radToDeg(pitch),
        horizontalFov:MathUtils.clamp(2*MathUtils.radToDeg(Math.atan(halfFov/camera.zoom)),55,110)};
    }
    remember();
    function zoom(factor: number) {
      camera.zoom = MathUtils.clamp(camera.zoom * factor, halfFov/Math.tan(MathUtils.degToRad(55)), halfFov/Math.tan(MathUtils.degToRad(27.5)));
      camera.updateProjectionMatrix();
      remember();
      invalidate();
    }

    function step(forward:number, side:number) {
      // Short collision steps also catch thin walls during fast drags.
      const steps = Math.ceil(Math.hypot(forward,side) / .05);
      if (!steps) return;
      const dx = (Math.cos(yaw)*forward - Math.sin(yaw)*side) / steps;
      const dz = (Math.sin(yaw)*forward + Math.cos(yaw)*side) / steps;
      for (let i=0;i<steps;i++) {
        const x=camera.position.x+dx, z=camera.position.z+dz;
        if (!walkable.current({x:x/scale,y:z/scale})) break;
        camera.position.x=x;
        camera.position.z=z;
      }
    }

    const keys=new Set<string>();
    let animation=0, last=0;
    function tick(now:number){
      animation=0;
      let forward=0, side=0;
      for(const key of keys){
        const [f,s]=movementKeys.get(key)!;
        forward+=f;side+=s;
      }
      const magnitude=Math.hypot(forward,side);
      if(!magnitude){last=0;return;}
      const distance=Math.min((now-(last||now))/1000,.05)*1.8/magnitude;
      last=now;
      step(forward*distance,side*distance);
      remember();
      invalidate();
      animation=requestAnimationFrame(tick);
    }
    function wake(){if(!animation)animation=requestAnimationFrame(tick);}
    function keyDown(event:KeyboardEvent){
      if(event.defaultPrevented||event.altKey||event.ctrlKey||event.metaKey||
        (event.target instanceof HTMLElement&&event.target.closest("input,textarea,select,[contenteditable]")))return;
      const key=event.key.toLowerCase();
      if(!movementKeys.has(key))return;
      event.preventDefault();
      keys.add(key);wake();
    }
    function keyUp(event:KeyboardEvent){keys.delete(event.key.toLowerCase());wake();}
    function release(){
      keys.clear();
    }
    if(keyboard){
      window.addEventListener("keydown",keyDown);
      window.addEventListener("keyup",keyUp);
      window.addEventListener("blur",release);
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
      const vertical = before.y - after.y;
      const looking = keyboard && event.shiftKey;
      if (looking) pitch = MathUtils.clamp(pitch + vertical * .006, MathUtils.degToRad(-45), MathUtils.degToRad(30));
      else step(MathUtils.clamp(vertical * .012, -.6, .6),0);
      const headingX = Math.cos(yaw), headingZ = Math.sin(yaw);
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
      cancelAnimationFrame(animation);
      release();
      window.removeEventListener("keydown",keyDown);
      window.removeEventListener("keyup",keyUp);
      window.removeEventListener("blur",release);
      canvas.removeEventListener("pointerdown", down);
      canvas.removeEventListener("pointermove", move);
      canvas.removeEventListener("pointerup", end);
      canvas.removeEventListener("pointercancel", end);
      canvas.removeEventListener("lostpointercapture", end);
      canvas.removeEventListener("wheel", wheel);
      pointers.forEach((_, id) => { if (canvas.hasPointerCapture(id)) canvas.releasePointerCapture(id); });
      set({camera: previous});
    };
  }, [camera, get, gl, keyboard, invalidate, pose, scale, set, view]);
  return null;
}
