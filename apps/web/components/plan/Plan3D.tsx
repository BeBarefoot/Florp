"use client";
import {OrbitNavigation} from "./OrbitNavigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Canvas } from "@react-three/fiber";
import { Grid } from "@react-three/drei";
import type { PlanModel, Pt, RoomType } from "../../lib/plan/model";
import { ROOM_TYPES } from "../../lib/plan/model";
import { metersPerPixel, openingEnds, scaleCheck } from "../../lib/plan/derive";
import { meshSignature, wallPieces } from "../../lib/plan/mesh";
import { API, request } from "../../lib/api";
import { newUuid } from "../../lib/uuid";
import { floorFinishes, type FloorFinish, contains, footprint, intersects, newItem, type Capture, type Frame, type Item,
  type Job, type ObjectKind, type Saved, type Scene, type View, type WallMaterial, type WallSide } from "../../lib/plan/scene";
import {objectKinds,objectName,tvDimensions,tvInches,tvSizeRange} from "../../lib/plan/furnitureCatalog";
import {renderPrompt, downloadPrompt} from "../../lib/plan/renderPrompt";
import {detectedPreviewItems, visibleDetections} from "../../lib/plan/detectedFurniture";
import { CaptureBridge, EyeCamera, SceneMesh } from "./SceneMesh";
import { roomsOf, walkSpace } from "../../lib/plan/walkSpace";
import { WalkCamera } from "./WalkCamera";
import { unmatchedFloorFinishes } from "../../lib/plan/floorMaterials";
import { setWallSurface } from "../../lib/plan/wallMaterials";
import {sceneReview,type ReviewIssue} from "../../lib/plan/sceneReview";
import ClosetDesigner from "./ClosetDesigner";
import RenderComparison from "./RenderComparison";

