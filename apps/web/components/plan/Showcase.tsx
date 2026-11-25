"use client";
import {OrbitNavigation} from "./OrbitNavigation";
import { roomTags } from "../../lib/plan/roomTags";
import {useCallback,useEffect,useMemo,useRef,useState} from "react";
import {Canvas,useThree} from "@react-three/fiber";
import {Html} from "@react-three/drei";
import {DoubleSide,Shape,Vector2,Vector3} from "three";
import Link from "next/link";
import {Maximize2,LayoutGrid,Box,MapPin,Pause,Play,SkipBack,SkipForward,Image as ImageIcon,FileDown,ImageDown,Bookmark,MapPinPlus,X,PencilRuler,Layers,Armchair} from "lucide-react";
import {MAX_HORIZONTAL_FOV_DEG} from "../../lib/plan/camera";
import {downloadPrompt,renderPrompt} from "../../lib/plan/renderPrompt";
import {SceneMesh} from "./SceneMesh";
import {metersPerPixel,scaleCheck} from "../../lib/plan/derive";
import {WalkCamera} from "./WalkCamera";
import {findRoomView,findWalkStart,roomsOf,walkSpace} from "../../lib/plan/walkSpace";
import {FloorPicker} from "./FloorPicker";
import {newUuid} from "../../lib/uuid";
import FinishSheet from "./FinishSheet";
import FurnishSheet from "./FurnishSheet";
import {scrollTourRail} from "./scrollTourRail";
import {FurniturePlacement} from "./FurniturePlacement";
import {fitsFloor,furnitureFit} from "../../lib/plan/furnitureFit";
import {objectName,tvDimensions,yardKinds} from "../../lib/plan/furnitureCatalog";
import { floorMaterialFor, materialDefaults, unmatchedFloorFinishes } from "../../lib/plan/floorMaterials";
import { contains, footprint, newItem } from "../../lib/plan/scene";
import type {PlanModel,Pt} from "../../lib/plan/model";
import type {FloorMaterial,Frame,Item,Scene,View} from "../../lib/plan/scene";

type FloorStyles = Pick<Scene,"floorMaterial"|"roomFloorMaterials">;
const wideView = {pitch:-5, horizontalFov:MAX_HORIZONTAL_FOV_DEG, eyeHeight:1.6};

function SampleFurniture({interior}:{interior:boolean}){
  function block(x:number,y:number,z:number,w:number,h:number,d:number,color:string){
    return <mesh castShadow receiveShadow position={[x,y,z]}><boxGeometry args={[w,h,d]}/><meshStandardMaterial color={color}/></mesh>;
  }
  return <>
    {interior&&<>
      {block(3,-.13,-1,50,.14,50,"#a8b391")}
      {[-4,-1,2,6,9,14].map((x,i)=><group key={x} position={[x,0,-4-i%2]}>
        {block(0,1,0,.2,2,.2,"#87785b")}
        <mesh position={[0,2.6,0]} scale={[1.5,1.6+i%2*.4,1.4]}><icosahedronGeometry args={[1,2]}/><meshStandardMaterial color={i%2?"#8eaa7d":"#78946a"}/></mesh>
      </group>)}
    </>}
    {block(2.6,1.7,.09,1.3,.94,.06,"#846447")}
    {block(2.6,1.7,.135,1.19,.82,.04,"#dec59d")}
    {block(2.78,1.62,.165,.45,.56,.025,"#aa694d")}
    {block(2.35,1.78,.166,.3,.28,.025,"#62746a")}
    {block(2.55,.015,2.35,3.8,.028,2.85,"#d3bca0")}
    {block(2.4,.29,1.46,2.8,.54,1,"#68755d")}
    {[1.57,2.4,3.23].map(x=><group key={x}>{block(x,.59,1.53,.79,.18,.72,"#8a9b7b")}</group>)}
    {block(2.4,.7,1.06,2.8,.55,.24,"#78856c")}
    {[1.11,3.69].map(x=><group key={x}>{block(x,.48,1.45,.24,.67,1,"#78856c")}</group>)}
    {block(2.5,.36,2.85,1.5,.12,.68,"#b48358")}{block(2.5,.18,2.85,.86,.32,.43,"#896345")}
    {block(3.96,.77,5.07,1.75,.12,1,"#b8875f")}
    {[3.3,4.64].flatMap(x=>[4.72,5.42].map(z=><group key={x+"-"+z}>{block(x,.38,z,.09,.74,.09,"#796046")}</group>))}
    {[4.27,5.88].map(z=><group key={z}>{block(3.95,.26,z,.55,.48,.5,"#a08a71")}{block(3.95,.61,z+(z<5?-.2:.2),.55,.46,.09,"#bda48a")}</group>)}
    <mesh castShadow receiveShadow position={[.75,.25,1]}><cylinderGeometry args={[.28,.2,.5,20]}/><meshStandardMaterial color="#bb845e"/></mesh>
    <mesh castShadow receiveShadow position={[.75,.82,1]} scale={[.46,.76,.42]}><icosahedronGeometry args={[1,1]}/><meshStandardMaterial color="#708763" flatShading/></mesh>
  </>;
}

