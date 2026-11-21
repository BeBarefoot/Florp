"use client";
import {useEffect,useMemo,useState} from "react";
import {Canvas,useThree} from "@react-three/fiber";
import {Html,OrbitControls} from "@react-three/drei";
import {Vector3} from "three";
import Link from "next/link";
import {ArrowLeft,Maximize2,Minimize2,Box,ChevronLeft,ChevronRight,MapPin,Pause,Play,Share2} from "lucide-react";
import {SceneMesh} from "./SceneMesh";
import {metersPerPixel} from "../../lib/plan/derive";
import {savedPose} from "../../lib/plan/camera";
import type {PlanModel} from "../../lib/plan/model";
import type {Scene,View} from "../../lib/plan/scene";

function SampleFurniture({interior}:{interior:boolean}){
  function block(x:number,y:number,z:number,w:number,h:number,d:number,color:string){
    return <mesh position={[x,y,z]}><boxGeometry args={[w,h,d]}/><meshStandardMaterial color={color}/></mesh>;
  }
  return <>
    {Array.from({length:27},(_,i)=><group key={"board"+i}>
      {block(5,.002,i*.25+.1,9.9,.002,.006,"#aa865f")}
    </group>)}
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
    {Array.from({length:27},(_,i)=><group key={"board"+i}>
      {block(5,.002,i*.25+.1,9.9,.002,.006,"#aa865f")}
    </group>)}
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
    <mesh position={[.75,.25,1]}><cylinderGeometry args={[.28,.2,.5,20]}/><meshStandardMaterial color="#bb845e"/></mesh>
    <mesh position={[.75,.82,1]} scale={[.46,.76,.42]}><icosahedronGeometry args={[1,1]}/><meshStandardMaterial color="#708763" flatShading/></mesh>
  </>;
}

function CameraRig({plan,view}:{plan:PlanModel;view?:View}){
  const {camera,size}=useThree();
  const scale=metersPerPixel(plan)!;
  const rig=useMemo(()=>{
    const aspect=size.width/Math.max(1,size.height);
    if(view){
      const pose=savedPose(view,scale,aspect);
      const eye=new Vector3(...pose.position);
      return {eye,target:eye.clone().addScaledVector(new Vector3(...pose.direction),.01),fov:pose.verticalFovDeg};
    }
    const span=Math.max(1,plan.imageTransform.width*scale,plan.imageTransform.height*scale);
    const target=new Vector3(plan.imageTransform.width*scale/2,.65,plan.imageTransform.height*scale/2);
    const distance=span*1.85/Math.min(1,aspect);
    return {target,eye:target.clone().addScaledVector(new Vector3(.82,1.1,1.22).normalize(),distance),fov:42};
  },[plan,view,scale,size.width,size.height]);
  const perspective=camera as import("three").PerspectiveCamera;
  // Set the initial pose before OrbitControls reads the camera.
  return <><primitive object={perspective} position={rig.eye} fov={rig.fov} onUpdate={()=>perspective.updateProjectionMatrix()}/>
    <OrbitControls target={rig.target} enablePan={false} enableZoom={!view} rotateSpeed={view?-.52:.65}
      minPolarAngle={view ? .12 : .08} maxPolarAngle={view?Math.PI-.12:Math.PI*.47}/></>;
}

