import {useLayoutEffect,useRef} from "react";
import {useThree} from "@react-three/fiber";
import {Plane,Raycaster,Vector2,Vector3} from "three";
import type {Item} from "../../lib/plan/scene";
import type {Pt} from "../../lib/plan/model";

export type CatalogDrag = {current:Item|null};
type Grab = {height:number;offset:Pt};
type Props = {
  scale:number;
  walkthrough:boolean;
  direct?:boolean;
  disabled:boolean;
  pending:Item|null;
  objects:Item[];
  catalogDrag:CatalogDrag;
  onPreview:(item:Item|null)=>void;
  onPlace:(item:Item,point:Pt|null)=>void;
  onSelect:(id:string)=>void;
};

export function FurniturePlacement(props:Props){
  const {gl,get}=useThree();
  const latest=useRef(props);
  useLayoutEffect(()=>{latest.current=props;});
  useLayoutEffect(()=>{
    const canvas=gl.domElement;
    const ray=new Raycaster();
    const coords=new Vector2();
    const heightPlane=new Plane(new Vector3(0,1,0));
    const planePoint=new Vector3();
    let gesture:{id:number;start:Pt;item:Item;grab?:Grab;moving:boolean}|null=null;
    let emptyTap:{id:number;start:Pt}|null=null;

    function hits(event:{clientX:number;clientY:number}){
      const bounds=canvas.getBoundingClientRect();
      if(event.clientX<bounds.left||event.clientX>=bounds.right||
        event.clientY<bounds.top||event.clientY>=bounds.bottom)return [];
      const {camera,scene}=get();
      coords.set(2*(event.clientX-bounds.left)/bounds.width-1,1-2*(event.clientY-bounds.top)/bounds.height);
      camera.updateMatrixWorld();
      ray.setFromCamera(coords,camera);
      return ray.intersectObjects(scene.children);
    }
    function ground(event:{clientX:number;clientY:number},movingId:string,grab?:Grab){
      const {scale,walkthrough}=latest.current;
      const bounds=canvas.getBoundingClientRect();
      if(event.clientX<bounds.left||event.clientX>=bounds.right||event.clientY<bounds.top||event.clientY>=bounds.bottom)return null;
      const intersections=hits(event);
      if(grab){
        heightPlane.constant=-grab.height;
        const point=ray.ray.intersectPlane(heightPlane,planePoint);
        if(!point)return null;
        return {x:point.x/scale+grab.offset.x,y:point.z/scale+grab.offset.y};
      }
      const hit=intersections.find(({object})=>{
        const data=object.userData;
        return data.walkFloor||data.furnishGround||
          (walkthrough&&!data.glass&&data.furnitureId!==movingId);
      });
      if(!hit||!(hit.object.userData.walkFloor||hit.object.userData.furnishGround))return null;
      return {x:hit.point.x/scale,y:hit.point.z/scale};
    }
    function down(event:PointerEvent){
      const {disabled,objects,pending,scale,direct}=latest.current;
      if(disabled||event.button!==0)return;
      if(gesture){
        if(direct&&!gesture.moving)gesture=null;
        else event.stopImmediatePropagation();
        return;
      }
      if(direct&&!event.isPrimary)return;
      const hit=pending?undefined:hits(event).find(({object})=>object.visible&&
        (!object.userData.glass||object.userData.furnitureId||object.userData.pickFixtureId));
      const item=pending??objects.find(object=>
        object.id===(hit?.object.userData.furnitureId??hit?.object.userData.pickFixtureId));
      const start={x:event.clientX,y:event.clientY};
      if(!item){
        if(!direct)emptyTap=emptyTap?null:{id:event.pointerId,start};
        return;
      }
      emptyTap=null;
      const grab=hit&&{height:hit.point.y,offset:{x:item.position.x-hit.point.x/scale,y:item.position.y-hit.point.z/scale}};
      gesture={id:event.pointerId,start,item,grab,moving:false};
      if(!direct){
        event.stopImmediatePropagation();
        canvas.setPointerCapture(event.pointerId);
      }
    }
    function move(event:PointerEvent){
      if(emptyTap?.id===event.pointerId&&Math.hypot(event.clientX-emptyTap.start.x,event.clientY-emptyTap.start.y)>=6)emptyTap=null;
      if(gesture?.id!==event.pointerId)return;
      if(!gesture.moving&&Math.hypot(event.clientX-gesture.start.x,event.clientY-gesture.start.y)<6){
        if(!latest.current.direct)event.stopImmediatePropagation();
        return;
      }
      if(!gesture.moving&&latest.current.direct)canvas.setPointerCapture(event.pointerId);
      event.stopImmediatePropagation();
      gesture.moving=true;
      const {item,grab}=gesture;
      const point=ground(event,item.id,grab);
      latest.current.onPreview(point?{...item,position:point}:null);
    }
    function end(event:PointerEvent){
      if(emptyTap?.id===event.pointerId){
        move(event);
        if(emptyTap&&event.type==="pointerup")latest.current.onSelect("");
        emptyTap=null;
      }
      if(gesture?.id!==event.pointerId)return;
      const {item,grab,moving}=gesture;
      gesture=null;
      if(latest.current.direct){
        if(!moving)return;
        event.preventDefault();
      }else event.stopImmediatePropagation();
      const {onPreview,onPlace,onSelect}=latest.current;
      onPreview(null);
      if(event.type!=="pointerup")return;
      if(!grab||moving)onPlace(item,ground(event,item.id,grab));
      else onSelect(item.id);
    }
    function dragOver(event:DragEvent){
      const {catalogDrag,disabled,onPreview}=latest.current;
      const item=catalogDrag.current;
      if(!item||disabled)return;
      event.preventDefault();
      if(event.dataTransfer)event.dataTransfer.dropEffect="copy";
      const point=ground(event,item.id);
      onPreview(point?{...item,position:point}:null);
    }
    function dragLeave(){latest.current.onPreview(null);}
    function drop(event:DragEvent){
      const {catalogDrag,disabled,onPlace,onPreview}=latest.current;
      const item=catalogDrag.current;
      if(!item||disabled)return;
      event.preventDefault();
      catalogDrag.current=null;
      onPreview(null);
      onPlace(item,ground(event,item.id));
    }
    const pointerListeners=[
      ["pointerdown",down],["pointermove",move],["pointerup",end],["pointercancel",end],["lostpointercapture",end],
    ] as const;
    for(const [type,listener] of pointerListeners)canvas.addEventListener(type,listener,true);
    canvas.addEventListener("dragover",dragOver);
    canvas.addEventListener("dragleave",dragLeave);
    canvas.addEventListener("drop",drop);
    return ()=>{
      for(const [type,listener] of pointerListeners)canvas.removeEventListener(type,listener,true);
      if(gesture&&canvas.hasPointerCapture(gesture.id))canvas.releasePointerCapture(gesture.id);
      canvas.removeEventListener("dragover",dragOver);
      canvas.removeEventListener("dragleave",dragLeave);
      canvas.removeEventListener("drop",drop);
    };
  },[gl,get]);
  return null;
}
