import {useEffect, useRef, type RefObject} from "react";
import {useFrame, useThree} from "@react-three/fiber";
import {Mesh, Raycaster, Vector2, Vector3} from "three";
import type {Item, WallSide} from "../../lib/plan/scene";
import {otherSide} from "../../lib/plan/wallMaterials";

export type WalkTarget = {id:string;point:Vector3} & (
  {kind:"object"|"opening"} | {kind:"wall";side:WallSide}
);

export const targetKey = (target:WalkTarget|null) =>
  target ? [target.kind,target.id,target.kind==="wall"?target.side:""].join(":") : "";

export function WalkthroughObjects({onHover, onTap}: {
  onHover: (target: WalkTarget|null) => void;
  onTap: (target: WalkTarget|null) => void;
}) {
  const {gl, get} = useThree();
  const callbacks = useRef({onHover, onTap});
  callbacks.current = {onHover, onTap};
  useEffect(() => {
    const canvas = gl.domElement;
    const ray = new Raycaster();
    const pointer = new Vector2();
    let press: {id: number; x: number; y: number} | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let upcoming = "";
    function pick(event: PointerEvent): WalkTarget|null {
      const bounds = canvas.getBoundingClientRect();
      if (!bounds.width || !bounds.height) return null;
      pointer.set(2 * (event.clientX - bounds.left) / bounds.width - 1,
        1 - 2 * (event.clientY - bounds.top) / bounds.height);
      const {camera, scene} = get();
      camera.updateMatrixWorld();
      ray.setFromCamera(pointer, camera);
      const hit = ray.intersectObjects(scene.children, true).find(({object}) =>
        object instanceof Mesh && object.visible &&
        (object.userData.openingId || (!object.userData.glass &&
        (object.userData.maskId || object.userData.pickFixtureId))));
      if(!hit)return null;
      const {openingId,wallId,positiveSide,furnitureId,pickFixtureId}=hit.object.userData;
      if(openingId)return {kind:"opening",id:openingId,point:hit.point};
      if(wallId&&Math.abs(hit.face?.normal.z??0)>.9)
        return {kind:"wall",id:wallId,point:hit.point,side:hit.face!.normal.z>0?positiveSide:otherSide(positiveSide)};
      const objectId=furnitureId??pickFixtureId;
      return objectId?{kind:"object",id:objectId,point:hit.point}:null;
    }
    function cancelHover(){
      clearTimeout(timer);
      upcoming="";
    }
    function move(event: PointerEvent) {
      if(press?.id===event.pointerId&&Math.hypot(press.x-event.clientX,press.y-event.clientY)>=6){
        press=null;
        callbacks.current.onTap(null);
      }
      if (event.pointerType !== "mouse" || event.buttons) return;
      const target=pick(event);
      const key=targetKey(target);
      if(key===upcoming)return;
      cancelHover();
      upcoming=key;
      if(target)timer=setTimeout(()=>callbacks.current.onHover(target),170);
    }
    function down(event: PointerEvent) {
      cancelHover();
      if (event.button === 0 && event.isPrimary)
        press = {id: event.pointerId, x: event.clientX, y: event.clientY};
      else press = null;
    }
    function up(event: PointerEvent) {
      if (!press || press.id !== event.pointerId) return;
      const isTap = Math.hypot(press.x - event.clientX, press.y - event.clientY) < 6;
      press = null;
      if (isTap) {
        const target = pick(event);
        callbacks.current.onTap(target);
        if (target) event.preventDefault();
      }
    }
    function cancel() {
      press = null;
    }
    canvas.addEventListener("pointermove", move);
    canvas.addEventListener("pointerdown", down);
    canvas.addEventListener("pointerup", up, true);
    canvas.addEventListener("pointercancel", cancel);
    canvas.addEventListener("pointerleave", cancelHover);
    return () => {
      canvas.removeEventListener("pointermove", move);
      canvas.removeEventListener("pointerdown", down);
      canvas.removeEventListener("pointerup", up, true);
      canvas.removeEventListener("pointercancel", cancel);
      canvas.removeEventListener("pointerleave", cancelHover);
      cancelHover();
    };
  }, [gl, get]);
  return null;
}

export function WalkTargetAnchor({target,element}:{target:WalkTarget;element:RefObject<HTMLDivElement|null>}){
  const {camera,size,invalidate}=useThree();
  const projected=useRef(new Vector3());
  const local=useRef(new Vector3());
  useFrame(()=>{
    const menu=element.current;
    if(!menu)return;
    camera.updateMatrixWorld();
    const point=projected.current.copy(target.point).project(camera);
    const x=(point.x+1)*size.width/2, y=(1-point.y)*size.height/2;
    const visible=local.current.copy(target.point).applyMatrix4(camera.matrixWorldInverse).z<0 &&
      x>=0&&x<=size.width&&y>=0&&y<=size.height;
    menu.style.visibility=visible?"visible":"hidden";
    if(!visible)return;
    const gap=10, margin=10;
    const left=x<menu.offsetWidth+gap+margin||x+menu.offsetWidth+gap<=size.width-margin
      ?x+gap:x-menu.offsetWidth-gap;
    menu.style.left=Math.max(margin,Math.min(left,size.width-menu.offsetWidth-margin))+"px";
    menu.style.top=Math.max(margin,Math.min(y-22,size.height-menu.offsetHeight-margin))+"px";
  });
  useEffect(()=>{
    const menu=element.current;
    if(!menu)return;
    invalidate();
    const observer=new ResizeObserver(()=>invalidate());
    observer.observe(menu);
    return ()=>observer.disconnect();
  },[element,invalidate]);
  return null;
}

export function ObjectHighlight({item, scale}: {item: Item; scale: number}) {
  return <group position={[item.position.x * scale, 0, item.position.y * scale]}
    rotation={[0, -item.rotation * Math.PI / 180, 0]}>
    <mesh position={[0, .012, 0]} raycast={()=>{}}>
      <boxGeometry args={[item.width + .05, .014, item.depth + .05]}/>
      <meshBasicMaterial color="#b99055" transparent opacity={.5} depthWrite={false}/>
    </mesh>
  </group>;
}
