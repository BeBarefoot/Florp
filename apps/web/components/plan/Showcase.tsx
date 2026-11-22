"use client";
import {useCallback,useEffect,useMemo,useRef,useState} from "react";
import {Canvas,useThree} from "@react-three/fiber";
import {Html,OrbitControls} from "@react-three/drei";
import {Vector3} from "three";
import Link from "next/link";
import {ArrowLeft,Maximize2,Minimize2,Box,ChevronLeft,ChevronRight,MapPin,Pause,Play,Share2} from "lucide-react";
import {downloadPrompt,renderPrompt} from "../../lib/plan/renderPrompt";
import {SceneMesh} from "./SceneMesh";
import {metersPerPixel} from "../../lib/plan/derive";
import {WalkCamera,type WalkInput} from "./WalkCamera";
import {findWalkStart,walkSpace} from "../../lib/plan/walkSpace";
import {FloorPicker} from "./FloorPicker";
import {newUuid} from "../../lib/uuid";
import type {PlanModel,Pt} from "../../lib/plan/model";
import type {Frame,Scene,View} from "../../lib/plan/scene";

function SampleFurniture({interior}:{interior:boolean}){
  function block(x:number,y:number,z:number,w:number,h:number,d:number,color:string){
    return <mesh castShadow receiveShadow position={[x,y,z]}><boxGeometry args={[w,h,d]}/><meshStandardMaterial color={color}/></mesh>;
  }
  return <>
    {[3.31,4.64,5.94].map(x=><group key={x}>{block(x,1.58,.008,.035,1.65,.08,"#756955")}</group>)}
    {block(4.625,.75,.01,2.71,.07,.17,"#99816a")}
    {block(4.625,2.4,.01,2.71,.06,.08,"#756955")}
    {[2.11,3.71,5.29].map(z=><group key={z}>{block(.01,1.58,z,.08,1.65,.035,"#756955")}</group>)}
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
    const distance=span*1.85/Math.min(1,aspect);
    return {target,eye:target.clone().addScaledVector(new Vector3(.82,1.1,1.22).normalize(),distance)};
  },[plan,scale,size.width,size.height]);
  const perspective=camera as import("three").PerspectiveCamera;
  return <><primitive object={perspective} position={eye} fov={42} onUpdate={()=>perspective.updateProjectionMatrix()}/>
    <OrbitControls target={target} enablePan={false} rotateSpeed={.65} minPolarAngle={.08} maxPolarAngle={Math.PI*.47}/></>;
}

type WalkFrame = {viewId:string;width:number;height:number;image:()=>string};

function clearSampleFloor(p:Pt,scale:number){
  return ![[.99,.96,3.81,1.96],[1.75,2.51,3.25,3.19],[3.08,4.57,4.84,5.57],
    [3.67,4,4.23,4.52],[3.67,5.63,4.23,6.13],[.41,.66,1.09,1.34]]
    .some(([a,b,c,d])=>p.x*scale>=a&&p.x*scale<=c&&p.y*scale>=b&&p.y*scale<=d);
}

