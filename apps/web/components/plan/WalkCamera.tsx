import { useLayoutEffect, useMemo, useRef } from "react";
import { useThree } from "@react-three/fiber";
import { MathUtils, Raycaster, Vector2, Vector3 } from "three";
import type { Pt } from "../../lib/plan/model";
import type { Frame, View } from "../../lib/plan/scene";
import { makeCamera } from "./SceneMesh";
import { MAX_HORIZONTAL_FOV_DEG } from "../../lib/plan/camera";
import {twoFingerDelta} from "../../lib/plan/touchGesture";

const movementKeys = new Map([
  ["w",[1,0]], ["arrowup",[1,0]], ["s",[-1,0]], ["arrowdown",[-1,0]],
  ["a",[0,-1]], ["arrowleft",[0,-1]], ["d",[0,1]], ["arrowright",[0,1]],
]);

export function WalkCamera({view, scale, frame, canMove, pose, keyboard, tapToWalk=false}: {
  keyboard?: boolean; tapToWalk?: boolean;
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
    const ray = new Raycaster();
    let tap: {id:number; origin:Pt}|null = null;
    let destination: Pt|null = null;
    let yaw = MathUtils.degToRad(view.yaw);
    let pitch = MathUtils.degToRad(view.pitch);

    const halfFov = Math.tan(MathUtils.degToRad(view.horizontalFov/2));
    function remember() {
      pose.current = {...view,position:{x:camera.position.x/scale,y:camera.position.z/scale},
        yaw:((MathUtils.radToDeg(yaw)%360+540)%360)-180, pitch:MathUtils.radToDeg(pitch),
        horizontalFov:MathUtils.clamp(2*MathUtils.radToDeg(Math.atan(halfFov/camera.zoom)),55,MAX_HORIZONTAL_FOV_DEG)};
    }
    remember();
    function zoom(factor: number) {
      camera.zoom = MathUtils.clamp(camera.zoom * factor, halfFov/Math.tan(MathUtils.degToRad(MAX_HORIZONTAL_FOV_DEG/2)), halfFov/Math.tan(MathUtils.degToRad(27.5)));
      camera.updateProjectionMatrix();
      remember();
      invalidate();
    }

    function travel(dx:number,dz:number,slide=false) {
      // Short collision steps also catch thin walls during fast drags.
      const steps = Math.ceil(Math.hypot(dx,dz) / .05);
      if (!steps) return false;
      dx/=steps;dz/=steps;
      const clear=(nextX:number,nextZ:number)=>walkable.current({x:nextX/scale,y:nextZ/scale});
      for(let i=0;i<steps;i++){
        const x=camera.position.x+dx,z=camera.position.z+dz;
        if(clear(x,z)){camera.position.x=x;camera.position.z=z;}
        else if(slide&&Math.abs(dx)>1e-8&&clear(x,camera.position.z))camera.position.x=x;
        else if(slide&&Math.abs(dz)>1e-8&&clear(camera.position.x,z))camera.position.z=z;
        else return false;
      }
      return true;
    }
    function step(forward:number,side:number){
      travel(Math.cos(yaw)*forward-Math.sin(yaw)*side,Math.sin(yaw)*forward+Math.cos(yaw)*side,tapToWalk);
    }
    function applyPose(){
      target.set(Math.cos(yaw)*Math.cos(pitch),Math.sin(pitch),Math.sin(yaw)*Math.cos(pitch));
      camera.lookAt(target.add(camera.position));
      remember();
      invalidate();
    }
    function tilt(amount:number){
      pitch=MathUtils.clamp(pitch+amount,MathUtils.degToRad(-45),MathUtils.degToRad(30));
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
      if(!magnitude&&!destination){last=0;return;}
      const seconds=Math.min((now-(last||now))/1000,.05);
      last=now;
      if(magnitude){
        const distance=seconds*1.8/magnitude;
        step(forward*distance,side*distance);
      }else if(destination&&seconds){
        const dx=destination.x-camera.position.x,dz=destination.y-camera.position.z;
        const distance=Math.hypot(dx,dz), stepSize=Math.min(distance,seconds*2.2);
        if(!distance||!travel(dx*stepSize/distance,dz*stepSize/distance)||stepSize>=distance)destination=null;
      }
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
      if(key.startsWith("arrow")&&event.target instanceof HTMLElement&&event.target.closest("[data-tour-tools]"))return;
      event.preventDefault();
      destination=null;
      keys.add(key);wake();
    }
    function keyUp(event:KeyboardEvent){keys.delete(event.key.toLowerCase());wake();}
    function release(){
      keys.clear();
      destination=null;
    }
    if(keyboard){
      window.addEventListener("keydown",keyDown);
      window.addEventListener("keyup",keyUp);
      window.addEventListener("blur",release);
    }

    function down(event: PointerEvent) {
      if (event.button !== 0 || pointers.size === 2) return;
      const origin={x:event.clientX,y:event.clientY};
      destination=null;
      tap=tapToWalk&&!pointers.size?{id:event.pointerId,origin}:null;
      pointers.set(event.pointerId,origin);
      canvas.setPointerCapture(event.pointerId);
    }

    function move(event: PointerEvent) {
      const before = pointers.get(event.pointerId);
      if (!before) return;
      const after = {x: event.clientX, y: event.clientY};
      pointers.set(event.pointerId, after);
      if (pointers.size === 2) {
        const other = [...pointers].find(([id]) => id !== event.pointerId)![1];
        const gesture=twoFingerDelta(before,after,other);
        yaw+=gesture.twist;
        step(MathUtils.clamp(-gesture.y*.012,-.6,.6),MathUtils.clamp(gesture.x*.011,-.6,.6));
        if(gesture.pinch!==1)zoom(gesture.pinch);
        applyPose();
        return;
      }
      if(tap?.id===event.pointerId){
        if(Math.hypot(after.x-tap.origin.x,after.y-tap.origin.y)<6)return;
        tap=null;
      }
      yaw += (after.x - before.x) * .007;
      const vertical = before.y - after.y;
      const looking = keyboard && event.shiftKey;
      if (looking) tilt(vertical*.006);
      else step(MathUtils.clamp(vertical * .012, -.6, .6),0);
      applyPose();
    }

    function end(event: PointerEvent) {
      pointers.delete(event.pointerId);
      if(tap?.id!==event.pointerId)return;
      const origin=tap.origin;
      tap=null;
      if(event.type!=="pointerup"||Math.hypot(event.clientX-origin.x,event.clientY-origin.y)>=6)return;
      const bounds=canvas.getBoundingClientRect();
      ray.setFromCamera(new Vector2(
        2*(event.clientX-bounds.left)/bounds.width-1,
        1-2*(event.clientY-bounds.top)/bounds.height,
      ),camera);
      const surface=ray.intersectObjects(get().scene.children).find(hit=>!hit.object.userData.glass);
      if(surface?.object.userData.walkFloor){
        destination={x:surface.point.x,y:surface.point.z};
        wake();
      }
    }

    function wheel(event: WheelEvent) {
      event.preventDefault();
      const units = event.deltaMode === WheelEvent.DOM_DELTA_PIXEL ? 1 :
        event.deltaMode === WheelEvent.DOM_DELTA_LINE ? 16 : canvas.clientHeight;
      if(!event.ctrlKey&&(event.shiftKey||Math.abs(event.deltaX)>Math.abs(event.deltaY))){
        yaw+=event.deltaX*units*.005;
        tilt(-event.deltaY*units*.004);
        applyPose();
      }else zoom(Math.exp(-event.deltaY * units * .002));
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
  }, [camera, get, gl, keyboard, invalidate, pose, scale, set, tapToWalk, view]);
  return null;
}
