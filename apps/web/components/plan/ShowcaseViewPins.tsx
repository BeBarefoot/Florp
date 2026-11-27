import {useRef,useState,type PointerEvent,type RefObject} from "react";
import {Html} from "@react-three/drei";
import {useThree} from "@react-three/fiber";
import {Raycaster,Vector2,Vector3} from "three";
import type {Pt} from "../../lib/plan/model";
import type {View} from "../../lib/plan/scene";

type Drag = {id:string;pointer:number;origin:Pt;start:Vector3;moved:boolean};
const pinHeight=2;

export function ShowcaseViewPins({views,scale,portal,disabled,onVisit,onMove}:{
  views:View[];scale:number;portal:RefObject<HTMLDivElement>;disabled:boolean;
  onVisit:(index:number)=>void;onMove:(view:View,position:Pt)=>void;
}){
  const {camera,gl}=useThree();
  const ray=useRef(new Raycaster());
  const drag=useRef<Drag|null>(null);
  const suppressClick=useRef(false);
  const [preview,setPreview]=useState<{id:string;position:Pt}|null>(null);
  const groups:{position:Pt;indices:number[]}[]=[];
  views.forEach((view,index)=>{
    const group=groups.find(({position})=>Math.hypot(position.x-view.position.x,position.y-view.position.y)*scale<.35);
    if(group)group.indices.push(index);
    else groups.push({position:view.position,indices:[index]});
  });

  function intersect(event:PointerEvent<HTMLButtonElement>){
    const bounds=gl.domElement.getBoundingClientRect();
    camera.updateMatrixWorld();
    ray.current.setFromCamera(new Vector2(
      2*(event.clientX-bounds.left)/bounds.width-1,
      1-2*(event.clientY-bounds.top)/bounds.height,
    ),camera);
    const {origin,direction}=ray.current.ray;
    // Project onto the pin plane and bound the projection at the horizon.
    const offset=pinHeight-origin.y;
    const towardPlane=Math.sign(offset)||-1;
    return ray.current.ray.at(Math.max(.001,Math.abs(offset))/Math.max(.04,direction.y*towardPlane),new Vector3());
  }
  function positionAt(view:View,event:PointerEvent<HTMLButtonElement>,start:Vector3):Pt{
    const point=intersect(event);
    return {x:view.position.x+(point.x-start.x)/scale,y:view.position.y+(point.z-start.z)/scale};
  }
  function pointerDown(event:PointerEvent<HTMLButtonElement>,view:View){
    if(event.button!==0||!event.isPrimary)return;
    suppressClick.current=false;
    if(disabled)return;
    const start=intersect(event);
    drag.current={id:view.id,pointer:event.pointerId,origin:{x:event.clientX,y:event.clientY},start,moved:false};
    event.currentTarget.setPointerCapture(event.pointerId);
  }
  function pointerMove(event:PointerEvent<HTMLButtonElement>,view:View){
    const active=drag.current;
    if(!active||active.id!==view.id||active.pointer!==event.pointerId)return;
    if(!active.moved&&Math.hypot(event.clientX-active.origin.x,event.clientY-active.origin.y)<6)return;
    active.moved=true;
    setPreview({id:view.id,position:positionAt(view,event,active.start)});
  }
  function cancel(){
    drag.current=null;
    setPreview(null);
  }
  function pointerUp(event:PointerEvent<HTMLButtonElement>,view:View){
    const active=drag.current;
    if(!active||active.id!==view.id||active.pointer!==event.pointerId)return;
    cancel();
    if(!active.moved)return;
    suppressClick.current=true;
    onMove(view,positionAt(view,event,active.start));
  }

  return <>
    {groups.map(({position,indices})=><Html key={views[indices[0]].id} portal={portal} center
      position={[position.x*scale,pinHeight,position.y*scale]} zIndexRange={[2,1]}>
      <div className="show-pin-group">{indices.map(index=>{
        const view=views[index];
        return <button key={view.id} type="button" draggable={false} className="show-pin"
          aria-label={"Visit "+view.name} data-movable={!disabled}
          data-dragging={preview?.id===view.id}
          title={"Drag to move "+view.name}
          onPointerDown={event=>pointerDown(event,view)} onPointerMove={event=>pointerMove(event,view)}
          onPointerUp={event=>pointerUp(event,view)} onPointerCancel={cancel} onLostPointerCapture={cancel}
          onClick={event=>{
            if(event.detail!==0&&suppressClick.current){suppressClick.current=false;return;}
            onVisit(index);
          }}>{index+1}</button>;
      })}</div>
    </Html>)}
    {preview&&<Html portal={portal} center position={[preview.position.x*scale,pinHeight,preview.position.y*scale]}
      zIndexRange={[2,1]} style={{pointerEvents:"none"}} wrapperClass="show-room-label">
      <span className="show-pin-preview" aria-hidden>
        {views.findIndex(view=>view.id===preview.id)+1}
      </span>
    </Html>}
  </>;
}