function ShowcaseWalk({plan,scene,view,sample,pose,onFrame,input}:{
  input?:WalkInput;plan:PlanModel;scene:Scene;view:View;sample:boolean;pose:{current:View|null};onFrame:(frame:WalkFrame|null)=>void;
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
  return <WalkCamera view={view} scale={scale} frame={frame} pose={pose} input={input}
    canMove={p=>space.validCamera(p,true)&&(!sample||clearSampleFloor(p,scale))}/>;

}

export default function Showcase({plan,scene,title,back,edit,sample=false,approximate=false,renders={},saveView}:{plan:PlanModel;scene:Scene;title:string;back:string;edit?:string;sample?:boolean;approximate?:boolean;renders?:Record<string,string>;saveView?:(view:View)=>Promise<View>}){
  const [localViews,setLocalViews]=useState<View[]>([]);
  const [freeView,setFreeView]=useState<View|null>(null);
  const [adding,setAdding]=useState(false);
  const [saving,setSaving]=useState(false);
  const savingRef=useRef(false);
  const [selectedId,setSelectedId]=useState<string|null>(null);
  const views=useMemo(()=>{
    if(scene.views.length||localViews.length)return [...scene.views,...localViews];
    const start=findWalkStart(plan,walkSpace(plan,metersPerPixel(plan)!,scene).validCamera);
    const entry:View={id:"walk-start",name:"Walkthrough",position:start??{x:0,y:0},yaw:0,pitch:-5,horizontalFov:90,eyeHeight:1.6};
    return start?[entry]:[];
  },[plan,scene,localViews]);
  const [playing,setPlaying]=useState(false),[notice,setNotice]=useState("");
  const [rendered,setRendered]=useState(false),[immersive,setImmersive]=useState(false);
  const scale=metersPerPixel(plan)!;
  const stop=selectedId==="overview"?-1:selectedId===null?(views.length?0:-1):views.findIndex(v=>v.id===selectedId);
  const view=freeView??views[stop];
  const latestViews=useRef(views);
  useEffect(()=>{latestViews.current=views;},[views]);
  const touchInput=useRef({forward:0,side:0});
  const wake=useRef<(()=>void)|null>(null);
  const input=useMemo(()=>({direction:touchInput,wake}),[]);
  const space=useMemo(()=>walkSpace(plan,scale,scene),[plan,scale,scene]);
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
    const entry={...location,id:newUuid(),name:"View "+(scene.views.length+localViews.length+1)};
    try{
      const saved=saveView?await saveView(entry):entry;
      if(!saveView)setLocalViews(current=>[...current,saved]);
      setFreeView(null);setSelectedId(saved.id);setAdding(false);
      setNotice(saveView?"View saved":"View added for this session");
    }catch(e){setNotice(String(e));}
    finally{savingRef.current=false;setSaving(false);}
  },[scene.views.length,localViews.length,saveView]);
  const land=useCallback((point:Pt|null,yaw:number)=>{
    if(savingRef.current)return;
    if(!point||!space.validCamera(point,true)||(sample&&!clearSampleFloor(point,scale))){
      setNotice("Choose an open spot on the floor.");
      return;
    }
    setPlaying(false);setRendered(false);setNotice("");setSelectedId("overview");
    const entry:View={id:"free-walk",name:"Walkthrough",position:point,yaw,pitch:-5,eyeHeight:1.6,horizontalFov:90};
    if(adding)void addView(entry);
    else setFreeView(entry);
  },[adding,addView,space,sample,scale]);
  async function share(){
    const url=new URL(location.href);url.hash=view&&!freeView&&!localViews.some(v=>v.id===view.id)?new URLSearchParams({view:view.id}).toString():"overview";
    try{
      if(navigator.share)await navigator.share({title,url:url.href});
      else {await navigator.clipboard.writeText(url.href);setNotice("Tour link copied");}
    }catch(e){if(!(e instanceof Error&&e.name==="AbortError"))setNotice(url.href);}
  }
  return <main className="showcase-player" data-immersive={immersive} aria-label="3D showcase">
    <div className="show-stage"><Canvas shadows frameloop="demand" dpr={[1,1.6]} camera={{near:.005,far:2000}} fallback={<p>Enable WebGL to view this tour.</p>}>
      <color attach="background" args={[sample&&view?"#cfdfdf":"#d8d9cb"]}/>
      <SceneMesh m={plan} objects={scene.objects} closedDoorIds={scene.closedDoorIds} floorFinish={scene.floorFinish} presentation cutaway={!view}/>
      {sample&&<SampleFurniture interior={!!view}/>}
      {view?<ShowcaseWalk key={view.id} plan={plan} scene={scene} view={view} sample={sample} pose={pose} onFrame={setViewport} input={rendered?undefined:input}/>:<><OverviewCamera plan={plan}/><FloorPicker scale={scale} onPick={land}/></>}
      {!view&&views.map((v,i)=><Html key={v.id} center position={[v.position.x*scale,2,v.position.y*scale]} zIndexRange={[2,1]}>
        <button className="show-pin" aria-label={"Visit "+v.name} onClick={()=>select(i)}>{i+1}</button>
      </Html>)}
    </Canvas>
    {view&&!rendered&&<div className="show-movement" role="group" aria-label="Walk controls">
      {([["↑","Walk forward",1,0],["←","Step left",0,-1],["↓","Walk backward",-1,0],["→","Step right",0,1]] as const).map(([symbol,label,forward,side])=>
        <button key={label} aria-label={label}
          onPointerDown={e=>{
            if(e.button!==0)return;
            e.currentTarget.setPointerCapture(e.pointerId);touchInput.current={forward,side};wake.current?.();
          }}
          onLostPointerCapture={()=>{touchInput.current={forward:0,side:0};}}
          onKeyDown={e=>{if(e.key===" "||e.key==="Enter"){e.preventDefault();touchInput.current={forward,side};wake.current?.();}}}
          onKeyUp={e=>{if(e.key===" "||e.key==="Enter")touchInput.current={forward:0,side:0};}}
          onBlur={()=>{touchInput.current={forward:0,side:0};}}
        >{symbol}</button>)}
    </div>}</div>
    {view&&rendered&&renders[view.id]&&<div className="show-render"><img src={renders[view.id]} alt={"Saved design render for "+view.name}/></div>}
    <div className="show-top"><Link href={back}><ArrowLeft size={18}/> Exit tour</Link><div className="show-tools"><button aria-label={immersive?"Show tour controls":"Hide tour controls"} aria-pressed={immersive} onClick={()=>setImmersive(!immersive)}>{immersive?<Minimize2 size={18}/>:<Maximize2 size={18}/>}</button><button onClick={share} aria-label="Share this tour"><Share2 size={18}/></button></div></div>
    <section className="show-panel"><small>{sample?"Sample tour · ":""}{title}{approximate?" · Approximate scale":""}</small><h1>{view?.name??"Dollhouse view"}</h1>
      <p>{view&&rendered&&renders[view.id]?"Saved design render":view?"Drag to turn and walk. Use the arrows or WASD to move. Pinch or scroll to zoom.":adding?(saveView?"Tap an open floor spot to save a view there.":"Tap an open floor spot to add a view for this session."):"Tap the floor to walk there. Drag to orbit."}</p>
      {view&&renders[view.id]&&<button aria-pressed={rendered} onClick={()=>{setPlaying(false);setRendered(!rendered);}}>{rendered?"Return to 3D":"Show saved design"}</button>}
      <div className="show-stops" aria-label="Tour stops">
        <button aria-pressed={!view} onClick={()=>select(-1)}><Box size={15}/> Overview</button>
        {views.map((v,i)=><button key={v.id} aria-pressed={!freeView&&stop===i} onClick={()=>select(i)}><MapPin size={14}/>{v.name}</button>)}
      </div>
      {views.length>1&&<div className="show-transport">
        <button onClick={()=>{setRendered(false);if(!playing&&stop===views.length-1)select(-1);setPlaying(!playing);}}>{playing?<Pause size={16}/>:<Play size={16}/>} {playing?"Pause":"Play tour"}</button>
        <button aria-label="Previous stop" disabled={stop<0} onClick={()=>select(stop-1)}><ChevronLeft/></button>
        <button aria-label="Next stop" disabled={stop>=views.length-1} onClick={()=>select(stop+1)}><ChevronRight/></button>
      </div>}
      {!view&&<button aria-pressed={adding} disabled={saving} onClick={()=>{setPlaying(false);setNotice("");setAdding(!adding);}}>
        {adding?"Cancel adding view":"Add view"}
      </button>}
      {view&&!rendered&&<button disabled={saving} onClick={()=>{
        setPlaying(false);
        if(pose.current?.id===view.id)void addView(pose.current);
      }}>Save this view</button>}
      {notice&&<p role="status">{notice}</p>}
    {view&&!rendered&&viewport?.viewId===view.id&&<><button onClick={()=>{
      setPlaying(false);
      if(pose.current?.id===view.id)downloadPrompt(renderPrompt(plan,scene,pose.current,viewport,[],approximate));
    }}>Download view prompt</button><button onClick={()=>{
      setPlaying(false);
      const link=document.createElement("a");
      link.href=viewport.image();link.download="florp-view.png";link.click();
    }}>Download view image</button></>}
    {edit&&<Link className="show-edit" href={edit}>Edit floor</Link>}
    </section>
  </main>;
}
