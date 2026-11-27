import {useEffect} from "react";
import {useThree} from "@react-three/fiber";
import {Raycaster,Vector2} from "three";
import type {Pt} from "../../lib/plan/model";

export function FloorPicker({scale,onPick}:{scale:number;onPick:(point:Pt|null,yaw:number)=>void}){
  const {gl,get}=useThree();
  useEffect(()=>{
    const canvas=gl.domElement;
    const pointers=new Set<number>();
    let start:PointerEvent|null=null;
    const ray=new Raycaster();
    function down(event:PointerEvent){
      if(event.button!==0)return;
      pointers.add(event.pointerId);
      start=pointers.size===1?event:null;
    }
    function move(event:PointerEvent){
      if(start?.pointerId===event.pointerId&&Math.hypot(event.clientX-start.clientX,event.clientY-start.clientY)>6)
        start=null;
    }
    function cancel(event:PointerEvent){
      pointers.delete(event.pointerId);
      if(start?.pointerId===event.pointerId)start=null;
    }
    function up(event:PointerEvent){
      move(event);
      const tap=start?.pointerId===event.pointerId;
      cancel(event);
      if(!tap||event.defaultPrevented)return;
      const bounds=canvas.getBoundingClientRect();
      const {camera,scene}=get();
      ray.setFromCamera(new Vector2(
        2*(event.clientX-bounds.left)/bounds.width-1,
        1-2*(event.clientY-bounds.top)/bounds.height,
      ),camera);
      const hit=ray.intersectObjects(scene.children).find(({object})=>!object.userData.glass);
      const yaw=Math.atan2(ray.ray.direction.z,ray.ray.direction.x)*180/Math.PI;
      onPick(hit?.object.userData.walkFloor
        ?{x:hit.point.x/scale,y:hit.point.z/scale}:null,yaw);
    }
    canvas.addEventListener("pointerdown",down);
    canvas.addEventListener("pointermove",move);
    canvas.addEventListener("pointerup",up);
    canvas.addEventListener("pointercancel",cancel);
    canvas.addEventListener("lostpointercapture",cancel);
    return ()=>{
      canvas.removeEventListener("pointerdown",down);
      canvas.removeEventListener("pointermove",move);
      canvas.removeEventListener("pointerup",up);
      canvas.removeEventListener("pointercancel",cancel);
      canvas.removeEventListener("lostpointercapture",cancel);
    };
  },[get,gl,onPick,scale]);
  return null;
}