function OverviewCamera({plan}:{plan:PlanModel}){
  const {camera,size}=useThree();
  const scale=metersPerPixel(plan)!;
  const {eye,target}=useMemo(()=>{
    const aspect=size.width/Math.max(1,size.height);
    const span=Math.max(1,plan.imageTransform.width*scale,plan.imageTransform.height*scale);
    const target=new Vector3(plan.imageTransform.width*scale/2,.65,plan.imageTransform.height*scale/2);
    const distance=span*1.90/Math.min(1,aspect);
    return {target,eye:target.clone().addScaledVector(new Vector3(.82,1.1,1.22).normalize(),distance)};
  },[plan,scale,size.width,size.height]);
  const perspective=camera as import("three").PerspectiveCamera;
  return <><primitive object={perspective} position={eye} fov={45} onUpdate={()=>perspective.updateProjectionMatrix()}/>
    <OrbitNavigation target={target} zoomToCursor rotateSpeed={.65} minDistance={.65} minPolarAngle={.08} maxPolarAngle={Math.PI*.47}/></>;
}

type WalkFrame = {viewId:string;width:number;height:number;image:()=>string};

function clearSampleFloor(p:Pt,scale:number){
  return ![[.99,.96,3.81,1.96],[1.75,2.51,3.25,3.19],[3.08,4.57,4.84,5.57],
    [3.67,4,4.23,4.52],[3.67,5.63,4.23,6.13],[.41,.66,1.09,1.34]]
    .some(([a,b,c,d])=>p.x*scale>=a&&p.x*scale<=c&&p.y*scale>=b&&p.y*scale<=d);
}

function ShowcaseWalk({plan,scene,view,sample,pose,onFrame,keyboard}:{
  keyboard:boolean;plan:PlanModel;scene:Scene;view:View;sample:boolean;pose:{current:View|null};onFrame:(frame:WalkFrame|null)=>void;
}){
  const {size,gl,get}=useThree();
  useEffect(()=>{
    onFrame({
      viewId:view.id,width:gl.domElement.width,height:gl.domElement.height,
      image:()=>{
        const {scene,camera}=get();
        gl.render(scene,camera);
        return gl.domElement.toDataURL("image/png");
      },
    });
    return ()=>onFrame(null);
  },[get,gl,size,onFrame,view.id]);
  const scale=metersPerPixel(plan)!;
  const space=useMemo(()=>walkSpace(plan,scale,scene,view.eyeHeight),[plan,scene,scale,view.eyeHeight]);
  const frame=useMemo<Frame>(()=>({width:size.width,height:Math.max(1,size.height),configured:false,model:"",provider:""}),[size.width,size.height]);
  return <WalkCamera view={view} scale={scale} frame={frame} pose={pose} keyboard={keyboard} tapToWalk={keyboard}
    canMove={p=>space.validCamera(p,true)&&(!sample||clearSampleFloor(p,scale))}/>;

}