export default function Showcase({plan,scene,title,back,sample=false,renders={}}:{plan:PlanModel;scene:Scene;title:string;back:string;sample?:boolean;renders?:Record<string,string>}){
  const [stop,setStop]=useState(scene.views.length?0:-1),[playing,setPlaying]=useState(false),[notice,setNotice]=useState("");
  const [rendered,setRendered]=useState(false),[immersive,setImmersive]=useState(false);
  const scale=metersPerPixel(plan)!;
  const views=scene.views,view=views[stop];
  useEffect(()=>{
    const read=()=>{const id=new URLSearchParams(location.hash.slice(1)).get("view");setStop(location.hash==="#overview"||!views.length?-1:Math.max(0,views.findIndex(v=>v.id===id)));};
    read();window.addEventListener("hashchange",read);return ()=>window.removeEventListener("hashchange",read);
  },[views]);
  useEffect(()=>{
    if(!playing)return;
    const timer=setTimeout(()=>{if(stop>=views.length-1)setPlaying(false);else setStop(stop+1);},6500);
    return ()=>clearTimeout(timer);
  },[playing,stop,views.length]);
  function select(index:number){setPlaying(false);setRendered(false);setStop(index);setNotice("");}
  async function share(){
    const url=new URL(location.href);url.hash=view?new URLSearchParams({view:view.id}).toString():"overview";
    try{
      if(navigator.share)await navigator.share({title,url:url.href});
      else {await navigator.clipboard.writeText(url.href);setNotice("Tour link copied");}
    }catch(e){if(!(e instanceof Error&&e.name==="AbortError"))setNotice(url.href);}
  }
  return <main className="showcase-player" data-immersive={immersive} aria-label="3D showcase">
    <Canvas dpr={[1,1.6]} camera={{near:.005,far:2000}} fallback={<p>Enable WebGL to view this tour.</p>}>
      <color attach="background" args={[sample&&view?"#cfdfdf":"#d8d9cb"]}/>
      <SceneMesh m={plan} objects={scene.objects} closedDoorIds={scene.closedDoorIds} floorFinish={scene.floorFinish}/>
      {sample&&<SampleFurniture interior={!!view}/>}
      <CameraRig key={view?.id??"overview"} plan={plan} view={view}/>
      {!view&&views.map((v,i)=><Html key={v.id} center position={[v.position.x*scale,2,v.position.y*scale]} zIndexRange={[2,1]}>
        <button className="show-pin" aria-label={"Visit "+v.name} onClick={()=>select(i)}>{i+1}</button>
      </Html>)}
    </Canvas>
    {view&&rendered&&renders[view.id]&&<div className="show-render"><img src={renders[view.id]} alt={"Saved design render for "+view.name}/></div>}
    <div className="show-top"><Link href={back}><ArrowLeft size={18}/> Exit tour</Link><div className="show-tools"><button aria-label={immersive?"Show tour controls":"Hide tour controls"} aria-pressed={immersive} onClick={()=>setImmersive(!immersive)}>{immersive?<Minimize2 size={18}/>:<Maximize2 size={18}/>}</button><button onClick={share} aria-label="Share this tour"><Share2 size={18}/></button></div></div>
    <section className="show-panel"><small>{sample?"Sample tour · ":""}{title}</small><h1>{view?.name??"Dollhouse view"}</h1>
      <p>{view&&rendered&&renders[view.id]?"Saved design render":view?"Drag to look around.":"Drag to orbit. Pinch or scroll to zoom."}</p>
      {view&&renders[view.id]&&<button aria-pressed={rendered} onClick={()=>{setPlaying(false);setRendered(!rendered);}}>{rendered?"Return to 3D":"Show saved design"}</button>}
      <div className="show-stops" aria-label="Tour stops">
        <button aria-pressed={!view} onClick={()=>select(-1)}><Box size={15}/> Overview</button>
        {views.map((v,i)=><button key={v.id} aria-pressed={stop===i} onClick={()=>select(i)}><MapPin size={14}/>{v.name}</button>)}
      </div>
      {!!views.length&&<div className="show-transport">
        <button onClick={()=>{setRendered(false);if(!playing&&stop===views.length-1)setStop(-1);setPlaying(!playing);}}>{playing?<Pause size={16}/>:<Play size={16}/>} {playing?"Pause":"Play tour"}</button>
        <button aria-label="Previous stop" disabled={stop<0} onClick={()=>select(stop-1)}><ChevronLeft/></button>
        <button aria-label="Next stop" disabled={stop>=views.length-1} onClick={()=>select(stop+1)}><ChevronRight/></button>
      </div>}
      {notice&&<p role="status">{notice}</p>}
    </section>
  </main>;
}
