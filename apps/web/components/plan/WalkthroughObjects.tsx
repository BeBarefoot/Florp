import {useEffect, useRef, type RefObject} from "react";
import {useFrame, useThree} from "@react-three/fiber";
import {Mesh, Raycaster, Vector2, Vector3} from "three";
import {Line} from "@react-three/drei";
import {itemBottom,type Item,type WallSide} from "../../lib/plan/scene";
import type {WallFace} from "../../lib/plan/wallFaces";
import type {WallPiece} from "../../lib/plan/mesh";
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
        (object.userData.openingId || object.userData.furnitureId || object.userData.pickFixtureId ||
          (!object.userData.glass && object.userData.maskId)));
      if(!hit)return null;
      const {openingId,wallId,positiveSide,furnitureId,pickFixtureId}=hit.object.userData;
      if(openingId)return {kind:"opening",id:openingId,point:hit.point};
      if(wallId){
        const z=hit.face?.normal.z??0;
        const local=camera.getWorldPosition(new Vector3());
        const positive=z!==0?z>0:hit.object.worldToLocal(local).z>=0;
        return {kind:"wall",id:wallId,point:hit.point,side:positive?positiveSide:otherSide(positiveSide)};
      }
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
      timer=setTimeout(()=>callbacks.current.onHover(target),target?55:110);
    }
    function down(event: PointerEvent) {
      cancelHover();
      if (event.button === 0 && event.isPrimary)
        press = {id: event.pointerId, x: event.clientX, y: event.clientY};
      else press = null;
    }
    function up(event: PointerEvent) {
      if (event.target!==canvas||!press||press.id!==event.pointerId) return;
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
    function leave(){
      cancelHover();
      callbacks.current.onHover(null);
    }
    canvas.addEventListener("pointermove", move);
    canvas.addEventListener("pointerdown", down);
    window.addEventListener("pointerup", up, true);
    canvas.addEventListener("pointercancel", cancel);
    canvas.addEventListener("pointerleave", leave);
    return () => {
      canvas.removeEventListener("pointermove", move);
      canvas.removeEventListener("pointerdown", down);
      window.removeEventListener("pointerup", up, true);
      canvas.removeEventListener("pointercancel", cancel);
      canvas.removeEventListener("pointerleave", leave);
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

export function SelectionBox({position,rotation,width,height,depth,selected}:{
  position:[number,number,number];rotation:number;width:number;height:number;depth:number;selected:boolean;
}){
  const corners:[number,number,number][]=[[-1,-1,-1],[1,-1,-1],[1,-1,1],[-1,-1,1],
    [-1,1,-1],[1,1,-1],[1,1,1],[-1,1,1]];
  const indices=[0,1,1,2,2,3,3,0,4,5,5,6,6,7,7,4,0,4,1,5,2,6,3,7];
  return <group position={position} rotation={[0,rotation,0]}>
    <Line segments points={indices.map(index=>{
      const [x,y,z]=corners[index];
      return [x*(width+.035)/2,y*(height+.035)/2,z*(depth+.035)/2];
    })} color={selected?"#20a67d":"#5dc6a4"} lineWidth={selected?2.6:1.6}
      depthTest={false} depthWrite={false} renderOrder={5} raycast={()=>{}}/>
  </group>;
}

export function ObjectHighlight({item,scale,selected}:{item:Item;scale:number;selected:boolean}){
  return <SelectionBox position={[item.position.x*scale,itemBottom(item)+item.height/2,item.position.y*scale]}
    rotation={-item.rotation*Math.PI/180} width={item.width} height={item.height} depth={item.depth} selected={selected}/>;
}

export function WallHighlight({faces,pieces,overview,selected}:{
  faces:WallFace[];pieces:WallPiece[];overview:boolean;selected:boolean;
}){
  return faces.map(face=>{
    const wall=pieces.find(piece=>piece.id===face.id);
    if(!wall)return null;
    const side=face.side===wall.positiveSide?1:-1;
    const left=Math.min(0,...wall.chunks.map(chunk=>chunk.start));
    const right=Math.max(wall.lengthM,...wall.chunks.map(chunk=>chunk.end));
    return <group key={face.id} position={[wall.centre[0],0,wall.centre[1]]} rotation={[0,wall.angle,0]}>
      <mesh position={[(left+right-wall.lengthM)/2,overview?wall.heightM+.008:wall.heightM-.065,
        overview?0:side*(wall.thicknessM/2+.008)]} raycast={()=>{}}>
        <boxGeometry args={[right-left,overview ? .014 : .11,overview ? wall.thicknessM : .014]}/>
        <meshBasicMaterial color={selected?"#168664":"#51ae91"} depthWrite={false}/>
      </mesh>
    </group>;
  });
}