function FitOverlay({points,scale,color}:{points:Pt[];scale:number;color:string}){
  const shape=new Shape(points.map(p=>new Vector2(p.x*scale,-p.y*scale)));
  return <mesh rotation={[-Math.PI/2,0,0]} position={[0,.025,0]} raycast={()=>{}}>
    <shapeGeometry args={[shape]}/><meshBasicMaterial color={color} side={DoubleSide} transparent opacity={.38} depthWrite={false}/>
  </mesh>;
}

export default function Showcase({plan,scene,title,edit,sample=false,approximate=false,renders={},saveView,saveFinishes,saveFurniture}:{plan:PlanModel;scene:Scene;title:string;edit?:string;sample?:boolean;approximate?:boolean;renders?:Record<string,string>;saveView?:(view:View,initial?:View)=>Promise<View>;saveFinishes?:(finishes:FloorStyles)=>Promise<void>;saveFurniture?:(objects:Item[])=>Promise<void>}){
  const [localViews,setLocalViews]=useState<View[]>([]);
  const [freeView,setFreeView]=useState<View|null>(null);
  const [adding,setAdding]=useState(false);
  const [saving,setSaving]=useState(false);
  const savingRef=useRef(false);
  const [selectedId,setSelectedId]=useState<string|null>(()=>
    typeof location!=="undefined"&&location.hash==="#overview"?"overview":null);
  const stage=useRef<HTMLDivElement>(null!);
  const tags = useMemo(() => roomTags(plan), [plan]);
  const rooms=useMemo(()=>roomsOf(plan),[plan]);
  const hasFloor=rooms.length>0;
  const check=scaleCheck(plan);
  const [finishesOpen,setFinishesOpen]=useState(false);
  const [pickingRoom,setPickingRoom]=useState(false);
  const [finishScope,setFinishScope]=useState("");
  const [finishDraft,setFinishDraft]=useState<FloorStyles|null>(null);
  const [sessionFinishes,setSessionFinishes]=useState<FloorStyles|null>(null);
  const [finishNotice,setFinishNotice]=useState("");
  const [furnishing,setFurnishing]=useState(false);
  const [furnitureDraft,setFurnitureDraft]=useState<Item[]|null>(null);
  const [previewFurniture,setPreviewFurniture]=useState<Item[]|null>(null);
  const [furnitureId,setFurnitureId]=useState("");
  const [placement,setPlacement]=useState<Item|null>(null);
  const [dragPreview,setDragPreview]=useState<Item|null>(null);
  const catalogDrag=useRef<Item|null>(null);
  const [furnitureNotice,setFurnitureNotice]=useState("");
  const tourScene=useMemo(()=>previewFurniture?{...scene,objects:previewFurniture}:scene,[previewFurniture,scene]);
  const objects=furnitureDraft??tourScene.objects;
  const selectedFurniture=objects.find(item=>item.id===furnitureId);
  const placingNew=placement&&!objects.some(item=>item.id===placement.id);
  const displayedObjects=dragPreview?[...objects.filter(item=>item.id!==dragPreview.id),dragPreview]:objects;
  const walkScene=useMemo(()=>furnitureDraft?{...tourScene,objects:furnitureDraft}:tourScene,[tourScene,furnitureDraft]);
  const styledScene={...scene,...sessionFinishes,...finishDraft,objects};
  const needsFinishReview=unmatchedFloorFinishes(styledScene,rooms).length>0;
  const material=floorMaterialFor(styledScene,finishScope)??materialDefaults.wood;
  function changeFinish(next:FloorMaterial){
    setFinishDraft(finishScope ?
      {floorMaterial:styledScene.floorMaterial,roomFloorMaterials:{...styledScene.roomFloorMaterials,[finishScope]:next}} :
      {floorMaterial:next,roomFloorMaterials:styledScene.roomFloorMaterials});
    setFinishNotice("");
  }
  async function applyFinishes(){
    if(!finishDraft||savingRef.current)return;
    savingRef.current=true;
    setSaving(true);
    try{
      if(saveFinishes)await saveFinishes(finishDraft);
      else setSessionFinishes(finishDraft);
      setFinishDraft(null);
      setFinishNotice(saveFinishes?"Finishes saved":"Finishes applied for this session");
    }catch(error){setFinishNotice(String(error));}
    finally{savingRef.current=false;setSaving(false);}
  }
  const scale=metersPerPixel(plan)!;
  const fit=useMemo(()=>furnishing&&selectedFurniture?furnitureFit(plan,selectedFurniture,objects,scale):null,
    [furnishing,selectedFurniture,objects,plan,scale]);
  const fitWarnings=fit?[
    ...(fit.overlaps.length?["Overlaps another object."]:[]),
    ...(fit.swing.length?["Blocks a door swing."]:[]),
    ...(fit.clearance.length?["Obstructs the 60 cm doorway approach."]:[]),
    ...(fit.narrow.length?["Nearby gap is narrower than 60 cm."]:[]),
  ]:[];
  const persistFurniture=check?.mismatch?undefined:saveFurniture;
  const previewReason=persistFurniture?undefined:
    approximate?"Preview only. Furniture fit uses an approximate scale.":
    check?.mismatch?"Preview only. Your scale measurements differ.":
    "Preview only. The scene needs review against the current floor plan.";
  function openFurnish(){
    setPlaying(false);setRendered(false);setAdding(false);setNotice("");
    if(view&&pose.current?.id===view.id)setFreeView(pose.current);
    setFurnishing(true);
  }
  function closeFurnish(){
    setFurnishing(false);setFurnitureDraft(null);setFurnitureId("");setPlacement(null);setFurnitureNotice("");
    setDragPreview(null);catalogDrag.current=null;
  }
  function updateFurniture(item:Item){
    if(!fitsFloor(plan,item,scale)){
      setFurnitureNotice(yardKinds.has(item.kind)
        ?"Choose a position where the whole object fits in a yard or balcony."
        :"Choose a position where the whole object fits inside one room.");
      return false;
    }
    setFurnitureDraft(objects.some(other=>other.id===item.id)
      ?objects.map(other=>other.id===item.id?item:other):[...objects,item]);
    setFurnitureId(item.id);
    setFurnitureNotice("");
    return true;
  }
  function placeFurniture(item:Item,point:Pt|null){
    if(savingRef.current)return;
    if(!point){setFurnitureNotice("Choose a visible spot on the floor.");return;}
    if(objects.length>=100&&!objects.some(other=>other.id===item.id))return;
    if(updateFurniture({...item,position:point}))setPlacement(null);
  };
  async function applyFurniture(){
    if(!furnitureDraft||placement||savingRef.current)return;
    savingRef.current=true;setSaving(true);
    try{
      if(persistFurniture){
        await persistFurniture(furnitureDraft);
        setPreviewFurniture(null);
      }else{
        setPreviewFurniture(furnitureDraft);
      }
      setFurnitureDraft(null);
      setFurnitureNotice(persistFurniture?"Furniture saved":"Preview kept for this session");
    }catch(error){setFurnitureNotice(String(error));}
    finally{savingRef.current=false;setSaving(false);}
  }
  const space=useMemo(()=>walkSpace(plan,scale,tourScene),[plan,scale,tourScene]);
  const canFrame=useCallback((point:Pt,walking:boolean)=>
    space.validCamera(point,walking)&&(!sample||clearSampleFloor(point,scale)),[space,sample,scale]);
  const cornerNear=useCallback((point:Pt)=>{
    const room=[...rooms].reverse().find(room=>contains(point,room.polygon));
    return room?findRoomView(room.polygon,scale,canFrame,point):undefined;
  },[rooms,scale,canFrame]);
  const views=useMemo(()=>{
    if(scene.views.length||localViews.length)return [...scene.views,...localViews];
    const start=findWalkStart(plan,scale,canFrame);
    return start?[{id:"walk-start",name:"Walkthrough",...wideView,...start}]:[];
  },[plan,scene.views,localViews,scale,canFrame]);
  const [playing,setPlaying]=useState(false),[notice,setNotice]=useState("");
  const [rendered,setRendered]=useState(false),[toolsOpen,setToolsOpen]=useState(false);
  const stop=selectedId==="overview"?-1:selectedId===null?(views.length?0:-1):views.findIndex(v=>v.id===selectedId);
  const openingView=useMemo(()=>{
    const first=views[0];
    if(!first||first.id==="walk-start")return first;
    const corner=cornerNear(first.position);
    return {...first,...wideView,...corner,id:"tour-start-corner"};
  },[views,cornerNear]);
  const view=freeView??(selectedId===null?openingView:views[stop]);
  const pinGroups=useMemo(()=>{
    const groups:{position:Pt;indices:number[]}[]=[];
    views.forEach((v,i)=>{
      const group=groups.find(g=>Math.hypot(g.position.x-v.position.x,g.position.y-v.position.y)*scale<.35);
      if(group)group.indices.push(i);
      else groups.push({position:v.position,indices:[i]});
    });
    return groups;
  },[views,scale]);
  const latestViews=useRef(views);
  useEffect(()=>{latestViews.current=views;},[views]);
  const pose=useRef<View|null>(null);
  const [viewport,setViewport]=useState<WalkFrame|null>(null);
  useEffect(()=>{
    const read=()=>{
      const id=new URLSearchParams(location.hash.slice(1)).get("view");
      setFreeView(null);
      setSelectedId(location.hash==="#overview"?"overview":latestViews.current.some(v=>v.id===id)?id:null);
    };
    read();window.addEventListener("hashchange",read);return ()=>window.removeEventListener("hashchange",read);
  },[]);
  useEffect(()=>{
    if(!playing)return;
    const timer=setTimeout(()=>{
      if(stop>=views.length-1)setPlaying(false);
      else {setFreeView(null);setSelectedId(views[stop+1].id);}
    },6500);
    return ()=>clearTimeout(timer);
  },[playing,stop,views]);
  function select(index:number){
    setPlaying(false);setRendered(false);setFreeView(null);setAdding(false);
    setSelectedId(views[index]?.id??"overview");setNotice("");
  }
  const addView=useCallback(async (location:View)=>{
    if(savingRef.current)return;
    savingRef.current=true;setSaving(true);
    const entry={...location,id:newUuid(),name:"View "+(views.length+1)};
    try{
      const initial = !scene.views.length && !localViews.length && views[0]?.id==="walk-start"
        ? {...views[0],id:newUuid(),name:"View 1"} : undefined;
      const saved=saveView?await saveView(entry,initial):entry;
      if(!saveView)setLocalViews(current=>[...(initial?[initial]:[]),...current,saved]);
      setFreeView(null);setSelectedId(saved.id);setAdding(false);
      setNotice(saveView?"View saved":"View added for this session");
    }catch(e){setNotice(String(e));}
    finally{savingRef.current=false;setSaving(false);}
  },[scene.views.length,localViews.length,views,saveView]);
  const land=useCallback((point:Pt|null,yaw:number)=>{
    if(savingRef.current)return;
    if(pickingRoom){
      const room=point&&[...rooms].reverse().find(r=>contains(point,r.polygon));
      if(room){
        setFinishScope(room.id);
        setPickingRoom(false);
        setFinishesOpen(true);
        setNotice("");
      }
      return;
    }
    const corner=adding&&point?cornerNear(point):undefined;
    if(!point||(!corner&&!canFrame(point,true))){
      setNotice("Choose an open spot on the floor.");
      return;
    }
    setPlaying(false);setRendered(false);setNotice("");setSelectedId("overview");
    const entry:View={id:"free-walk",name:"Walkthrough",...wideView,...(corner??{position:point,yaw})};
    if(adding)void addView(entry);
    else setFreeView(entry);
  },[adding,addView,canFrame,cornerNear,pickingRoom,rooms]);
  function openCornerView(){
    if(!view)return;
    const point=pose.current?.id===view.id?pose.current.position:view.position;
    const corner=cornerNear(point);
    setPlaying(false);
    if(!corner){setNotice("No clear corner in this room.");return;}
    setNotice("");
    setFreeView({id:"free-walk",name:"Walkthrough",...wideView,...corner});
  }
  return <main className="showcase-player" data-furnishing={furnishing} aria-label="3D showcase">
    <h1 className="show-current-view">{view?.name??"Dollhouse view"}</h1>
    <div ref={stage} className="show-stage"><Canvas shadows frameloop="demand" dpr={[1,1.6]} camera={{near:.005,far:2000}} fallback={<p>Enable WebGL to view this tour.</p>}>
      <color attach="background" args={[view?"#d4e3e9":"#d8d9cb"]}/>
      <SceneMesh m={plan} objects={displayedObjects} closedDoorIds={scene.closedDoorIds} floorStyle={styledScene}
        wallFinishes={scene.wallFinishes} presentation cutaway={!view}/>
      {sample&&<SampleFurniture interior={!!view}/>}
      {view?<ShowcaseWalk key={view.id} plan={plan} scene={walkScene} view={view} sample={sample} pose={pose} onFrame={setViewport} keyboard={!rendered}/>:
        <><OverviewCamera plan={plan}/>{!furnishing&&<FloorPicker scale={scale} onPick={land}/>}</>}
      {furnishing&&<FurniturePlacement scale={scale} walkthrough={!!view} disabled={saving} pending={placement}
        objects={objects} catalogDrag={catalogDrag}
        onPreview={item=>setDragPreview(item&&fitsFloor(plan,item,scale)?item:null)}
        onPlace={placeFurniture} onSelect={id=>{setFurnitureId(id);setFurnitureNotice("");}}/>}
      {!dragPreview&&fit&&selectedFurniture&&<>
        <FitOverlay points={footprint({...selectedFurniture,width:selectedFurniture.width+.08,depth:selectedFurniture.depth+.08},scale)}
          scale={scale} color={fitWarnings.length?"#af5035":"#477b63"}/>
        {fit.swing.concat(fit.clearance,fit.narrow).map((points,i)=><FitOverlay key={i} points={points} scale={scale} color="#af5035"/>)}
      </>}
      {!view&&tags.map(tag=><Html key={tag.key} portal={stage} center wrapperClass="show-room-label" style={{pointerEvents:"none",display:furnishing?"none":undefined}}
        position={[tag.position.x*scale,.18,tag.position.y*scale]} zIndexRange={[1,0]}>
        <span className="show-room-tag">{tag.text}</span>
      </Html>)}
      {!view&&pinGroups.map(({position,indices})=><Html key={views[indices[0]].id} portal={stage} center
        style={{display:pickingRoom||furnishing?"none":undefined}} position={[position.x*scale,2,position.y*scale]} zIndexRange={[2,1]}>
        <div className="show-pin-group">{indices.map(i=><button key={views[i].id} className="show-pin" aria-label={"Visit "+views[i].name} onClick={()=>select(i)}>{i+1}</button>)}</div>
      </Html>)}
    </Canvas>
    </div>
    {view&&rendered&&renders[view.id]&&<div className="show-render"><img src={renders[view.id]} alt={"Saved design render for "+view.name}/></div>}
    {view&&<button type="button" className="show-overview" data-tour-tools onClick={()=>select(-1)}><Box size={18}/>Overview</button>}
    {furnishing?<FurnishSheet objects={objects} selected={selectedFurniture} previewReason={previewReason}
      pending={placement?placingNew?`Tap or drag on ${yardKinds.has(placement.kind)?"a yard or balcony":"the floor"} to place the ${objectName(placement.kind).toLowerCase()}.`:"Tap or drag on the ground to move this object.":""}
      dirty={!!furnitureDraft} saving={saving} message={furnitureNotice} issues={fitWarnings}
      edit={edit&&"/phone/edit/"+encodeURIComponent(plan.id)}
      onAdd={kind=>{setPlacement(newItem(kind,{x:0,y:0}));setFurnitureId("");setFurnitureNotice("");}}
      onDragStart={kind=>{catalogDrag.current=newItem(kind,{x:0,y:0});setFurnitureNotice("");}}
      onDragEnd={()=>{catalogDrag.current=null;setDragPreview(null);}}
      onSelect={id=>{setFurnitureId(id);setPlacement(null);setFurnitureNotice("");}}
      onMove={()=>{if(selectedFurniture){setPlacement(selectedFurniture);setFurnitureNotice("");}}}
      onRotate={degrees=>{if(selectedFurniture)updateFurniture({...selectedFurniture,rotation:(selectedFurniture.rotation+degrees+360)%360});}}
      onResize={(key,value)=>{
        if(!selectedFurniture)return;
        const item={...selectedFurniture,[key]:value};
        if(key==="width"&&item.mattressWidth!=null)item.mattressWidth=Math.min(value,item.mattressWidth);
        if(key==="depth"&&item.mattressDepth!=null)item.mattressDepth=Math.min(value*.96,item.mattressDepth);
        updateFurniture(item);
      }}
      onScreenSize={inches=>{if(selectedFurniture?.kind==="tv")updateFurniture({...selectedFurniture,...tvDimensions(inches)});}}
      onRemove={()=>{setFurnitureDraft(objects.filter(item=>item.id!==furnitureId));setFurnitureId("");setFurnitureNotice("");}}
      onCancelPick={()=>{setPlacement(null);setFurnitureNotice("");}} onClose={closeFurnish} onSave={()=>void applyFurniture()}/>:
    finishesOpen?<FinishSheet rooms={rooms} scope={finishScope} selectScope={setFinishScope} material={material}
      change={changeFinish} saving={saving} dirty={!!finishDraft} notice={finishNotice} canPersist={!!saveFinishes}
      onReset={finishScope&&styledScene.roomFloorMaterials?.[finishScope]?()=>{
        const overrides={...styledScene.roomFloorMaterials};
        delete overrides[finishScope];
        setFinishDraft({floorMaterial:styledScene.floorMaterial,roomFloorMaterials:overrides});
        setFinishNotice("");
      }:undefined}
      onPick={()=>{select(-1);setPickingRoom(true);setFinishesOpen(false);}}
      onClose={()=>{setFinishesOpen(false);setFinishDraft(null);setFinishNotice("");}}
      onSave={()=>void applyFinishes()}
      reviewHref={needsFinishReview&&edit?edit+"?setup=finishes":undefined}/>:
    <section className="show-panel" aria-label="Tour controls" data-tour-tools onKeyDown={event=>{
      if(event.key==="Escape"&&toolsOpen&&!pickingRoom){
        setToolsOpen(false);
        event.currentTarget.querySelector<HTMLButtonElement>(".show-menu-button")?.focus();
      }
    }}>
      {(toolsOpen||adding||pickingRoom)&&<div className="show-heading">
        <small>{approximate?"Approximate scale · ":""}{title}</small>
        <p>{pickingRoom?"Tap a room’s floor to choose it.":adding?"Tap a room to add a wide corner view.":rendered?"Saved design render":view?"Tap to walk. Drag two fingers to move, twist to turn, and pinch to zoom.":"Drag to orbit. Use two fingers to pan, twist, or zoom."}</p>
      </div>}
      <div className="show-dock">
        <button type="button" className="show-menu-button" aria-label={toolsOpen?"Close tour tools":"Open tour tools"}
          aria-expanded={toolsOpen||pickingRoom} aria-controls="show-tour-actions"
          onClick={()=>{
            if(pickingRoom){setPickingRoom(false);setFinishesOpen(true);}
            else setToolsOpen(!toolsOpen);
          }}>
          {toolsOpen||pickingRoom?<X/>:<LayoutGrid/>}
        </button>
        <div id="show-tour-actions" className="show-list" role="group" aria-label="Tour actions" hidden={!toolsOpen&&!pickingRoom} onWheel={scrollTourRail}>
          {pickingRoom?<button onClick={()=>{setPickingRoom(false);setFinishesOpen(true);}}><X/>Cancel room selection</button>:<>
          {hasFloor&&<button disabled={saving} onClick={()=>{
            setPlaying(false);setRendered(false);setAdding(false);setFinishesOpen(true);
          }}><Layers/>Finishes</button>}
          {(hasFloor||!!plan.gardens?.length)&&!sample&&<button disabled={saving} onClick={openFurnish}><Armchair/>Furnish</button>}
          {views.map((v,i)=><button key={v.id} aria-pressed={view===v} onClick={()=>select(i)}><MapPin/>{v.name}</button>)}
          {view&&renders[view.id]&&<button aria-pressed={rendered} onClick={()=>{setPlaying(false);setRendered(!rendered);}}>
            {rendered?<Box/>:<ImageIcon/>}{rendered?"Return to 3D":"Show saved design"}
          </button>}
          {views.length>1&&<>
            <button onClick={()=>{setRendered(false);if(!playing&&stop===views.length-1)select(-1);setPlaying(!playing);}}>
              {playing?<Pause/>:<Play/>}{playing?"Pause":"Play tour"}
            </button>
            <button disabled={stop<0} onClick={()=>select(stop-1)}><SkipBack/>Previous stop</button>
            <button disabled={stop>=views.length-1} onClick={()=>select(stop+1)}><SkipForward/>Next stop</button>
          </>}
          {!view&&hasFloor&&<button aria-pressed={adding} disabled={saving} onClick={()=>{setPlaying(false);setNotice("");setAdding(!adding);}}>
            {adding?<X/>:<MapPinPlus/>}{adding?"Cancel adding view":"Add view"}
          </button>}
          {view&&!rendered&&<button disabled={saving} onClick={openCornerView}><Maximize2/>Corner view</button>}
          {view&&!rendered&&<button disabled={saving} onClick={()=>{
            setPlaying(false);
            if(pose.current?.id===view.id)void addView(pose.current);
          }}><Bookmark/>Save this view</button>}
          {edit&&<Link href={"/phone/edit/"+encodeURIComponent(plan.id)}><PencilRuler/>Edit floor</Link>}
          {view&&!rendered&&viewport?.viewId===view.id&&<>
            <button onClick={()=>{
              setPlaying(false);
              if(pose.current?.id===view.id)downloadPrompt(renderPrompt(plan,styledScene,pose.current,viewport,[],approximate));
            }}><FileDown/>Download view prompt</button>
            <button onClick={()=>{
              setPlaying(false);
              const link=document.createElement("a");
              link.href=viewport.image();link.download="florp-view.png";link.click();
            }}><ImageDown/>Download view image</button>
          </>}
          {!hasFloor&&edit&&<Link href={edit+"?setup=floor"}><PencilRuler/>Mark a walkable floor in the editor</Link>}
          </>}
        </div>
      </div>
      {(toolsOpen||adding||pickingRoom)&&(!hasFloor||notice||needsFinishReview)&&<p role="status">{notice||(!hasFloor?"No walkable floor was found.":"Some saved floor finishes need review. Open Finishes.")}</p>}
      {toolsOpen&&check?.mismatch&&<p role="alert" className="show-scale-warning">Scale measurements differ by {(check.difference*100).toFixed(1)}%. Check scale in Edit floor.</p>}
    </section>}
  </main>;
}
