import {savedPose} from "./camera";
import {metersPerPixel, nodeMap, openingEnds, wallEnds} from "./derive";
import type {PlanModel, Pt} from "./model";
import {contains, floorFinishes, promptFor, type Scene, type View, type Capture} from "./scene";
import {roomsOf} from "./walkSpace";
import {floorMaterialFor} from "./floorMaterials";

export function renderPrompt(plan:PlanModel, scene:Scene, view:View, frame:{width:number;height:number}, facts:string[], approximate=false, capture?:Capture|null) {
  const scale=metersPerPixel(plan);
  if (!scale) throw new Error("A display scale is required for the camera specification.");
  const pose=savedPose(view,scale,frame.width/frame.height);
  const nodes=nodeMap(plan);
  const xz=(p:Pt)=>[p.x*scale,p.y*scale];
  const length=(a:Pt,b:Pt)=>Math.hypot(a.x-b.x,a.y-b.y)*scale;
  const rooms=roomsOf(plan);
  const geometry={
    imageCoordinates:capture?"Visible object boundsXY are inclusive [left,top,right,bottom] pixels from the top left. pixels counts only unoccluded pixels. depthMm is the minimum and maximum visible camera-space depth in millimetres. A null region is fully hidden.":undefined,
    coordinates:"Metres from the top-left of the floor plan. +X right, +Y up, +Z down the plan. Floor coordinates are [X,Z].",
    scale:approximate?"Approximate display scale": "Plan reference scale",
    metresPerPixel:scale,
    camera:{projection:"rectilinear perspective",eyeXYZ:pose.position,forwardUnitXYZ:pose.direction,
      yawDegreesFromXToZ:view.yaw,pitchDegreesUp:view.pitch,rollDegrees:0,
      horizontalFovDegrees:view.horizontalFov,verticalFovDegrees:pose.verticalFovDeg,
      framePixels:[frame.width,frame.height],clipMetres:[.03,80],
      insideRooms:rooms.filter(r=>contains(view.position,r.polygon)).map(r=>r.id)},
    floorFinish:scene.floorMaterial??floorFinishes[scene.floorFinish??"default"].name,
    rooms:rooms.map(r=>({id:r.id,label:r.label,type:r.roomType,perimeterXZ:r.polygon.map(xz),
      floorFinish:floorMaterialFor(scene,r.id)??floorFinishes[scene.floorFinish??"default"].name,
      successiveEdgeLengths:r.polygon.map((p,i)=>length(p,r.polygon[(i+1)%r.polygon.length])),
      ceilingHeight:r.ceilingHeightM??2.8,defaultCeiling:r.ceilingHeightM==null})),
    walls:plan.walls.map(w=>{
      const [a,b]=wallEnds(plan,w,nodes);
      return {id:w.id,centrelineXZ:[xz(a),xz(b)],length:length(a,b),thickness:w.thicknessPx*scale,height:w.heightM,material:w.material};
    }),
    openings:plan.openings.filter(o=>o.status==="confirmed").map(o=>{
      const ends=openingEnds(plan,o,nodes);
      return {id:o.id,kind:o.kind,wall:o.hostWallId,endpointsXZ:ends?.map(xz),width:o.widthPx*scale,
        sill:o.sillM,height:o.heightM,...(o.kind==="door"?{hinge:o.hinge,swing:o.swing,closed:scene.closedDoorIds?.includes(o.id)??false}:{})};
    }),
    stairs:plan.stairs?.map(s=>({id:s.id,risePerStep:s.riseM,treadsXZ:s.treads.map(poly=>poly.map(xz))})),
    objects:scene.objects.map(({position,rotation,...o},i)=>({...o,
      ...(capture?{visibleInFrame:capture.visibleRegions[1000+i]??null}:{}),centreXZ:xz(position),rotationDegreesFromXToZ:rotation})),
  };
  const framing=scene.objects.flatMap((object,i)=>{
    const region=capture?.visibleRegions[1000+i];
    if(!region)return [];
    const [left,top,right,bottom]=region.boundsXY;
    const percent=100*region.pixels/(frame.width*frame.height);
    return [`Visible ${object.kind} occupies ${percent.toFixed(2)}% of the image, within pixels (${left}, ${top}) to (${right}, ${bottom}) from the upper left. Preserve that visible portion.`];
  });
  return [promptFor(view,facts,scene.style),
    `Camera eye [X,Y,Z] = [${pose.position.join(", ")}] m, looking along [${pose.direction.join(", ")}]. Frame ${frame.width} × ${frame.height} px.`,
    ...framing,
    "Use each room’s specified floor material, colour and pattern dimensions on its visible floor.",
    "Match the supplied frame edge for edge. Preserve occlusion, silhouettes, perspective and cropping. Keep off-camera geometry outside the frame.",
    JSON.stringify(geometry)].join("\n");
}

export function downloadPrompt(prompt:string) {
  const url=URL.createObjectURL(new Blob([prompt],{type:"text/plain;charset=utf-8"}));
  const link=document.createElement("a");
  link.href=url;
  link.download="florp-view-prompt.txt";
  link.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
}
