"use client";
import {OrbitNavigation} from "./OrbitNavigation";
import {detectedPreviewItems, visibleDetections} from "../../lib/plan/detectedFurniture";
import { roomTags } from "../../lib/plan/roomTags";
import {useCallback,useEffect,useMemo,useRef,useState} from "react";
import {Canvas,useThree} from "@react-three/fiber";
import {Html} from "@react-three/drei";
import {DoubleSide,Shape,Vector2,Vector3} from "three";
import Link from "next/link";
import DesktopBrand from "../DesktopBrand";
import {request} from "../../lib/api";
import {Maximize2,LayoutGrid,Box,Footprints,MapPin,Pause,Play,SkipBack,SkipForward,Image as ImageIcon,FileDown,ImageDown,Bookmark,MapPinPlus,X,PencilRuler,Layers,Armchair} from "lucide-react";
import {MAX_HORIZONTAL_FOV_DEG} from "../../lib/plan/camera";
import {downloadPrompt,renderPrompt} from "../../lib/plan/renderPrompt";
import {homePresets, presetFloor, type HomePreset} from "../../lib/plan/homePresets";
import {WalkthroughObjects, ObjectHighlight, SelectionBox, WallHighlight, WalkTargetAnchor, targetKey, type WalkTarget} from "./WalkthroughObjects";
import {WalkthroughEditMenu,type WalkEditor} from "./WalkthroughEditMenu";
import {SceneMesh} from "./SceneMesh";
import {metersPerPixel,openingEnds,scaleCheck} from "../../lib/plan/derive";
import {doorLeaves} from "../../lib/plan/doorLeaves";
import {wallPieces} from "../../lib/plan/mesh";
import {connectedWallFace} from "../../lib/plan/wallFaces";
import {WalkCamera} from "./WalkCamera";
import {findRoomFloorPoint,findRoomView,findWalkStart,roomsOf,walkSpace} from "../../lib/plan/walkSpace";
import {FloorPicker} from "./FloorPicker";
import {ShowcaseViewPins} from "./ShowcaseViewPins";
import {newUuid} from "../../lib/uuid";
import FinishSheet from "./FinishSheet";
import FurnishSheet from "./FurnishSheet";
import {scrollTourRail} from "./scrollTourRail";
import {FurniturePlacement} from "./FurniturePlacement";
import {fitsFloor,furnitureFit} from "../../lib/plan/furnitureFit";
import {objectName, furnitureRooms, tvDimensions,yardKinds, type ObjectKind} from "../../lib/plan/furnitureCatalog";
import { floorMaterialFor, materialDefaults, unmatchedFloorFinishes } from "../../lib/plan/floorMaterials";
import { contains, footprint, newItem } from "../../lib/plan/scene";
import type {PlanModel,Pt} from "../../lib/plan/model";
import type {FloorMaterial,Frame,Item,Scene,View,WalkthroughEdit} from "../../lib/plan/scene";
import {styledWindowFrame} from "../../lib/plan/windowStyle";
import {setWallSurface} from "../../lib/plan/wallMaterials";

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
    canMove={(to,from)=>space.canWalk(from,to)&&(!sample||clearSampleFloor(to,scale))}/>;

}

function FitOverlay({points,scale,color}:{points:Pt[];scale:number;color:string}){
  const shape=new Shape(points.map(p=>new Vector2(p.x*scale,-p.y*scale)));
  return <mesh rotation={[-Math.PI/2,0,0]} position={[0,.025,0]} raycast={()=>{}}>
    <shapeGeometry args={[shape]}/><meshBasicMaterial color={color} side={DoubleSide} transparent opacity={.38} depthWrite={false}/>
  </mesh>;
}