type Mode = "camera" | "aim" | "sight" | "object" | "move" | "move-view" | "zone" | null;
type CaptureFn = (v: View, s: number, f: Frame, key: string) => Capture;
const initialFrame: Frame = { width:1024,height:768,configured:false,model:"",provider:"fal" };
const initial: Saved = {revision:0,planRevision:null,config:{views:[],objects:[],style:""}};
const active = (j: Job) => ["submitting","queued","running"].includes(j.status);
const json = (method: string, body: unknown) => ({method,headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
const wrap = (angle:number) => ((angle+180)%360+360)%360-180;
const points = (poly:Pt[]) => poly.map(p=>`${p.x},${p.y}`).join(" ");
const sleepPollMs=3000;
const fixtureName = (o: Item) => o.kind==="wardrobe"?"Closet":objectName(o.kind);

export default function Plan3D({model:m, phone=false, dirty=false, designerOpen=false, onPlanEdit, savePlan}:{
  model:PlanModel;designerOpen?:boolean; phone?:boolean;dirty?:boolean;onPlanEdit?:(m:PlanModel)=>void;savePlan?:()=>Promise<PlanModel|null>;
}) {
  const scale=metersPerPixel(m)!;
  const check=scaleCheck(m);
  const path=`/blueprints/${m.id}`;
  const [saved,setSaved]=useState<Saved|null>(null), [scene,setScene]=useState<Scene>(initial.config);
  const [finishWallId,setFinishWallId]=useState("");
  const [wallSide,setWallSide]=useState<WallSide>("a");
  const [frame,setFrame]=useState(initialFrame), [jobs,setJobs]=useState<Job[]>([]);
  const [viewId,setViewId]=useState(""), [itemId,setItemId]=useState(""), [roomId,setRoomId]=useState("");
  const [mode,setMode]=useState<Mode>(null), [kind,setKind]=useState<ObjectKind>("bed");
  const [zoneStart,setZoneStart]=useState<Pt|null>(null);
  const [cameraMode,setCameraMode]=useState<"orbit"|"preview"|"walk">("orbit");
  const [capture,setCapture]=useState<Capture|null>(null);
  const [sight,setSight]=useState(""), [message,setMessage]=useState(""), [busy,setBusy]=useState(false);
  const [authorized,setAuthorized]=useState(false), [variant,setVariant]=useState("");
  const [editObject,setEditObject]=useState("");
  const [selectedJob,setSelectedJob]=useState("");
  const [recoveringRender,setRecoveringRender]=useState(false);
  const [recoveryMessage,setRecoveryMessage]=useState("");
  const [undo,setUndo]=useState<Scene[]>([]);
  const [ready,setReady]=useState(false);
  const [fixtureScan,setFixtureScan]=useState<{planRevision:number;suggestions:Item[]}|null>(null);
  const [fixtureId,setFixtureId]=useState("");
  const [showDetections,setShowDetections]=useState(true);
  const [showBlueprint,setShowBlueprint]=useState(false);
  const walkPose=useRef<View|null>(null);
  const [design,setDesign]=useState(false);
  const [mapOpen,setMapOpen]=useState(false);
  const showMap=phone&&!design&&(mapOpen||mode==="camera"||mode==="aim"||!viewId);
  const captureFn=useRef<CaptureFn|null>(null);
  const submitRetry=useRef<{key:string; signature:string}|null>(null);
  const bind=useCallback((f:CaptureFn|null)=>{captureFn.current=f;setReady(!!f);},[]);
  const view=scene.views.find(v=>v.id===viewId)??scene.views[0];
  const item=scene.objects.find(o=>o.id===itemId);
  const rooms=useMemo(()=>roomsOf(m),[m]);
  const finishWall=m.walls.find(wall=>wall.id===finishWallId);
  const wallFinish=finishWall&&scene.wallFinishes?.[finishWall.id]?.[wallSide];
  function setWallFinish(material:WallMaterial|null){
    if(!finishWall)return;
    change({...scene,wallFinishes:setWallSurface(scene.wallFinishes,finishWall.id,wallSide,material)});
  }
  const oldRevision=saved?.planRevision;
  const needsReview=oldRevision!=null&&oldRevision!==m.revision;
  const [history,setHistory]=useState<{source:number;plan:PlanModel|null}|null>(null);
  const [reviewed,setReviewed]=useState<Record<string,true>>({});
  useEffect(()=>{
    setReviewed({});
    if(!needsReview||oldRevision==null)return;
    const controller=new AbortController();
    request<{revision:number;model:PlanModel}[]>(path+"/plan/history",{signal:controller.signal})
      .then(history=>{if(!controller.signal.aborted)setHistory({source:oldRevision,plan:history.find(entry=>entry.revision===oldRevision)?.model??null});})
      .catch(()=>{if(!controller.signal.aborted)setHistory({source:oldRevision,plan:null});});
    return ()=>controller.abort();
  },[needsReview,oldRevision,m.revision,path]);
  const reviewPending=needsReview&&history?.source!==oldRevision;
  const reviewIssues=useMemo(()=>needsReview&&!dirty&&!reviewPending?sceneReview(m,history?.plan??null,scene):[],
    [needsReview,m,dirty,reviewPending,history,scene]);
  const issueKey=(issue:ReviewIssue)=>issue.kind+":"+issue.id+":"+issue.reason;
  // A finish explicitly assigned to a current room during this edit has
  // already been reviewed. Continue to check every finish from the saved scene.
  const unresolved=reviewIssues.filter(issue=>!reviewed[issueKey(issue)]&&
    (issue.kind!=="room"||issue.missing||Object.hasOwn(saved?.config.roomFloorMaterials??{},issue.id)));
  function removeReviewItem(issue:ReviewIssue){
    const {id,kind}=issue;
    if(kind==="object") change({...scene,objects:scene.objects.filter(item=>item.id!==id)});
    if(kind==="view") change({...scene,views:scene.views.filter(view=>view.id!==id)});
    if(kind==="room") resolveFinish(id);
    if(kind==="door") change({...scene,closedDoorIds:scene.closedDoorIds?.filter(key=>key!==id)});
    if(kind==="wall"){
      const wallFinishes={...scene.wallFinishes};
      delete wallFinishes[id];
      change({...scene,wallFinishes});
    }
    if(kind==="window"){
      const windowFinishes={...scene.windowFinishes};
      delete windowFinishes[id];
      change({...scene,windowFinishes});
    }
  }
  const unmatchedFinishes=unmatchedFloorFinishes(scene,rooms);
  function resolveFinish(previousRoom:string, destination?:string) {
    const materials={...scene.roomFloorMaterials};
    if(destination) materials[destination]=materials[previousRoom];
    delete materials[previousRoom];
    change({...scene,roomFloorMaterials:materials});
  }
  const room=rooms.find(r=>r.id===roomId);
  const pieces=useMemo(()=>wallPieces(m),[m]);
  const nodeMap=useMemo(()=>new Map(m.nodes.map(n=>[n.id,n])),[m.nodes]);
  const finishSideLines=finishWall&&(["a","b"] as const).map(side=>{
    const a=nodeMap.get(finishWall.a)!, b=nodeMap.get(finishWall.b)!;
    const length=Math.hypot(b.x-a.x,b.y-a.y);
    const sign=(finishWall.a<finishWall.b)===(side==="a")?1:-1;
    const distance=finishWall.thicknessPx/2+.08/scale;
    const at=(fraction:number)=>({
      x:a.x+(b.x-a.x)*fraction-(b.y-a.y)/length*distance*sign,
      y:a.y+(b.y-a.y)*fraction+(b.x-a.x)/length*distance*sign,
    });
    const roomIndex=rooms.findIndex(room=>[.25,.5,.75].some(fraction=>contains(at(fraction),room.polygon)));
    return {side,start:at(.18),end:at(.82),room:roomIndex<0?"":rooms[roomIndex].label||`Room ${roomIndex+1}`};
  });
  const w=m.imageTransform.width*scale, h=m.imageTransform.height*scale;
  const cameraTarget:[number,number,number]=[w/2,0,h/2];
  const fingerprintFor=(v:View|undefined)=>JSON.stringify([m,v,scene.objects,scene.closedDoorIds,scene.designPreset,scene.floorFinish,scene.floorMaterial,scene.roomFloorMaterials,scene.wallFinishes,scene.windowFinishes,frame.width,frame.height]);
  const fingerprint=fingerprintFor(view);
  const shot=capture?.fingerprint===fingerprint?capture:null;
  const fixtureSuggestions=fixtureScan?.planRevision===m.revision&&!dirty?
    fixtureScan.suggestions.filter(o=>!scene.dismissedFixtureIds?.includes(o.id)&&
      !scene.objects.some(p=>p.id===o.id||(p.kind===o.kind&&contains(o.position,footprint(p,scale))&&
        contains(p.position,footprint(o,scale))))):[];
  const detections=useMemo(()=>detectedPreviewItems(m,scale),[m,scale]);
  const detectedObjects=showDetections?visibleDetections(detections,scene.objects,scale):[];
  const fixture=fixtureSuggestions.find(o=>o.id===fixtureId)??fixtureSuggestions[0];
  const edited=!!saved&&(JSON.stringify(scene)!==JSON.stringify(saved.config)||saved.planRevision!==m.revision);

  useEffect(()=>{
    let cancelled=false;
    request<Saved>(path+"/scene").then(r=>{if(!cancelled){setSaved(r);setScene(r.config);setViewId(r.config.views[0]?.id??"");setCameraMode(r.config.views.length?(phone?"walk":"preview"):"orbit");if(phone&&!r.config.views.length)setMode("camera");}})
      .catch(e=>{if(!cancelled)setMessage(String(e));});
    request<Frame>(path+"/scene/render-settings").then(r=>{if(!cancelled)setFrame(r);}).catch(e=>setMessage(`Image generation settings could not be loaded: ${String(e)}`));
    request<Job[]>(path+"/scene/renders").then(r=>{if(!cancelled)setJobs(r);}).catch(e=>{if(!cancelled)setMessage(String(e));});
    return ()=>{cancelled=true;};
  },[path,phone]);
  useEffect(()=>{
    if(dirty||!m.roomSymbols?.length)return;
    const controller=new AbortController();
    request<{planRevision:number;suggestions:Item[]}>(path+"/scene/fixture-suggestions?measured_only=true&plan_revision="+m.revision,
      {signal:controller.signal})
      .then(result=>{if(!controller.signal.aborted)setFixtureScan(current=>current?.planRevision===result.planRevision?current:result);})
      .catch(error=>{if(!controller.signal.aborted)setMessage(String(error));});
    return ()=>controller.abort();
  },[dirty,m.revision,m.roomSymbols?.length,path]);
  const pending=jobs.filter(active).map(j=>j.id).join(",");
  useEffect(()=>{
    if(!pending)return;
    let cancelled=false;
    let timer:ReturnType<typeof setTimeout>;
    async function update() {
      await Promise.all(pending.split(",").map(async id=>{
        try{
          const j=await request<Job>(path+"/scene/renders/"+id);
          if(!cancelled)setJobs(all=>all.map(x=>x.id===id?j:x));
        }catch(e){if(!cancelled)setMessage(String(e));}
      }));
      if(!cancelled)timer=setTimeout(update,sleepPollMs);
    }
    timer=setTimeout(update,sleepPollMs);
    return ()=>{cancelled=true;clearTimeout(timer);};
  },[path,pending]);

  function change(next:Scene, checkpoint=true) {
    if(checkpoint)setUndo(all=>[...all.slice(-29),scene]);
    setScene(next);
    setSight("");
  }
  async function scanFixtures(){
    setBusy(true);
    setMessage("Looking for furniture and bathroom fixtures…");
    try {
      const result=await request<{planRevision:number;suggestions:Item[];orientationNeedsReview?:boolean}>(path+"/scene/fixture-suggestions?plan_revision="+m.revision);
      setFixtureScan(result);setFixtureId("");setMode(null);setShowBlueprint(true);
      setMessage(result.orientationNeedsReview?"Review each detected fixture before inserting. Check its size and front/back rotation.":result.suggestions.length?"Review the outlined suggestions. Nothing has been inserted.":
        "No fixture symbols could be identified reliably. You can still place objects by hand.");
    }catch(e){setMessage(String(e));}finally{setBusy(false);}
  }
  function reviewFixture(o:Item, insert:boolean){
    if(insert){
      if(scene.objects.length>=100){setMessage("This scene already contains 100 objects.");return;}
      change({...scene,objects:[...scene.objects,o]});setItemId(o.id);
    }else{
      const dismissed=[...(scene.dismissedFixtureIds??[]),o.id];
      change({...scene,dismissedFixtureIds:dismissed.slice(-500)});
    }
    setMessage(insert?"Fixture inserted. You can adjust it before saving the scene.":"Suggestion dismissed.");
  }
  function updateView(patch:Partial<View>){
    if(view)change({...scene,views:scene.views.map(v=>v.id===view.id?{...v,...patch}:v)},false);
  }
  function updateItem(patch:Partial<Item>, checkpoint=true){
    if(!item)return;
    const next={...item,...patch};
    if(next.kind==="bed"&&((next.mattressWidth??0)>next.width||(next.mattressDepth??0)>next.depth*.96)){
      setMessage("The mattress must fit the frame with space for the headboard.");return;
    }
    change({...scene,objects:scene.objects.map(o=>o.id===item.id?next:o)},checkpoint);
    setMessage("");
  }
  const {clearance,validCamera}=walkSpace(m,scale,scene,view?.eyeHeight,pieces,nodeMap);
  function snap(p:Pt, o:Item){
    const a=o.rotation*Math.PI/180;
    let best=.22, result=p;
    for(const wall of m.walls){
      const u=nodeMap.get(wall.a)!,v=nodeMap.get(wall.b)!;
      const dx=(v.x-u.x)*scale,dz=(v.y-u.y)*scale, len=Math.hypot(dx,dz);
      if(!len)continue;
      const nx=-dz/len,nz=dx/len;
      const x=(p.x-u.x)*scale,z=(p.y-u.y)*scale, along=(x*dx+z*dz)/len;
      if(along<0||along>len)continue;
      const dist=x*nx+z*nz;
      const half=Math.abs(nx*Math.cos(a)+nz*Math.sin(a))*o.width/2+
        Math.abs(-nx*Math.sin(a)+nz*Math.cos(a))*o.depth/2+wall.thicknessPx*scale/2+.015;
      const delta=Math.sign(dist||1)*half-dist;
      if(Math.abs(delta)<best){best=Math.abs(delta);result={x:p.x+nx*delta/scale,y:p.y+nz*delta/scale};}
    }
    return result;
  }
  function mapPoint(svg:SVGSVGElement, clientX:number, clientY:number){
    const matrix=svg.getScreenCTM();
    if(!matrix)return null;
    const {x,y}=new DOMPoint(clientX,clientY).matrixTransform(matrix.inverse());
    return x<0||y<0||x>m.imageTransform.width||y>m.imageTransform.height?null:{x,y};
  }
  function placeObject(p:Pt,k:ObjectKind){
    if(scene.objects.length>=100){setMessage("This scene already contains 100 objects.");return;}
    const o=newItem(k,p);
    o.position=snap(p,o);
    if(o.position.x<0||o.position.y<0||o.position.x>m.imageTransform.width||o.position.y>m.imageTransform.height)return;
    change({...scene,objects:[...scene.objects,o]});setItemId(o.id);setMode(null);
  }
  function clickPlan(e:React.MouseEvent<SVGSVGElement>){
    const p=mapPoint(e.currentTarget,e.clientX,e.clientY);
    if(!p)return;
    const {x,y}=p;
    if(phone && !mode && cameraMode==="walk" && view){
      const start=walkPose.current?.id===view.id?walkPose.current:view;
      const dx=x-start.position.x, dy=y-start.position.y;
      const steps=Math.max(1,Math.ceil(Math.hypot(dx,dy)*scale/.05));
      for(let i=1;i<=steps;i++){
        if(!validCamera({x:start.position.x+dx*i/steps,y:start.position.y+dy*i/steps},true)){
          setMessage("The direct path is blocked. Tap a clear spot on this side or move through an open door.");return;
        }
      }
      updateView({...start,position:p});setMapOpen(false);setMessage("");return;
    }
    if(mode==="camera"){
      if(!validCamera(p)){setMessage("Place the camera inside a room or room zone, at least 30 cm from the wall and outside furniture.");return;}
      if(scene.views.length>=30){setMessage("Delete a saved view before adding another.");return;}
      const v:View={id:newUuid(),name:`View ${scene.views.length+1}`,position:p,yaw:0,pitch:-10,horizontalFov:90,eyeHeight:1.6};
      change({...scene,views:[...scene.views,v]});setViewId(v.id);setMode("aim");setCameraMode("orbit");setMessage("");
    }else if(mode==="move-view"&&view){
      if(!validCamera(p,true)){setMessage("Choose a clear position for the saved view.");return;}
      updateView({position:p});setMode(null);setCameraMode("preview");setMessage("");
    }else if(mode==="aim"&&view){
      if(Math.hypot(x-view.position.x,y-view.position.y)*scale<.1)return;
      updateView({yaw:Math.round(Math.atan2(y-view.position.y,x-view.position.x)*180/Math.PI)});
      setMode(null);setCameraMode(phone?"walk":"preview");setMessage("");
    }else if(mode==="sight"&&view){
      // Sample solid wall chunks along a horizontal eye-level line, respecting cut door openings.
      const a=view.position;
      const length=Math.hypot(x-a.x,y-a.y)*scale;
      const n=Math.min(3000,Math.ceil(length/.025));
      let blocked=false;
      for(let i=1;i<n;i++) if(clearance({x:a.x+(x-a.x)*i/n,y:a.y+(y-a.y)*i/n})<.016){blocked=true;break;}
      setSight(blocked?"A wall blocks this eye-level sightline.":"The eye-level sightline is clear of walls. Capture to check which fixtures are visible.");
      setMode(null);
    }else if(mode==="object"){
      placeObject(p,kind);
    }else if(mode==="move"&&item){
      const pos=snap(p,item);
      if(pos.x<0||pos.y<0||pos.x>m.imageTransform.width||pos.y>m.imageTransform.height)return;
      updateItem({position:pos});setMode(null);
    }else if(mode==="zone"){
      if(!zoneStart){setZoneStart(p);return;}
      if(Math.abs(x-zoneStart.x)*scale<.2||Math.abs(y-zoneStart.y)*scale<.2)return;
      const id=newUuid();
      onPlanEdit?.({...m,roomZones:[...(m.roomZones||[]),{id,label:null,polygon:[zoneStart,{x,y:zoneStart.y},p,{x:zoneStart.x,y}]}]});
      setZoneStart(null);setMode(view?null:"camera");setRoomId(id);
    }else{
      const o=[...scene.objects].reverse().find(o=>contains(p,footprint(o,scale)));
      setItemId(o?.id??"");setRoomId(rooms.find(r=>contains(p,r.polygon))?.id??"");
    }
  }
  function nudge(forward:number, side:number){
    if(!view)return;
    const a=view.yaw*Math.PI/180;
    const p={x:view.position.x+(forward*Math.cos(a)-side*Math.sin(a))/scale,
      y:view.position.y+(forward*Math.sin(a)+side*Math.cos(a))/scale};
    const steps=Math.ceil(Math.hypot(forward,side)/.025);
    const clear=Array.from({length:steps},(_,i)=>(i+1)/steps).every(t=>validCamera({
      x:view.position.x+(p.x-view.position.x)*t,
      y:view.position.y+(p.y-view.position.y)*t,
    },true));
    if(clear){updateView({position:p});setMessage("");}
    else setMessage("That move would put the camera too close to a wall or inside furniture.");
  }
  function editRoom(patch:{label?:string;roomType?:RoomType|null;ceilingHeightM?:number|null}){
    const apply=<T extends {id:string}>(r:T)=>r.id===roomId?{...r,...patch,needsSemanticReview:false}:r;
    onPlanEdit?.({...m,rooms:m.rooms.map(apply),roomZones:m.roomZones?.map(apply)});
  }
  const overlaps=!!item&&scene.objects.some(o=>o.id!==item.id&&intersects(footprint(item,scale),footprint(o,scale)));
  const visibleIn=(capture:Capture|null,id:number)=>!!capture&&(capture.coverage[id]||0)>=Math.max(24,frame.width*frame.height*.00015);
  const visible=(id:number)=>visibleIn(shot,id);
  function factsFor(capture:Capture|null, camera=view){return [
    ...rooms.filter((r,i)=>visibleIn(capture,i+2)||(camera&&contains(camera.position,r.polygon))).flatMap(r=>r.roomType?
      [`Space type: ${r.roomType}.`]:[]),
    ...scene.objects.flatMap((o,i)=>visibleIn(capture,1000+i)?
      [`Visible ${o.kind}: ${o.kind==="bed"?(o.mattressWidth??o.width).toFixed(2)+" × "+(o.mattressDepth??o.depth).toFixed(2)+" m mattress":o.width.toFixed(2)+" × "+o.depth.toFixed(2)+" m footprint"}.`]:[]),
  ];}
  const facts=factsFor(shot);
  const prompt=view?renderPrompt(m,scene,view,frame,[...new Set(facts)],false,shot):"";
  useEffect(()=>setAuthorized(false),[fingerprint,prompt]);
  async function persistScene(planRevision:number, config=scene){
    if(!saved)throw Error("The scene has not loaded.");
    if(saved.planRevision===planRevision&&JSON.stringify(saved.config)===JSON.stringify(config))return saved;
    if(saved.planRevision!=null&&saved.planRevision!==planRevision&&
      (m.revision!==planRevision||reviewPending||unresolved.length))
      throw Error("Review affected items before saving this scene.");
    const r=await request<Saved>(path+"/scene",json("PUT",{expectedRevision:saved.revision,planRevision,config}));
    setSaved(r);
    setScene(current=>current===scene?r.config:current);
    return r;
  }
  async function save(){
    setBusy(true);setMessage("");
    try{
      const plan=dirty&&savePlan?await savePlan():m;
      if(!plan)throw Error("The floor plan could not be saved.");
      await persistScene(plan.revision);setMessage("Scene saved.");
    }catch(e){setMessage(String(e));}finally{setBusy(false);}
  }
  function takeCapture(){
    const current=cameraMode==="walk"&&walkPose.current?.id===view?.id?walkPose.current:view;
    if(!current||!captureFn.current||!validCamera(current.position)){
      setMessage("Move the camera to a clear position before capturing.");return;
    }
    try{setCapture(captureFn.current(current,scale,frame,fingerprintFor(current)));updateView(current);setCameraMode("preview");setMessage("");}
    catch(e){setMessage(`Capture failed: ${String(e)}`);}
  }
  async function generate(){
    if(!view||!authorized||dirty||!frame.configured||busy)return;
    const current=cameraMode==="walk"&&walkPose.current?.id===view.id?walkPose.current:view;
    if(!validCamera(current.position)||!captureFn.current){setMessage("Place and aim a camera inside a room before generating.");return;}
    setBusy(true);setMessage("");
    try {
      const key=fingerprintFor(current);
      const currentShot=capture?.fingerprint===key?capture:captureFn.current(current,scale,frame,key);
      const config={...scene,views:scene.views.map(v=>v.id===current.id?current:v)};
      setCapture(currentShot);setCameraMode("preview");
      const submittedPrompt=renderPrompt(m,config,current,frame,[...new Set(factsFor(currentShot,current))],false,currentShot);
      const r=await persistScene(m.revision,config);
      const target=frame.provider==="local-comfy" && scene.objects.some(o=>o.id===editObject) ? editObject : "";
      if(target && !scene.objects.some((o,i)=>o.id===target && visibleIn(currentShot,1000+i)))throw new Error("Choose an object visible in this view.");
      const signature=JSON.stringify([target,currentShot.fingerprint,submittedPrompt,variant,r.revision]);
      if(submitRetry.current?.signature!==signature)submitRetry.current={signature,key:newUuid()};
      const job=await request<Job>(path+"/renders",json("POST",{requestKey:submitRetry.current.key,
        ...(target?{targetObjectId:target}:{}),sceneRevision:r.revision,viewId:view.id,name:variant.trim()||view.name,prompt:submittedPrompt,confirmed:true,
        depth:currentShot.depth.split(",")[1],mask:currentShot.mask.split(",")[1],preview:currentShot.preview.split(",")[1]}));
      submitRetry.current=null;setAuthorized(false);
      setJobs(all=>[job,...all.filter(j=>j.id!==job.id)]);setSelectedJob(job.id);
    }catch(e){setMessage(String(e));}
    finally{setBusy(false);}
  }
  async function exportInputs(){
    if(!shot||!view)return;
    let architectureReview:unknown={status:"draft",revision:m.revision};
    if(!dirty){
      try{architectureReview=await request(path+`/plan/review?revision=${m.revision}`);}
      catch(e){setMessage(`Review status could not be loaded: ${String(e)}`);return;}
    }
    const content={sceneSnapshot:scene,visibleRegions:shot.visibleRegions,architectureReview,view,planRevision:dirty?null:m.revision,planSnapshot:m,frame:{width:frame.width,height:frame.height},
      depthEncoding:"RGB24 view-space millimetres; zero is background",
      maskIds:{1:"Structure",...Object.fromEntries(rooms.map((r,i)=>[i+2,r.roomType??"room"])),
        ...Object.fromEntries(scene.objects.map((o,i)=>[1000+i,o.id])),
        ...Object.fromEntries(pieces.map((p,i)=>[2000+i,p.id]))},
      floorFinish:scene.floorMaterial??scene.floorFinish??"default",roomFloorMaterials:scene.roomFloorMaterials,prompt,depth:shot.depth,mask:shot.mask,preview:shot.preview};
    const url=URL.createObjectURL(new Blob([JSON.stringify(content)],{type:"application/json"}));
    const a=document.createElement("a");a.href=url;a.download="florp-render-inputs.json";a.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  const viewJobs=jobs.filter(j=>j.viewId===view?.id);
  const job=viewJobs.find(j=>j.id===selectedJob)??viewJobs[0];
  const asset=(name:string)=>`${API}${path}/scene/renders/${job?.id}/${name}`;
  const finishRecovery=!!unmatchedFinishes.length&&<section aria-label="Floor finishes to review">
    <h3>Floor finishes to review</h3>
    <p>{dirty?"Save the plan to confirm room matches.":"These finishes belong to rooms from an earlier layout. Reassign them or remove them, then save the scene."}</p>
    {!dirty&&unmatchedFinishes.map(([id,finish],index)=><div className="scene-actions" key={id}>
      <span>{index+1}. {finish.kind} · {finish.color}{finish.kind!=="concrete"?` · ${Math.round(finish.widthM*100)} × ${Math.round(finish.lengthM*100)} cm`:""}</span>
      <label>Move finish {index+1} to <select value="" onChange={e=>resolveFinish(id,e.target.value)}>
        <option value="" disabled>Choose a room</option>
        {rooms.map((room,i)=>!Object.hasOwn(scene.roomFloorMaterials??{},room.id)&&
          <option key={room.id} value={room.id}>{room.label||`Room ${i+1}`}</option>)}
      </select></label>
      <button onClick={()=>resolveFinish(id)}>Remove finish {index+1}</button>
    </div>)}
  </section>;
  return <div className="plan3d scene-studio" data-phone-map={phone?showMap:undefined} data-phone-step={phone?(design?"design":"walk"):undefined} data-testid="plan-3d" data-wall-lengths={meshSignature(pieces)} data-stair-count={m.stairs?.length??0}>
    <fieldset disabled={busy||!saved} className="scene-controls">
      {check?.mismatch&&<p role="alert">Known measurements differ by {(check.difference*100).toFixed(1)}%. Review the scale in 2D before relying on furniture fit.</p>}
      {!check&&<p>Check a second known distance in 2D before relying on furniture fit.</p>}
      {needsReview&&<section className="scene-change-review" aria-label="Review plan changes">
        <h3>Review plan changes</h3>
        {reviewPending?<p role="status">Comparing the saved scene with this plan…</p>:
          dirty?<p>Save the plan first to review its changes.</p>:
          <p>{unresolved.length ? `${unresolved.length} items need review before saving.` : "Affected items reviewed. Save the scene to update it."}</p>}
        {!reviewPending&&finishRecovery}
        {unresolved.filter(issue=>issue.kind!=="room"||!issue.missing).map(issue=><div className="scene-actions" key={issueKey(issue)}>
          <span><strong>{issue.label}</strong> · {issue.reason}</span>
          {(issue.kind==="object"||issue.kind==="view")&&<button onClick={()=>{
            if(issue.kind==="object"){setItemId(issue.id);setMode("move");}
            else {setViewId(issue.id);setMode("move-view");}
            setCameraMode("orbit");setMapOpen(true);setMessage("Choose a new position on the plan.");
          }}>Move {issue.kind==="view"?"view":"furniture"}</button>}
          {issue.kind==="room"&&<select aria-label="Reassign floor finish" value="" onChange={e=>resolveFinish(issue.id,e.target.value)}>
            <option value="" disabled>Reassign floor finish</option>
            {rooms.filter(room=>!Object.hasOwn(scene.roomFloorMaterials??{},room.id)).map((room,index)=>
              <option key={room.id} value={room.id}>{room.label||`Room ${index+1}`}</option>)}
          </select>}
          {!issue.missing&&<button onClick={()=>setReviewed(all=>({...all,[issueKey(issue)]:true}))}>Keep as is</button>}
          <button onClick={()=>removeReviewItem(issue)}>Remove</button>
        </div>)}
      </section>}
      {phone&&<div className="phone-steps">
        <button disabled={!view} aria-pressed={!design&&!showMap&&cameraMode==="walk"} onClick={()=>{setDesign(false);setMapOpen(false);setCameraMode("walk");}}>Walk</button>
        <button disabled={!view||!!mode} aria-pressed={showMap} onClick={()=>{setDesign(false);setCameraMode("walk");setMapOpen(!showMap);}}>Floor map</button>
        <button disabled={!!mode} aria-pressed={!showMap&&!design&&cameraMode==="orbit"} onClick={()=>{setMapOpen(false);setDesign(false);setCameraMode("orbit");}}>3D overview</button>
        <button disabled={!view||!ready||cameraMode==="orbit"||!!mode} aria-pressed={design} onClick={()=>{
          if(!view)return;
          const current=cameraMode==="walk"&&walkPose.current?.id===view.id?walkPose.current:view;
          if(!validCamera(current.position)){setMessage("Move into a clear space to capture this view.");return;}
          try{
            if(!captureFn.current)return;
            setCapture(captureFn.current(current,scale,frame,fingerprintFor(current)));
            updateView(current);setCameraMode("preview");setDesign(true);setMessage("");
          }catch(e){setMessage(String(e));}
        }}>Design this view</button>
        <button disabled={!edited} onClick={()=>void save()}>Save scene</button>
      </div>}
      {!rooms.length&&onPlanEdit&&<div className="scene-actions">
        <p>No closed rooms were found. Mark two opposite corners of a clear walking area on the original plan to add a floor and place a camera.</p>
        <button onClick={()=>{setShowBlueprint(true);setZoneStart(null);setMode("zone");setMapOpen(true);}}>Mark walkable floor</button>
      </div>}
      <div className="scene-actions">
        <button disabled={!rooms.length} onClick={()=>{setMode("camera");setCameraMode("orbit");}}>Place camera</button>
        <button disabled={!view} onClick={()=>setCameraMode(cameraMode==="preview"?"orbit":"preview")}>{cameraMode==="preview"?"Back to orbit":"Preview view"}</button>
        <button disabled={!view} aria-pressed={cameraMode==="walk"} onClick={()=>setCameraMode(cameraMode==="walk"?"orbit":"walk")}>Walkthrough</button>
        <button disabled={!edited&&!dirty} onClick={()=>void save()}>Save scene</button>
        <button disabled={!undo.length} onClick={()=>{setScene(undo[undo.length-1]);setUndo(undo.slice(0,-1));}}>Undo scene edit</button>
      </div>
      {!phone&&<ClosetDesigner open={designerOpen} plan={m} scene={scene} sceneRevision={saved?.revision??0} disabled={dirty||needsReview||JSON.stringify(scene)!==JSON.stringify(saved?.config)}/>}
      <label>Floor finish <select value={scene.floorMaterial?"custom":scene.floorFinish??"default"}
        onChange={e=>change({...scene,floorFinish:e.target.value as FloorFinish,floorMaterial:null})}>
        {scene.floorMaterial&&<option value="custom" disabled>Custom walkthrough finish</option>}
        {Object.entries(floorFinishes).map(([key,finish])=><option key={key} value={key}>{finish.name}</option>)}
      </select></label>
      <div className="scene-actions" role="group" aria-label="Wall finishes">
        <label>Wall <select value={finishWall?.id??""} onChange={e=>setFinishWallId(e.target.value)}>
          <option value="">Choose wall</option>
          {m.walls.map((wall,i)=><option key={wall.id} value={wall.id}>Wall {i+1}</option>)}
        </select></label>
        {finishWall&&<>
          <label>Side <select value={wallSide} onChange={e=>setWallSide(e.target.value as WallSide)}>
            {finishSideLines&&finishSideLines.map(line=><option key={line.side} value={line.side}>
              Side {line.side.toUpperCase()}{line.room?` · ${line.room}`:""}
            </option>)}
          </select></label>
          <label>Wall finish <select value={wallFinish?.kind??""} onChange={e=>{
            const kind=e.target.value as WallMaterial["kind"]|"";
            setWallFinish(kind?{kind,color:wallFinish?.color??"#d9c9ad"}:null);
          }}>
            <option value="">Original</option><option value="paint">Paint</option><option value="tile">Tile</option>
          </select></label>
          {wallFinish&&<label>Wall colour <input type="color" value={wallFinish.color}
            onChange={e=>setWallFinish({...wallFinish,color:e.target.value})}/></label>}
        </>}
      </div>
      {!needsReview&&finishRecovery}
      {message&&<p role="status">{message}</p>}
      <div className="scene-layout">
        <div>
          <svg aria-label="Camera and furniture placement plan" className="scene-map" viewBox={`0 0 ${m.imageTransform.width} ${m.imageTransform.height}`} onClick={clickPlan}
            onDragOver={e=>{if(e.dataTransfer.types.includes("application/x-florp-furniture"))e.preventDefault();}}
            onDrop={e=>{
              e.preventDefault();
              const k=e.dataTransfer.getData("application/x-florp-furniture") as ObjectKind;
              const p=mapPoint(e.currentTarget,e.clientX,e.clientY);
              if(objectKinds.includes(k)&&p)placeObject(p,k);
            }}>
            {showBlueprint&&<image href={API+path+"/preview"} width={m.imageTransform.width} height={m.imageTransform.height}/>}
            {rooms.map(r=><polygon key={r.id} points={points(r.polygon)} fill={r.id===roomId?"#b8ded5":"#e2eee7"} stroke="#b1c3bb" strokeWidth="1" opacity={showBlueprint ? .18 : 1}/>)}
            {m.walls.map(w=>{const a=nodeMap.get(w.a)!,b=nodeMap.get(w.b)!;
              return <line key={w.id} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={w.id===finishWallId?"#b66b51":"#233f4a"} strokeWidth={w.thicknessPx}/>;})}
            {finishSideLines&&finishSideLines.filter(line=>line.side===wallSide).map(({side,start,end})=>
              <line key={side} x1={start.x} y1={start.y} x2={end.x} y2={end.y} stroke="#b66b51"
                strokeWidth="3" vectorEffect="non-scaling-stroke" pointerEvents="none"/>)}
            {m.openings.filter(o=>o.status==="confirmed").map(o=>{
              const ends=openingEnds(m,o,nodeMap);if(!ends)return null;const [a,b]=ends;
              return <line key={o.id} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={o.kind==="window"?"#81c4d1":"#fff"} strokeWidth={nodeMap.size?m.walls.find(w=>w.id===o.hostWallId)?.thicknessPx??5:5}/>;})}
            {fixtureSuggestions.map((o,i)=><g key={o.id}>
              <polygon data-testid="fixture-outline" points={points(footprint(o,scale))}
                fill={o.id===fixture?.id?"#b777443d":"#fff1"} stroke="#a65020" strokeWidth={o.id===fixture?.id?2.5:1.5}
                vectorEffect="non-scaling-stroke" strokeDasharray="5 3"
                onClick={e=>{if(!mode){e.stopPropagation();setFixtureId(o.id);}}}/>
              <text x={o.position.x} y={o.position.y} pointerEvents="none" textAnchor="middle" fill="#702f13"
                stroke="white" strokeWidth={m.imageTransform.width/420} paintOrder="stroke"
                fontSize={Math.max(9,m.imageTransform.width/82)}>{i+1}</text>
            </g>)}
            {scene.objects.map(o=><g key={o.id}><polygon points={points(footprint(o,scale))} fill={o.id===itemId?"#d3a86b":"#e5d5b9"} stroke="#946e3e"/>
              <text x={o.position.x} y={o.position.y} textAnchor="middle" fontSize={Math.max(7,m.imageTransform.width/92)}>{o.kind}</text></g>)}
            {view&&(()=>{const p=view.position, length=.95/scale;
              const ends=[view.yaw-view.horizontalFov/2,view.yaw+view.horizontalFov/2].map(d=>({x:p.x+length*Math.cos(d*Math.PI/180),y:p.y+length*Math.sin(d*Math.PI/180)}));
              return <g><polygon points={points([p,...ends])} fill="#008a8044" stroke="#008a80"/><circle cx={p.x} cy={p.y} r={.075/scale} fill="#007c70"/></g>;})()}
          </svg>
          <p aria-live="polite">{mode==="camera"?"Click the camera position inside a room.":mode==="aim"?"Click the direction to face.":
            mode==="sight"?"Click a target to check the eye-level sightline.":mode==="zone"?"Click two opposite corners of the room zone.":
            mode?"Click where the object should go.":phone?"Tap a reachable spot on the map to move.":"Click a room or object to edit it."}</p>
        </div>
        <div className="scene-viewport">
          <div className="scene-frame" role="group" aria-label="Walkthrough" tabIndex={cameraMode==="preview"&&view?0:-1}
          onKeyDown={e=>{
            if(cameraMode!=="preview"||!view||busy||e.altKey||e.ctrlKey||e.metaKey)return;
            switch(e.key.toLowerCase()){
              case "w": case "arrowup": nudge(.1,0); break;
              case "s": case "arrowdown": nudge(-.1,0); break;
              case "a": nudge(0,-.1); break;
              case "d": nudge(0,.1); break;
              case "arrowleft": updateView({yaw:wrap(view.yaw-5)}); break;
              case "arrowright": updateView({yaw:wrap(view.yaw+5)}); break;
              default: return;
            }
            e.preventDefault();
            e.stopPropagation();
          }} data-mode={view?cameraMode:"orbit"} style={{aspectRatio:`${frame.width}/${frame.height}`}}>
            <Canvas dpr={[1,2]} camera={{position:[w/2+w*.6,Math.max(7,h*.9),h/2+Math.max(8,h)],fov:55}}>
              <color attach="background" args={["#e9eff2"]}/>
              <SceneMesh floorStyle={scene} designPreset={scene.designPreset} wallFinishes={scene.wallFinishes} windowFinishes={scene.windowFinishes} m={m} objects={scene.objects} detectedObjects={detectedObjects} closedDoorIds={scene.closedDoorIds}/>
              <CaptureBridge bind={bind}/>
              {view&&cameraMode==="walk"?<WalkCamera view={view} scale={scale} frame={frame} canMove={p=>validCamera(p,true)} pose={walkPose}/>:
                view&&cameraMode==="preview"?<EyeCamera view={view} scale={scale} frame={frame}/>:
                <><Grid infiniteGrid cellSize={1} sectionSize={5}/><OrbitNavigation makeDefault target={cameraTarget}/></>}
            </Canvas>
          </div>
          {view&&cameraMode==="walk"&&<p>Drag left or right to turn and up or down to walk. Scroll or pinch to zoom.</p>}
          {(!view||cameraMode==="orbit")&&<p>Drag to orbit. Scroll or pinch to zoom. Right-drag or drag with two fingers to pan.{!view&&" Place and aim a camera to start a walkthrough."}</p>}
        </div>
      </div>
      <div className="scene-actions">
        {view&&<>
          {cameraMode==="preview"&&<p>Focus the walkthrough to walk with WASD and turn with the arrow keys, or use the movement buttons below.</p>}
          <label>Saved view <select value={view.id} onChange={e=>{setViewId(e.target.value);setCameraMode("preview");setSight("");}}>{scene.views.map(v=><option key={v.id} value={v.id}>{v.name}</option>)}</select></label>
          <label>Name <input maxLength={80} value={view.name} onChange={e=>updateView({name:e.target.value})}/></label>
          <button onClick={()=>setMode("aim")}>Aim</button>
          <button onClick={()=>setMode("sight")}>Check sightline</button>
          <button onClick={()=>{change({...scene,views:scene.views.filter(v=>v.id!==view.id)});setCameraMode("orbit");}}>Remove view</button>
          <label>Eye height <input type="number" min=".8" max="2.2" step=".05" value={view.eyeHeight} onChange={e=>{
            const n=e.target.valueAsNumber;if(n>=.8&&n<=2.2)updateView({eyeHeight:n});}}/> m</label>
          <label>Pitch <input type="range" min="-45" max="30" step="1" value={view.pitch} onChange={e=>updateView({pitch:Number(e.target.value)})}/> {view.pitch}°</label>
          <label>View width <select value={view.horizontalFov} onChange={e=>updateView({horizontalFov:Number(e.target.value)})}>
            <option value="70">Natural · 70°</option><option value="90">Wide · 90°</option><option value="100">Extra wide · 100°</option></select></label>
          <button onClick={()=>nudge(.1,0)}>Forward</button><button onClick={()=>nudge(-.1,0)}>Back</button>
          <button onClick={()=>nudge(0,-.1)}>Left</button><button onClick={()=>nudge(0,.1)}>Right</button>
          <button onClick={()=>updateView({yaw:wrap(view.yaw-5)})}>Turn left</button>
          <button onClick={()=>updateView({yaw:wrap(view.yaw+5)})}>Turn right</button>
        </>}
      </div>
      {sight&&<p role="status">{sight}</p>}
      {view&&!validCamera(view.position)&&<p>Camera needs 30 cm of wall clearance and a clear floor position.</p>}
      <div className="scene-actions">
        <label>Furniture <select aria-label="Furniture" value={kind} onChange={e=>setKind(e.target.value as ObjectKind)}>
          {objectKinds.map(k=><option key={k} value={k}>{objectName(k)}</option>)}</select></label>
        <button draggable onDragStart={e=>e.dataTransfer.setData("application/x-florp-furniture",kind)}
          onClick={()=>setMode("object")} title="Drag onto the plan or click to place">Place object</button>
        <button disabled={(m.roomZones?.length??0)>=50} onClick={()=>{setMode("zone");setZoneStart(null);}}>Mark room zone</button>
        {mode&&<button onClick={()=>{setMode(null);setZoneStart(null);}}>Cancel placement</button>}
      </div>
      <section className="scene-fixtures" aria-label="Fixture suggestions">
        {!!detections.length&&<label><input type="checkbox" checked={showDetections} onChange={e=>setShowDetections(e.target.checked)}/> Detected furniture preview</label>}
        <div className="scene-actions">
          <button disabled={dirty} title={dirty?"Save the plan before scanning.":undefined} onClick={()=>void scanFixtures()}>Find fixtures on plan</button>
          <label><input type="checkbox" checked={showBlueprint} onChange={e=>setShowBlueprint(e.target.checked)}/> Show original plan</label>
          {!!scene.dismissedFixtureIds?.length&&<button onClick={()=>change({...scene,dismissedFixtureIds:[]})}>Restore dismissed suggestions</button>}
        </div>
        {fixture&&<div className="scene-actions">
          <label>Suggestion <select aria-label="Fixture suggestion" value={fixture.id} onChange={e=>{setFixtureId(e.target.value);setMode(null);}}>
            {fixtureSuggestions.map((o,i)=><option key={o.id} value={o.id}>{i+1}. {fixtureName(o)}</option>)}
          </select></label>
          <span>{fixture.width.toFixed(2)} × {fixture.depth.toFixed(2)} m estimated footprint</span>
          <button onClick={()=>reviewFixture(fixture,true)}>Insert {fixtureName(fixture).toLowerCase()}</button>
          <button onClick={()=>reviewFixture(fixture,false)}>Dismiss suggestion</button>
        </div>}
      </section>
      {m.openings.some(o=>o.kind==="door"&&o.status==="confirmed")&&<details>
        <summary>Door positions</summary>
        <div className="scene-actions">{m.openings.filter(o=>o.kind==="door"&&o.status==="confirmed").map((o,i)=><label key={o.id}>
          <input type="checkbox" checked={scene.closedDoorIds?.includes(o.id)??false} onChange={e=>{
            const ids=scene.closedDoorIds??[];
            change({...scene,closedDoorIds:e.target.checked?[...ids,o.id]:ids.filter(id=>id!==o.id)});
          }}/> Door {i+1} closed</label>)}</div>
      </details>}
      <section aria-label="Objects in this scene" className="scene-object-list">
        <h3>Objects in this scene ({scene.objects.length})</h3>
        <p>Choose furniture above, then click the plan to add it. Select any object here to move or resize it. Undo restores a removed object.</p>
        {!scene.objects.length&&<p>No objects yet. Add furniture or find fixtures on the original plan.</p>}
        {scene.objects.map((o,i)=><div className="scene-actions" key={o.id}>
          <button aria-pressed={itemId===o.id} onClick={()=>{setItemId(o.id);setRoomId("");setMode(null);}}>{i+1}. {objectName(o.kind)}</button>
          <span>{o.width.toFixed(2)} × {o.depth.toFixed(2)} m</span>
          <button aria-label={`Remove ${o.kind} ${i+1}`} onClick={()=>{change({...scene,objects:scene.objects.filter(x=>x.id!==o.id)});if(itemId===o.id)setItemId("");}}>Remove</button>
        </div>)}
      </section>
      {item&&<div className="scene-actions" aria-label="Selected furniture">
        <strong>{objectName(item.kind)}</strong>
        {item.kind==="tv"&&<label>Screen diagonal (inches)
          <input key={item.width} type="number" {...tvSizeRange} step="1" defaultValue={tvInches(item.width,item.height)}
            onBlur={e=>{
              const inches=e.target.valueAsNumber;
              if(e.target.validity.valid&&Number.isFinite(inches))updateItem(tvDimensions(inches));
              else e.target.value=String(tvInches(item.width,item.height));
            }}/>
        </label>}
        {(item.kind==="tv"?["depth"]:["width","depth","height",...(item.kind==="bed"?["mattressWidth","mattressDepth"]:[])]).map(raw=>{
          const k=raw as "width"|"depth"|"height"|"mattressWidth"|"mattressDepth";
          const min=(item.kind==="rug"||item.kind==="cooktop")&&k==="height"?.006:.06;
          return <label key={k}>{({width:"Frame width",depth:"Frame depth",height:"Height",mattressWidth:"Mattress width",mattressDepth:"Mattress length"})[k]}
            <input key={item.id+"-"+k+"-"+item[k]} aria-label={k} type="number" step={min===.006?.001:.01} min={min} max={k==="height"?5:8} defaultValue={item[k]??""}
              onBlur={e=>{const n=e.target.valueAsNumber;if(n>=min&&n<=(k==="height"?5:8))updateItem({[k]:n});else e.target.value=String(item[k]??"");}}/> m</label>;
        })}
        <button onClick={()=>setMode("move")}>Move</button>
        <button onClick={()=>updateItem({rotation:wrap(item.rotation+15)})}>Rotate 15°</button>
        <button onClick={()=>change({...scene,objects:scene.objects.filter(o=>o.id!==item.id)})}>Remove object</button>
        {overlaps&&<span role="status">Furniture footprints overlap.</span>}
      </div>}
      {room&&<div className="scene-actions" aria-label="Selected room">
        <label>Room name <input maxLength={80} value={room.label??""} onChange={e=>editRoom({label:e.target.value})}/></label>
        <label>Room type <select value={room.roomType??""} onChange={e=>editRoom({roomType:e.target.value as RoomType||null})}>
          <option value="">Unspecified</option>{ROOM_TYPES.map(t=><option key={t}>{t}</option>)}</select></label>
        {"areaPx2" in room&&typeof room.areaPx2==="number"&&<span>{(room.areaPx2*scale*scale).toFixed(2)} m²</span>}
        {room.roomType!=="balcony"&&<label>Ceiling height (assumed) <input key={room.id} type="number" min="1.8" max="8" step=".05" defaultValue={room.ceilingHeightM??2.8}
          onBlur={e=>{const n=e.target.valueAsNumber;if(n>=1.8&&n<=8&&n!==(room.ceilingHeightM??2.8))editRoom({ceilingHeightM:n});}}/> m</label>}
        {room.needsSemanticReview&&<strong>Review room labels after a split or merge.</strong>}
        {m.roomZones?.some(r=>r.id===room.id)&&<button onClick={()=>onPlanEdit?.({...m,roomZones:m.roomZones?.filter(r=>r.id!==room.id)})}>Remove room zone</button>}
      </div>}
      <section className="scene-render" aria-label="Create a design image">
        <h3>Create a design image</h3>
        {phone&&shot&&<img style={{width:"100%"}} src={shot.preview} alt="Captured walkthrough view"/>}
        {!view&&<p>Place a camera on the plan and click where it should look. Then enter your design below.</p>}
        <label className="scene-design-prompt">Design prompt <textarea rows={4} maxLength={1200} value={scene.style} onChange={e=>change({...scene,style:e.target.value},false)} placeholder="Create a warm brown bedroom, with black bathroom tiles and a gold toilet."/></label>
        <p>Describe materials, colours and lighting for this camera view. Only spaces and objects visible in the capture can be designed.</p>
        <button disabled={!view||!ready||!validCamera(view.position)} onClick={takeCapture}>Capture view</button>
        {shot&&<>
          {Object.entries(shot.coverage).some(([id,n])=>Number(id)>=2000&&n>frame.width*frame.height*.65)&&<p>A wall fills most of the frame. Try backing up, turning, or widening the view.</p>}
          <p>{facts.length?facts.join(" "):"No labelled spaces or furniture are visible in this view."}</p>
          {scene.objects.some((o,i)=>o.kind==="toilet"&&!visible(1000+i))&&<p>A placed toilet is not visible in this view.</p>}
          <details><summary>Prompt sent to the renderer</summary><pre>{prompt}</pre></details>
          <button onClick={()=>downloadPrompt(prompt)}>Download view prompt</button>
          <a href={shot.preview} download="florp-view.png">Download captured image</a>
          <button onClick={exportInputs}>Export render inputs</button>
          <label>Variant name <input maxLength={80} value={variant} onChange={e=>setVariant(e.target.value)}/></label>
        </>}
          {frame.provider==="local-comfy"&&<label>Render area <select value={editObject} onChange={e=>{setEditObject(e.target.value);setAuthorized(false);}}>
            <option value="">Whole view</option>
            {scene.objects.map((o,i)=><option key={o.id} value={o.id} disabled={!!shot&&!visible(1000+i)}>{fixtureName(o)} {i+1}</option>)}
          </select></label>}
          {frame.configured?<label><input type="checkbox" checked={authorized} onChange={e=>setAuthorized(e.target.checked)}/>
            {frame.provider==="local-comfy"?"Generate on this computer using local ComfyUI — no cloud API charge":<>Send this view’s depth image and prompt to {frame.provider==="comfy"?"Comfy Cloud":"fal"} for a billable render</>}</label>:<p>{frame.provider==="comfy"?"Set COMFY_API_KEY":"Set COMFY_API_KEY for Comfy Cloud, or IMAGE_API_KEY for fal"} on the API server to enable generation. Capture and export work without a key.</p>}
          {dirty&&<p>Save the floor plan before generating.</p>}
          <button disabled={busy||!view||!ready||!authorized||!frame.configured||dirty||!validCamera(view.position)} onClick={()=>void generate()}>Generate preview</button>
      </section>
      {!!viewJobs.length&&<section className="scene-render">
        <label>Render variants <select value={job?.id} onChange={e=>{setSelectedJob(e.target.value);setRecoveryMessage("");}}>
          {viewJobs.map(j=><option value={j.id} key={j.id}>{j.name} · {j.status}</option>)}</select></label>
        {job&&<p role="status">{job.status} {job.error??""} · {job.model} · Scene {job.sceneRevision}</p>}
        {job&&["failed","submitting"].includes(job.status)&&<button disabled={recoveringRender} onClick={()=>void (async()=>{
          setRecoveringRender(true);
          setRecoveryMessage("");
          try{
            const recovered=await request<Job>(path+"/scene/renders/"+encodeURIComponent(job.id)+"/recover",{method:"POST"});
            setJobs(current=>current.map(item=>item.id===recovered.id?recovered:item));
          }catch(error){setRecoveryMessage(String(error));}
          finally{setRecoveringRender(false);}
        })()}>Check for existing render</button>}
        {recoveryMessage&&<p role="status">{recoveryMessage}</p>}
        {job?.status==="failed"&&job.model.startsWith("local-comfy:")&&<p>See the local ComfyUI setup guide in the Florp README for port and model checks. Keep ComfyUI running until generation finishes.</p>}
        {job?.status==="failed"&&!job.model.startsWith("local-comfy:")&&<p>After fixing the account or configuration issue, select consent and generate a new preview. If the connection was interrupted, check the provider dashboard first to avoid paying twice. Your saved camera and capture remain available.</p>}
        {job?.status==="failed"&&job.model.startsWith("comfy:")&&<a href="https://cloud.comfy.org" target="_blank" rel="noreferrer">Open Comfy account and credits</a>}
        {job?.status==="complete"&&<RenderComparison key={job.id} asset={asset}/>}
      </section>}
    </fieldset>
  </div>;
}
