import { metersPerPixel, nodeMap, openingEnds, wallEnds } from "./derive";
import { fitsFloor, furnitureFit } from "./furnitureFit";
import { objectName } from "./furnitureCatalog";
import type { PlanModel } from "./model";
import type { Scene } from "./scene";
import { roomsOf, walkSpace } from "./walkSpace";

export type ReviewIssue = {
  kind: "object" | "view" | "room" | "wall" | "window" | "door";
  id: string;
  label: string;
  reason: string;
  missing?: boolean;
};
const same = (a:unknown,b:unknown) => JSON.stringify(a)===JSON.stringify(b);

export function sceneReview(plan:PlanModel, previous:PlanModel|null, scene:Scene):ReviewIssue[] {
  const scale=metersPerPixel(plan);
  if(!scale)return [];
  const priorScale=previous&&metersPerPixel(previous);
  const rooms=roomsOf(plan), oldRooms=previous?roomsOf(previous):[];
  const nodes=nodeMap(plan), oldNodes=previous&&nodeMap(previous);
  const currentSpace=walkSpace(plan,scale,scene);
  const oldSpace=previous&&priorScale?walkSpace(previous,priorScale,scene):null;
  const issues:ReviewIssue[]=[];
  const bounds=plan.imageTransform;
  for(const item of scene.objects){
    const fit=furnitureFit(plan,item,scene.objects,scale);
    const oldFit=previous&&priorScale?furnitureFit(previous,item,scene.objects,priorScale):null;
    const outside=item.position.x<0||item.position.y<0||item.position.x>bounds.width||item.position.y>bounds.height;
    const lostFloor=!!rooms.length&&!fitsFloor(plan,item,scale)&&(!previous||!priorScale||fitsFloor(previous,item,priorScale));
    const blocked=fit.swing.length+fit.clearance.length>(oldFit?oldFit.swing.length+oldFit.clearance.length:0);
    if(outside||lostFloor||blocked)issues.push({kind:"object",id:item.id,label:objectName(item.kind),
      reason:outside?"Outside the drawing":lostFloor?"Footprint crosses a room boundary":"A doorway may be obstructed",missing:outside});
  }
  for(const view of scene.views){
    const before=oldSpace?.validCamera(view.position,true);
    if(!currentSpace.clearFloor(view.position,true)||(before&&!currentSpace.validCamera(view.position,true)))
      issues.push({kind:"view",id:view.id,label:view.name,reason:"Camera needs a clear floor position"});
  }
  for(const id of Object.keys(scene.roomFloorMaterials??{})){
    const room=rooms.find(candidate=>candidate.id===id), old=oldRooms.find(candidate=>candidate.id===id);
    if(!room||!old||!same(room.polygon,old.polygon))issues.push({kind:"room",id,label:old?.label??room?.label??"Room floor finish",
      reason:room?"Room boundary changed":"Room needs reassignment",missing:!room});
  }
  for(const id of Object.keys(scene.wallFinishes??{})){
    const wall=plan.walls.find(candidate=>candidate.id===id), old=previous?.walls.find(candidate=>candidate.id===id);
    if(!wall||!old||!oldNodes||!same(wallEnds(plan,wall,nodes),wallEnds(previous!,old,oldNodes)))
      issues.push({kind:"wall",id,label:"Wall finish",reason:wall?"Finished wall moved":"Finished wall was removed",missing:!wall});
  }
  for(const id of Object.keys(scene.windowFinishes??{})){
    const window=plan.openings.find(candidate=>candidate.kind==="window"&&candidate.id===id);
    const old=previous?.openings.find(candidate=>candidate.id===id);
    if(!window||!old||!same(openingEnds(plan,window,nodes),openingEnds(previous!,old,oldNodes!)))
      issues.push({kind:"window",id,label:"Window frame finish",reason:window?"Finished window moved":"Finished window was removed",missing:!window});
  }
  for(const id of scene.closedDoorIds??[]){
    if(!plan.openings.some(door=>door.id===id&&door.kind==="door"&&door.status==="confirmed"&&!door.passage))
      issues.push({kind:"door",id,label:"Closed door",reason:"This door is no longer in the plan",missing:true});
  }
  return issues;
}