export default function Showcase({plan,scene,title,edit,desktop=false,stale=false,sample=false,approximate=false,renders={},saveView,moveView,saveFinishes,saveFurniture,savePreset,saveWalkEdit}:{plan:PlanModel;scene:Scene;title:string;edit?:string;desktop?:boolean;stale?:boolean;sample?:boolean;approximate?:boolean;renders?:Record<string,string>;saveView?:(view:View,initial?:View)=>Promise<View>;moveView?:(id:string,position:Pt)=>Promise<void>;saveFinishes?:(finishes:FloorStyles)=>Promise<void>;saveFurniture?:(objects:Item[])=>Promise<void>;savePreset?:(preset:HomePreset|null)=>Promise<void>;saveWalkEdit?:(change:WalkthroughEdit)=>Promise<void>}){
  const [localViews,setLocalViews]=useState<View[]>([]);
  const [localPinPositions,setLocalPinPositions]=useState<Record<string,Pt>>({});
  const [pinNotice,setPinNotice]=useState("");
  const [freeView,setFreeView]=useState<View|null>(null);
  const [adding,setAdding]=useState(false);
  const [saving,setSaving]=useState(false);
  const savingRef=useRef(false);
  const [selectedId,setSelectedId]=useState<string|null>(()=>
    typeof location!=="undefined"&&location.hash==="#overview"?"overview":null);
  const studioPoseKey = desktop ? `florp-studio-pose:${plan.id}:${plan.revision}` : null;
  const lastWalkPose = useRef<View | null>(null);
  const stage=useRef<HTMLDivElement>(null!);
  const tags = useMemo(() => roomTags(plan, true), [plan]);
  const scale=metersPerPixel(plan)!;
  const rooms=useMemo(()=>roomsOf(plan),[plan]);
  const hasFloor=rooms.length>0;
  const check=scaleCheck(plan);
  const [finishesOpen,setFinishesOpen]=useState(false);
  const [pickingRoom,setPickingRoom]=useState(false);
  const [finishScope,setFinishScope]=useState("");
  const [finishDraft,setFinishDraft]=useState<FloorStyles|null>(null);
  const [sessionFinishes,setSessionFinishes]=useState<FloorStyles|null>(null);
  const [stylesOpen,setStylesOpen]=useState(false);
  const [presetDraft,setPresetDraft]=useState<HomePreset|null|undefined>(undefined);
  const [sessionPreset,setSessionPreset]=useState<HomePreset|null|undefined>(undefined);
  const designPreset=presetDraft!==undefined?presetDraft:sessionPreset!==undefined?sessionPreset:scene.designPreset;
  const [target,setTarget]=useState<WalkTarget|null>(null);
  const [pointed,setPointed]=useState<WalkTarget|null>(null);
  const [quickNotice,setQuickNotice]=useState("");
  const menu=useRef<HTMLDivElement>(null);
  const [sessionEdits,setSessionEdits]=useState<WalkthroughEdit>({});
  function chooseTarget(next:WalkTarget|null){
    setPointed(null);
    if(savingRef.current||targetKey(next)===targetKey(target))return;
    setQuickNotice("");
    setTarget(next);
  }
  const [finishNotice,setFinishNotice]=useState("");
  const [furnishing,setFurnishing]=useState(false);
  const [hiddenDetections,setHiddenDetections]=useState<string[]>([]);
  const [showDetections,setShowDetections]=useState(true);
  const [detected,setDetected]=useState<{planRevision:number;suggestions:Item[]}|null>(null);
  useEffect(()=>{
    if(approximate||sample||!plan.roomSymbols?.length)return;
    const controller=new AbortController();
    request<{planRevision:number;suggestions:Item[]}>(`/blueprints/${encodeURIComponent(plan.id)}/scene/fixture-suggestions?measured_only=true&plan_revision=${plan.revision}`,
      {signal:controller.signal})
      .then(result=>{if(!controller.signal.aborted)setDetected(result);})
      .catch(error=>{if(!controller.signal.aborted)setFurnitureNotice(String(error));});
    return ()=>controller.abort();
  },[approximate,sample,plan.id,plan.revision,plan.roomSymbols?.length]);
  const [furnitureDraft,setFurnitureDraft]=useState<Item[]|null>(null);
  const [previewFurniture,setPreviewFurniture]=useState<Item[]|null>(null);
  const [furnitureId,setFurnitureId]=useState("");
  const [placement,setPlacement]=useState<Item|null>(null);
  const [dragPreview,setDragPreview]=useState<Item|null>(null);
  const catalogDrag=useRef<Item|null>(null);
  const [furnitureNotice,setFurnitureNotice]=useState("");
  const tourScene=useMemo(()=>({...scene,...sessionEdits,objects:previewFurniture??scene.objects}),[previewFurniture,scene,sessionEdits]);
  const objects=furnitureDraft??tourScene.objects;
  const selectedFurniture=objects.find(item=>item.id===furnitureId);
  const localDetections=useMemo(()=>detectedPreviewItems(plan,scale),[plan,scale]);
  const suggestions=useMemo(()=>visibleDetections(
    detected?.planRevision===plan.revision?detected.suggestions:localDetections,
    objects,scale,[...(scene.dismissedFixtureIds??[]),...hiddenDetections]
  ),[detected,plan.revision,localDetections,objects,scale,scene.dismissedFixtureIds,hiddenDetections]);
  const displayedObjects=showDetections?[...objects,...suggestions]:objects;
  function inDrawing(point:Pt){
    const {width,height}=plan.imageTransform;
    return point.x>=0&&point.x<=width&&point.y>=0&&point.y<=height;
  }
  function canPlaceFurniture(item:Item){
    return inDrawing(item.position)&&(displayedObjects.some(object=>object.id===item.id)||
      (!rooms.length&&!yardKinds.has(item.kind))||fitsFloor(plan,item,scale));
  }
  const hovered=target?.kind==="object"?displayedObjects.find(item=>item.id===target.id):undefined;
  const hoveredOpening=target?.kind==="opening"?plan.openings.find(item=>item.id===target.id):undefined;
  const alternatives=hovered ? [...new Set(furnitureRooms.flatMap(room=>room.groups
    .filter(group=>(group.items as readonly ObjectKind[]).includes(hovered.kind)).flatMap(group=>[...group.items])))]
    .filter(kind=>kind!==hovered.kind) : [];
  const editableObjects=dragPreview?[...objects.filter(item=>item.id!==dragPreview.id),dragPreview]:objects;
  const walkScene=useMemo(()=>furnitureDraft?{...tourScene,objects:furnitureDraft}:tourScene,[tourScene,furnitureDraft]);
  const styledScene={...tourScene,...sessionFinishes,...finishDraft,objects,designPreset};
  const needsFinishReview=unmatchedFloorFinishes(styledScene,rooms).length>0;
  const material=floorMaterialFor(styledScene,finishScope)??presetFloor(designPreset,rooms.find(room=>room.id===finishScope)?.roomType)??materialDefaults.wood;
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
  const fit=useMemo(()=>furnishing&&selectedFurniture?furnitureFit(plan,selectedFurniture,objects,scale):null,
    [furnishing,selectedFurniture,objects,plan,scale]);
  const fitWarnings=fit?[
    ...(selectedFurniture&&!fitsFloor(plan,selectedFurniture,scale)?["Footprint extends beyond the detected floor."]:[]),
    ...(fit.overlaps.length?["Overlaps another object."]:[]),
    ...(fit.swing.length?["Blocks a door swing."]:[]),
    ...(fit.clearance.length?["Obstructs the 60 cm doorway approach."]:[]),
    ...(fit.narrow.length?["Nearby gap is narrower than 60 cm."]:[]),
  ]:[];
  const persistFurniture=check?.mismatch?undefined:saveFurniture;
  const previewReason=persistFurniture?undefined:
    approximate?"Approximate scale":check?.mismatch?"Scale mismatch":"Scene needs review";
  const selectFurniture=useCallback((id:string)=>{
    setFurnitureId(id);setPlacement(null);setFurnitureNotice("");setDragPreview(null);
  },[]);
  useEffect(()=>{
    if(!furnishing)return;
    const cancel=(event:KeyboardEvent)=>{
      if(event.key!=="Escape")return;
      selectFurniture("");
    };
    window.addEventListener("keydown",cancel);
    return ()=>window.removeEventListener("keydown",cancel);
  },[furnishing,selectFurniture]);
  async function applyPreset(){
    if(presetDraft===undefined||savingRef.current)return;
    savingRef.current=true;setSaving(true);
    try{
      if(savePreset)await savePreset(presetDraft);
      else setSessionPreset(presetDraft);
      setNotice(savePreset ? "Style saved" : "Style applied for this session");
      setPresetDraft(undefined);setStylesOpen(false);
    }catch(error){setNotice(String(error));}
    finally{savingRef.current=false;setSaving(false);}
  }
  function openFurnish(){
    setPlaying(false);setRendered(false);setAdding(false);setNotice("");
    chooseTarget(null);
    setStylesOpen(false);setPresetDraft(undefined);setFinishesOpen(false);
    if(view&&pose.current?.id===view.id)setFreeView(pose.current);
    setFurnishing(true);
  }
  async function applyQuickEdit(change:WalkthroughEdit){
    if(savingRef.current)return;
    if(view&&pose.current?.id===view.id)setFreeView(pose.current);
    savingRef.current=true;setSaving(true);setQuickNotice("");
    try{
      if(change.objects){
        if(persistFurniture){await persistFurniture(change.objects);setPreviewFurniture(null);}
        else setPreviewFurniture(change.objects);
      }else if(saveWalkEdit)await saveWalkEdit(change);
      else setSessionEdits(current=>({...current,...change}));
      setTarget(null);
    }catch(error){setQuickNotice(String(error));}
    finally{savingRef.current=false;setSaving(false);}
  }
  function applyQuickFurniture(item:Item){
    const exists=objects.some(object=>object.id===item.id);
    if(!exists&&objects.length>=100){setQuickNotice("This tour already has 100 objects.");return;}
    if(!inDrawing(item.position)){setQuickNotice("Place the object within the drawing.");return;}
    void applyQuickEdit({objects:exists?objects.map(object=>object.id===item.id?item:object):[...objects,item]});
  }
  function removeQuickFurniture(item:Item){
    if(objects.some(object=>object.id===item.id))void applyQuickEdit({objects:objects.filter(object=>object.id!==item.id)});
    else {setHiddenDetections(current=>[...current,item.id]);chooseTarget(null);}
  }
  function closeFurnish(){
    setFurnishing(false);setFurnitureDraft(null);setFurnitureId("");setPlacement(null);setFurnitureNotice("");
    setDragPreview(null);catalogDrag.current=null;
  }
  function updateFurniture(item:Item){
    if(!canPlaceFurniture(item)){
      setFurnitureNotice(item.kind==="car"?"Choose a spot in a garage or yard where the car fits.":yardKinds.has(item.kind)
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
    if(!point){selectFurniture("");return;}
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
  const pieces=useMemo(()=>wallPieces(plan),[plan]);
  const space=useMemo(()=>walkSpace(plan,scale,tourScene,undefined,pieces),[plan,scale,tourScene,pieces]);
  const canFrame=useCallback((point:Pt,walking:boolean)=>
    space.validCamera(point,walking)&&(!sample||clearSampleFloor(point,scale)),[space,sample,scale]);
  const cornerNear=useCallback((point:Pt)=>{
    const room=[...rooms].reverse().find(room=>contains(point,room.polygon));
    return room?findRoomView(room.polygon,scale,canFrame,point):undefined;
  },[rooms,scale,canFrame]);
  const views=useMemo(()=>{
    if(scene.views.length||localViews.length)return [...scene.views,...localViews].map(view=>
      Object.hasOwn(localPinPositions,view.id)?{...view,position:localPinPositions[view.id]}:view);
    const {width,height}=plan.imageTransform;
    const floor=findWalkStart(plan,scale,canFrame);
    const fallback=floor?undefined:findRoomFloorPoint([{x:0,y:0},{x:width,y:0},{x:width,y:height},{x:0,y:height}],space.clearFloor);
    const start=floor??(fallback&&{position:fallback,yaw:0});
    return start?[{id:"walk-start",name:"Walkthrough",...wideView,...start}]:[];
  },[plan,scene.views,localViews,localPinPositions,scale,canFrame,space]);
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
  async function repositionView(view:View,position:Pt){
    if(savingRef.current)return;
    setPinNotice("");
    savingRef.current=true;setSaving(true);
    try{
      if(view.id==="walk-start"){
        const first={...view,id:newUuid(),name:"View 1",position};
        if(saveView)await saveView(first);
        else setLocalViews([first]);
      }else if(moveView)await moveView(view.id,position);
      else setLocalPinPositions(current=>({...current,[view.id]:position}));
    }
    catch(error){setPinNotice(String(error));}
    finally{savingRef.current=false;setSaving(false);}
  }
  const latestViews=useRef(views);
  useEffect(()=>{latestViews.current=views;},[views]);
  const pose=useRef<View|null>(null);
  const [viewport,setViewport]=useState<WalkFrame|null>(null);
  useEffect(()=>{
    const read=()=>{
      const id=new URLSearchParams(location.hash.slice(1)).get("view");
      let previous: View | null = null;
      if (studioPoseKey) {
        try { previous = JSON.parse(sessionStorage.getItem(studioPoseKey) ?? "null"); } catch {}
      }
      lastWalkPose.current = previous;
      setFreeView(!location.hash ? previous : null);
      setSelectedId(location.hash==="#overview"?"overview":latestViews.current.some(v=>v.id===id)?id:null);
    };
    read();window.addEventListener("hashchange",read);return ()=>window.removeEventListener("hashchange",read);
  },[studioPoseKey]);
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
    chooseTarget(null);
    setPinNotice("");
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
    const room=adding&&point?[...rooms].reverse().find(r=>contains(point,r.polygon)):undefined;
    const corner=room&&findRoomView(room.polygon,scale,canFrame,point??undefined);
    const position=corner?.position??(point&&canFrame(point,true)?point:
      room&&findRoomFloorPoint(room.polygon,canFrame));
    if(!position){
      setNotice(room?"No clear camera position in this room.":"Tap a room’s floor.");
      return;
    }
    setPlaying(false);setRendered(false);setNotice("");setSelectedId("overview");
    const entry:View={id:"free-walk",name:"Walkthrough",...wideView,position,yaw:corner?.yaw??yaw};
    if(adding)void addView(entry);
    else setFreeView(entry);
  },[adding,addView,canFrame,pickingRoom,rooms,scale]);
  function openCornerView(){
    if(!view)return;
    const point=pose.current?.id===view.id?pose.current.position:view.position;
    const corner=cornerNear(point);
    setPlaying(false);
    if(!corner){setNotice("No clear corner in this room.");return;}
    setNotice("");
    setFreeView({id:"free-walk",name:"Walkthrough",...wideView,...corner});
  }
  function quickEditor():WalkEditor|undefined{
    if(!target||!canSelect)return;
    const href=edit&&"/phone/edit/"+encodeURIComponent(plan.id)+"?opening="+encodeURIComponent(target.id);
    const preset=designPreset?homePresets[designPreset]:undefined;
    if(target.kind==="wall"){
      const {id,side}=target;
      const finishes=tourScene.wallFinishes;
      const wall=plan.walls.find(candidate=>candidate.id===id);
      return {kind:"wall",finish:finishes?.[id]?.[side]??null,color:preset?.wall??(wall?.material==="concrete"?"#c7c5be":"#efeae0"),
        onApply:finish=>void applyQuickEdit({wallFinishes:connectedWallFace(plan,target).reduce(
          (result,face)=>setWallSurface(result,face.id,face.side,finish),finishes)})};
    }
    if(hoveredOpening?.kind==="window"){
      const {id}=hoveredOpening;
      const overrides=tourScene.windowFinishes;
      const {material,color}=styledWindowFrame(hoveredOpening,preset?.frame,overrides?.[id]);
      return {kind:"window",href,finish:{material,color},
        onApply:finish=>void applyQuickEdit({windowFinishes:{...overrides,[id]:finish}}),
        onReset:overrides?.[id]?()=>{
          const windowFinishes={...overrides};
          delete windowFinishes[id];
          void applyQuickEdit({windowFinishes});
        }:undefined};
    }
    if(hoveredOpening?.kind==="door"&&!hoveredOpening.passage){
      const {id}=hoveredOpening;
      const closed=tourScene.closedDoorIds??[];
      return {kind:"door",href,closed:closed.includes(id),onToggle:()=>void applyQuickEdit({
        closedDoorIds:closed.includes(id)?closed.filter(door=>door!==id):[...closed,id],
      })};
    }
    if(hovered)return {kind:"object",item:hovered,suggestion:!objects.some(item=>item.id===hovered.id),
      alternatives,onApply:applyQuickFurniture,onRemove:()=>removeQuickFurniture(hovered)};
  }
  const canSelect=!sample&&!furnishing&&!stylesOpen&&!finishesOpen&&!rendered&&!playing&&!adding&&!pickingRoom;
  const editor=quickEditor();
  const highlight=canSelect?(editor?target:pointed):null;
  const selected=!!editor;
  function selectionOutline(){
    if(!highlight)return null;
    if(highlight.kind==="wall")return <WallHighlight faces={connectedWallFace(plan,highlight)}
      pieces={pieces} overview={!view} selected={selected}/>;
    if(highlight.kind==="object"){
      const item=displayedObjects.find(candidate=>candidate.id===highlight.id);
      return item?<ObjectHighlight item={item} scale={scale} selected={selected}/>:null;
    }
    const opening=plan.openings.find(candidate=>candidate.id===highlight.id);
    if(!opening)return null;
    if(opening.kind==="door"){
      const door=doorLeaves(plan,scale,tourScene.closedDoorIds).find(candidate=>candidate.id===opening.id);
      if(door)return <SelectionBox position={[door.x+Math.cos(door.angle)*door.length/2,door.height/2,
        door.z-Math.sin(door.angle)*door.length/2]} rotation={door.angle} width={door.length}
        height={door.height} depth={.06} selected={selected}/>;
    }
    const ends=openingEnds(plan,opening);
    if(!ends)return null;
    const [a,b]=ends;
    return <SelectionBox position={[(a.x+b.x)*scale/2,opening.sillM+opening.heightM/2,(a.y+b.y)*scale/2]}
      rotation={-Math.atan2(b.y-a.y,b.x-a.x)} width={Math.hypot(b.x-a.x,b.y-a.y)*scale}
      height={opening.heightM} depth={.11} selected={selected}/>;
  }
  return <main className="showcase-player" data-furnishing={furnishing} data-placing={!!placement||adding}
    data-pointing={canSelect&&!!pointed} aria-label="3D showcase"
    onPointerDownCapture={event=>{
      if(event.button===0&&furnishing&&event.target instanceof Element&&!event.target.closest(".furnish-sheet,canvas")){
        selectFurniture("");
      }
    }}>
    <h1 className="show-current-view">{view?.name??"Dollhouse view"}</h1>
    <div ref={stage} className="show-stage"><Canvas shadows frameloop="demand" dpr={[1,1.6]} camera={{near:.005,far:2000}} fallback={<p>Enable WebGL to view this tour.</p>}>
      <color attach="background" args={[view?"#d4e3e9":"#d8d9cb"]}/>
      <SceneMesh m={plan} objects={editableObjects}
        detectedObjects={showDetections?suggestions.filter(item=>item.id!==dragPreview?.id):undefined}
        closedDoorIds={tourScene.closedDoorIds} floorStyle={styledScene}
        wallFinishes={tourScene.wallFinishes} windowFinishes={tourScene.windowFinishes} designPreset={designPreset}
        presentation cutaway={!view} walkGround={!!view&&!sample}/>
      {canSelect&&<WalkthroughObjects onHover={next=>setPointed(current=>targetKey(current)===targetKey(next)?current:next)}
        onTap={chooseTarget}/>}
      {editor&&target&&<WalkTargetAnchor key={targetKey(target)} target={target} element={menu}/>}
      {!dragPreview&&selectionOutline()}
      {sample&&<SampleFurniture interior={!!view}/>}
      {view?<ShowcaseWalk key={view.id} plan={plan} scene={walkScene} view={view} sample={sample} pose={pose} onFrame={setViewport} keyboard={!rendered}/>:
        <><OverviewCamera plan={plan}/>{!furnishing&&<FloorPicker scale={scale} roomPicking={adding||pickingRoom} onPick={land}/>}</>}
      {(furnishing||canSelect)&&<FurniturePlacement scale={scale} walkthrough={!!view} disabled={saving} pending={placement}
        direct={!furnishing} objects={displayedObjects} catalogDrag={catalogDrag}
        onPreview={item=>setDragPreview(item&&canPlaceFurniture(item)?item:null)}
        onPlace={(item,point)=>{
          if(furnishing)placeFurniture(item,point);
          else if(point)applyQuickFurniture({...item,position:point});
        }} onSelect={selectFurniture}/>}
      {!dragPreview&&fit&&selectedFurniture&&<>
        <FitOverlay points={footprint({...selectedFurniture,width:selectedFurniture.width+.08,depth:selectedFurniture.depth+.08},scale)}
          scale={scale} color={fitWarnings.length?"#af5035":"#477b63"}/>
        {fit.swing.concat(fit.clearance,fit.narrow).map((points,i)=><FitOverlay key={i} points={points} scale={scale} color="#af5035"/>)}
      </>}
      {!view&&tags.map(tag=><Html key={tag.key} portal={stage} center wrapperClass="show-room-label" style={{pointerEvents:"none",display:furnishing?"none":undefined}}
        position={[tag.position.x*scale,.18,tag.position.y*scale]} zIndexRange={[1,0]}>
        <span className="show-room-tag">{tag.text}</span>
      </Html>)}
      {!view&&!adding&&!pickingRoom&&!furnishing&&<ShowcaseViewPins views={views} scale={scale} portal={stage} disabled={saving}
        onVisit={select} onMove={(view,position)=>void repositionView(view,position)}/>}
    </Canvas>
    </div>
    {view&&rendered&&renders[view.id]&&<div className="show-render"><img src={renders[view.id]} alt={"Saved design render for "+view.name}/></div>}
    {desktop ? <header className="studio-header" data-tour-tools>
      <DesktopBrand/>
      <nav className="studio-modes" aria-label="Workspace views">
      <Link href={edit ?? "/"} onClick={()=>{
        const previous = view ? pose.current ?? view : lastWalkPose.current;
        if (studioPoseKey && previous) {
          try { sessionStorage.setItem(studioPoseKey, JSON.stringify(previous)); } catch {}
        }
      }}>{edit ? "Plan" : "Homes"}</Link>
      <button aria-pressed={!view} onClick={()=>{if(view){lastWalkPose.current=pose.current??view;select(-1);}}}><Box size={16}/>Overview</button>
      <button aria-pressed={!!view} disabled={!views.length} onClick={()=>{if(!view){select(0);setFreeView(lastWalkPose.current);}}}><Footprints size={16}/>Walk</button>
      </nav>
      <span className="studio-floor-name" title={title}>{title}</span>
    </header> : view&&<button type="button" className="show-overview" data-tour-tools onClick={()=>select(-1)}><Box size={18}/>Overview</button>}
    {desktop&&(approximate||stale||notice)&&<div className="studio-status" role="status">
      {approximate?"Approximate scale":stale?<Link href={(edit??"/")+"?setup=furniture"}>Review scene against the updated plan</Link>:notice}
    </div>}
    {editor&&<WalkthroughEditMenu key={targetKey(target)} editor={editor} menu={menu} busy={saving} message={quickNotice} close={()=>chooseTarget(null)}/>}
    {stylesOpen&&<section className="finish-sheet style-sheet" aria-label="Whole-home style" data-tour-tools onWheel={scrollTourRail}>
      <div className="finish-heading"><h2>Whole-home style</h2><button aria-label="Close styles" onClick={()=>{setPresetDraft(undefined);setStylesOpen(false);}}><X size={18}/></button></div>
      <div className="tour-rail style-presets">
        {Object.entries(homePresets).map(([key,preset])=><button key={key} aria-pressed={designPreset===key}
          onClick={()=>setPresetDraft(key as HomePreset)}>
          <span className="style-swatches" aria-hidden>{[preset.floor.color,preset.fabric,preset.door].map((color,i)=><i key={i} style={{background:color}}/>)}</span>{preset.name}
        </button>)}
        <button aria-pressed={!designPreset} onClick={()=>setPresetDraft(null)}>Original</button>
      </div>
      <button className="finish-save" disabled={saving||presetDraft===undefined} onClick={()=>void applyPreset()}>Apply style</button>
    </section>}
    {furnishing?<FurnishSheet objects={objects} selected={selectedFurniture} previewReason={previewReason}
      detected={suggestions}
      onInsertDetected={item=>{
        if(objects.length>=100)return;
        setPlacement(null);setFurnitureDraft([...objects,item]);setFurnitureId(item.id);
      }}
      pending={placement}
      dirty={!!furnitureDraft} saving={saving} message={furnitureNotice} issues={fitWarnings}
      edit={edit&&"/phone/edit/"+encodeURIComponent(plan.id)}
      onAdd={kind=>{
        if(placement?.kind===kind&&!selectedFurniture) selectFurniture("");
        else {selectFurniture("");setPlacement(newItem(kind,{x:0,y:0}));}
      }}
      onDragStart={kind=>{catalogDrag.current=newItem(kind,{x:0,y:0});setFurnitureNotice("");}}
      onDragEnd={()=>{catalogDrag.current=null;setDragPreview(null);}}
      onSelect={selectFurniture}
      onMove={()=>{if(selectedFurniture){setPlacement(placement?null:selectedFurniture);setFurnitureNotice("");}}}
      onRotate={degrees=>{if(selectedFurniture)updateFurniture({...selectedFurniture,rotation:(selectedFurniture.rotation+degrees+360)%360});}}
      onResize={(key,value)=>{
        if(!selectedFurniture)return;
        const item={...selectedFurniture,[key]:value};
        if(key==="width"&&item.mattressWidth!=null)item.mattressWidth=Math.min(value,item.mattressWidth);
        if(key==="depth"&&item.mattressDepth!=null)item.mattressDepth=Math.min(value*.96,item.mattressDepth);
        updateFurniture(item);
      }}
      onScreenSize={inches=>{if(selectedFurniture?.kind==="tv")updateFurniture({...selectedFurniture,...tvDimensions(inches)});}}
      onRemove={()=>{setFurnitureDraft(objects.filter(item=>item.id!==furnitureId));selectFurniture("");}}
      onClose={closeFurnish} onSave={()=>void applyFurniture()}/>:
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
      {(adding||pickingRoom||(!desktop&&toolsOpen))&&<div className="show-heading">
        <small>{approximate?"Approximate scale · ":""}{title}</small>
        <p>{pickingRoom?"Tap a room’s floor to choose it.":adding?"Tap a room to add a wide corner view.":rendered?"Saved design render":view?"Tap to walk. Drag two fingers to move, twist to turn, and pinch to zoom.":"Drag a numbered pin to move its view. Drag the scene to orbit."}</p>
      </div>}
      <div className="show-dock">
        <button type="button" className="show-menu-button" aria-label={toolsOpen?"Close tour tools":"Open tour tools"}
          aria-expanded={toolsOpen||pickingRoom} aria-controls="show-tour-actions"
          onClick={()=>{
            if(pickingRoom){setPickingRoom(false);setFinishesOpen(true);}
            else setToolsOpen(!toolsOpen);
          }}>
          {toolsOpen||pickingRoom?<X/>:<LayoutGrid/>}{desktop&&<span>{toolsOpen||pickingRoom?"Close":"Design"}</span>}
        </button>
        <div id="show-tour-actions" className="show-list" role="group" aria-label="Tour actions" hidden={!toolsOpen&&!pickingRoom} onWheel={scrollTourRail}>
          {pickingRoom?<button onClick={()=>{setPickingRoom(false);setFinishesOpen(true);}}><X/>Cancel room selection</button>:<>
          {!sample&&<button disabled={saving} onClick={()=>{setPlaying(false);setRendered(false);setFinishesOpen(false);closeFurnish();setStylesOpen(true);setToolsOpen(false);}}><Layers/>Styles</button>}
          {hasFloor&&<button disabled={saving} onClick={()=>{
            setPlaying(false);setRendered(false);setAdding(false);setStylesOpen(false);setPresetDraft(undefined);closeFurnish();setFinishesOpen(true);
          }}><Layers/>Finishes</button>}
          {!!suggestions.length&&<button type="button" aria-pressed={showDetections} onClick={()=>setShowDetections(shown=>!shown)}>
            <Armchair/>Detected preview
          </button>}
          {!sample&&<button disabled={saving} onClick={openFurnish}><Armchair/>Furnish</button>}
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
          {edit&&<Link href={desktop?edit:"/phone/edit/"+encodeURIComponent(plan.id)}><PencilRuler/>Edit floor</Link>}
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
      {(pinNotice||(toolsOpen||adding||pickingRoom)&&(!hasFloor||notice||needsFinishReview))&&
        <p role="status">{pinNotice||notice||(!hasFloor?"Using a preview floor.":"Some saved floor finishes need review. Open Finishes.")}</p>}
      {toolsOpen&&check?.mismatch&&<p role="alert" className="show-scale-warning">Scale measurements differ by {(check.difference*100).toFixed(1)}%. Check scale in Edit floor.</p>}
    </section>}
  </main>;
}
