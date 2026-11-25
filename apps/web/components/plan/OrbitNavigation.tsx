import {OrbitControls} from "@react-three/drei";
import {useThree} from "@react-three/fiber";
import {useEffect,useRef,type ComponentProps,type ComponentRef} from "react";
import {MathUtils,Spherical,TOUCH,Vector3} from "three";
import type {Pt} from "../../lib/plan/model";
import {twoFingerDelta} from "../../lib/plan/touchGesture";

export function OrbitNavigation(props:ComponentProps<typeof OrbitControls>){
  const controls=useRef<ComponentRef<typeof OrbitControls>>(null);
  const {gl,invalidate}=useThree();
  useEffect(()=>{
    const canvas=gl.domElement;
    const pointerPositions=new Map<number,Pt>();
    const offset=new Vector3();
    const spherical=new Spherical();
    function rotate(azimuth:number,polar:number){
      const orbit=controls.current;
      if(!orbit?.enabled)return;
      spherical.setFromVector3(offset.copy(orbit.object.position).sub(orbit.target));
      spherical.theta+=azimuth;
      spherical.phi=MathUtils.clamp(spherical.phi+polar,orbit.minPolarAngle,orbit.maxPolarAngle);
      orbit.object.position.copy(offset.setFromSpherical(spherical.makeSafe()).add(orbit.target));
      orbit.update();
      invalidate();
    }
    function wheel(event:WheelEvent){
      // Chrome reports a trackpad pinch as Ctrl+wheel. Let OrbitControls zoom it.
      if(event.ctrlKey||event.deltaMode!==WheelEvent.DOM_DELTA_PIXEL)return;
      event.preventDefault();
      event.stopImmediatePropagation();
      rotate(-event.deltaX*.006,-event.deltaY*.006);
    }
    function down(event:PointerEvent){
      if(event.pointerType==="touch")pointerPositions.set(event.pointerId,{x:event.clientX,y:event.clientY});
    }
    function move(event:PointerEvent){
      const previous=pointerPositions.get(event.pointerId);
      if(!previous)return;
      const next={x:event.clientX,y:event.clientY};
      pointerPositions.set(event.pointerId,next);
      if(pointerPositions.size!==2)return;
      const other=[...pointerPositions].find(([id])=>id!==event.pointerId)![1];
      rotate(-twoFingerDelta(previous,next,other).twist,0);
    }
    function end(event:PointerEvent){pointerPositions.delete(event.pointerId);}
    canvas.addEventListener("wheel",wheel,{capture:true,passive:false});
    canvas.addEventListener("pointerdown",down);
    canvas.addEventListener("pointermove",move);
    canvas.addEventListener("pointerup",end);
    canvas.addEventListener("pointercancel",end);
    canvas.addEventListener("lostpointercapture",end);
    return ()=>{
      canvas.removeEventListener("wheel",wheel,true);
      canvas.removeEventListener("pointerdown",down);
      canvas.removeEventListener("pointermove",move);
      canvas.removeEventListener("pointerup",end);
      canvas.removeEventListener("pointercancel",end);
      canvas.removeEventListener("lostpointercapture",end);
    };
  },[gl,invalidate]);
  return <OrbitControls ref={controls} touches={{ONE:TOUCH.ROTATE,TWO:TOUCH.DOLLY_PAN}} {...props}/>;
}
