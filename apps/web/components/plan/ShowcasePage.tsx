"use client";
import {ExtractionProgress} from "./ExtractionProgress";
import {extractWithProgress, type ExtractionProgress as ExtractionState} from "../../lib/plan/extractionProgress";
import dynamic from "next/dynamic";
import Link from "next/link";
import {useParams} from "next/navigation";
import {useEffect,useMemo,useState} from "react";
import type {HomePreset} from "../../lib/plan/homePresets";
import {API,request,type Blueprint} from "../../lib/api";
import type {Alignment,PlanModel,PlanResponse} from "../../lib/plan/model";
import type {Job,Saved,Scene,View,WalkthroughEdit} from "../../lib/plan/scene";
import {metersPerPixel} from "../../lib/plan/derive";
import {samplePlan,sampleScene} from "../../lib/plan/showcaseSample";

import type {StairLanding} from "../../lib/plan/stairLink";
import type {HouseOverview} from "../../lib/plan/houseOverview";

const emptyScene:Scene={views:[],objects:[],style:""};
function previewScale(plan:PlanModel):PlanModel {
  if(metersPerPixel(plan)||!plan.nodes.length)return plan;
  const xs=plan.nodes.map(n=>n.x),ys=plan.nodes.map(n=>n.y);
  const extent=Math.max(Math.max(...xs)-Math.min(...xs),Math.max(...ys)-Math.min(...ys));
  if(extent<5)return plan;
  // This reference is used only for the on-screen draft and is never written to the plan.
  return {...plan,scale:{metersPerPixel:10/extent,reference:{p1:{x:0,y:0},p2:{x:extent,y:0},lengthMeters:10}}};
}

async function openPlan(base:string, onProgress:(state:ExtractionState)=>void){
  const path=base+"/plan";
  const existing=await request<PlanResponse>(path);
  if(existing.model||existing.revision!==0)return existing;
  try{
    return await extractWithProgress(base,0,onProgress);
  }catch(e){
    if(!(e instanceof Error)||!e.message.startsWith("409"))throw e;
    const current=await request<PlanResponse>(path);
    if(!current.model)throw e;
    return current;
  }
}

const Player=dynamic(()=>import("./Showcase"),{ssr:false});
export default function ShowcasePage({desktop = false}: {desktop?: boolean}){
  const {id}=useParams<{id:string}>();
  const [extraction,setExtraction]=useState<ExtractionState|null>(null);
  const [data,setData]=useState<[PlanResponse,Saved,Blueprint]|null>(null),[error,setError]=useState("");
  const [house, setHouse] = useState<{ id: string; upperIsActive: boolean; other: HouseOverview["upper"];
    alignment?: Alignment | null; provisionalOrder: boolean } | null>(null);
  const [houseStatus, setHouseStatus] = useState("");
  const [renders,setRenders]=useState<Record<string,string>>({});
  useEffect(()=>{
    setError("");setData(null);setRenders({});setExtraction(null);
    if(id==="sample")return;
    let live=true;
    const base="/blueprints/"+encodeURIComponent(id);
    Promise.all([openPlan(base,state=>{if(live)setExtraction(state);}),request<Saved>(base+"/scene"),request<Blueprint>(base+"/info")])
      .then(value=>{if(live)setData(value);}).catch(e=>{if(live)setError(String(e));});
    return ()=>{live=false;};
  },[id]);
  useEffect(()=>{
    if(!data||data[2].id!==id)return;
    let live=true;
    const path="/blueprints/"+encodeURIComponent(id)+"/scene/renders";
    request<Job[]>(path).then(jobs=>{
      const images:Record<string,string>={};
      for(const j of jobs){
        if(j.status==="complete"&&j.planRevision===data[0].revision&&!images[j.viewId]&&
          (j.sceneRevision===data[1].revision||j.compatibleSceneRevision===data[1].revision)){
          images[j.viewId]=API+path+"/"+encodeURIComponent(j.id)+"/result.png";
        }
      }
      if(live)setRenders(images);
    }).catch(()=>{});
    return ()=>{live=false;};
  },[data,id]);
  const blueprint = data?.[2];
  const [landings,setLandings]=useState<Record<string,StairLanding>>({});
  const stairsPath = desktop && blueprint?.floor ? `/projects/${encodeURIComponent(blueprint.project_id)}/stair-landings` : "";
  useEffect(()=>{
    setLandings({});
    if(!stairsPath)return;
    const controller=new AbortController();
    request<Record<string,StairLanding>>(stairsPath,{signal:controller.signal})
      .then(result=>{if(!controller.signal.aborted)setLandings(result);}).catch(()=>{});
    return ()=>controller.abort();
  },[stairsPath,id]);
  useEffect(() => {
    setHouse(null);
    setHouseStatus("");
    if (!desktop || blueprint?.id !== id || !blueprint.project_id) return;
    let active = true;
    let foundOtherFloor = false;
    const project = "/projects/" + encodeURIComponent(blueprint.project_id);
    async function loadHouse() {
      if (!blueprint) return;
      const pair = blueprint.floor;
      let otherId = pair?.otherId;
      let upperIsActive = pair?.level === 2;
      if (!otherId) {
        const floors = await request<Blueprint[]>(project + "/blueprints");
        if (!Array.isArray(floors) || floors.length !== 2 || !floors.some(floor => floor.id === id)) return;
        const [first, second] = [...floors].sort((a, b) => (a.created_at ?? "").localeCompare(b.created_at ?? ""));
        upperIsActive = second.id === id;
        otherId = upperIsActive ? first.id : second.id;
      }
      foundOtherFloor = true;
      if (active) setHouseStatus("Preparing the other floor…");
      const base = "/blueprints/" + encodeURIComponent(otherId);
      const [result, saved, pairing] = await Promise.all([
        openPlan(base, progress => { if (active) setHouseStatus("Preparing the other floor · " + progress.percent + "%"); }),
        request<Saved>(base + "/scene"),
        pair ? request<{first:string; second:string; alignment?:Alignment|null} | null>(project + "/floor-pair") : null,
      ]);
      if (!active) return;
      const other = result.model && previewScale(result.model);
      if (!other?.walls.length || !metersPerPixel(other)) {
        setHouseStatus("The other floor needs walls before it can appear in 3D.");
        return;
      }
      const first = upperIsActive ? otherId : id, second = upperIsActive ? id : otherId;
      const alignment = pairing?.first === first && pairing.second === second ? pairing.alignment : null;
      setHouse({id,upperIsActive,other:{plan:other,scene:saved.planRevision===other.revision?saved.config:emptyScene},
        alignment,provisionalOrder:!pair});
      setHouseStatus("");
    }
    void loadHouse().catch(error => {
      if (active) setHouseStatus(foundOtherFloor || blueprint.floor ? String(error) : "");
    });
    return () => { active = false; };
  }, [blueprint,desktop,id]);
  const original=data?.[0].model;
  const plan=useMemo(()=>original?previewScale(original):null,[original]);
  if(id==="sample")return <Player plan={samplePlan} scene={sampleScene} title="Courtyard apartment" sample desktop={desktop}/>;
  const back=desktop?(data?.[2].project_id ? "/project/"+data[2].project_id : "/"):data?.[2].project_id?"/phone/spaces/"+data[2].project_id:"/phone";
  if(data&&data[2].id===id&&plan&&metersPerPixel(plan)&&plan.walls.length){
    const approximate=plan!==original;
    const currentScene=!approximate&&data[1].planRevision===plan.revision;
    const {floorFinish,floorMaterial,roomFloorMaterials,wallFinishes,windowFinishes,designPreset}=data[1].config;
    const scene=currentScene?data[1].config:{...emptyScene,floorFinish,floorMaterial,roomFloorMaterials,wallFinishes,windowFinishes,designPreset,objects:desktop?data[1].config.objects:[],views:desktop?data[1].config.views:[]};
    const priorScene=data[1], planRevision=plan.revision;
    const canSave=!approximate&&(!priorScene.revision||currentScene);
    async function saveDesign(change:Pick<Scene,"floorMaterial"|"roomFloorMaterials">|Pick<Scene,"designPreset">|WalkthroughEdit){
      const saved=await request<Saved>("/blueprints/"+encodeURIComponent(id)+"/scene",{
        method:"PUT",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({expectedRevision:priorScene.revision,planRevision,
          config:{...priorScene.config,...change}}),
      });
      setRenders({});
      setData(current=>current?.[2].id===id?[current[0],saved,current[2]]:current);
    }
    async function saveViews(update:(views:View[])=>View[]){
      const path="/blueprints/"+encodeURIComponent(id)+"/scene";
      const latest=await request<Saved>(path);
      if(latest.revision&&latest.planRevision!==planRevision)
        throw Error("The floor has changed. Reload the tour before saving.");
      const saved=await request<Saved>(path,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({
        expectedRevision:latest.revision,planRevision,
        config:{...latest.config,views:update(latest.config.views)},
      })});
      setRenders({});
      setData(current=>current?.[2].id===id?[current[0],saved,current[2]]:current);
      return saved.config.views;
    }
    const {floor,project_id}=data[2];
    const levelAction = desktop && project_id ? floor
      ? {href:`/studio/${encodeURIComponent(floor.otherId)}#overview`, label:floor.level===1?"Second floor":"First floor", importing:false}
      : house?.id===id
        ? {href:`/studio/${encodeURIComponent(house.other.plan.id)}#overview`, label:house.upperIsActive?"First floor":"Second floor", importing:false}
        : {href:`/project/${encodeURIComponent(project_id)}#add-floor`, label:"Import second floor", importing:true}
      : undefined;
    const activeLevel = {plan,scene};
    const overview = house?.id === id ? {
      ground:house.upperIsActive ? house.other : activeLevel, upper:house.upperIsActive ? activeLevel : house.other,
      alignment:house.alignment, provisionalOrder:house.provisionalOrder,
    } : undefined;
    const stairs=floor&&stairsPath?{
      id:floor.otherId, level:floor.level, regions:floor.regions, local:landings[id],
      destination:landings[floor.otherId],
      save:async (landing:StairLanding)=>setLandings(await request<Record<string,StairLanding>>(
        stairsPath+"/"+encodeURIComponent(id),{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(landing)})),
    }:undefined;
    return <Player key={id} stairs={stairs} house={overview} houseStatus={houseStatus} alignmentHref={`/project/${encodeURIComponent(project_id)}#${floor?"floor-alignment":"floor-review"}`}
      levelAction={levelAction} plan={plan} scene={scene} desktop={desktop} stale={!!priorScene.revision&&!currentScene&&!approximate}
      approximate={approximate} renders={currentScene?renders:undefined} title={data[2].filename}
      edit={"/plan/"+id}
      saveFinishes={canSave?saveDesign:undefined}
      savePreset={canSave?(preset:HomePreset|null)=>saveDesign({designPreset:preset}):undefined}
      saveWalkEdit={canSave?saveDesign:undefined}
      saveFurniture={canSave?objects=>saveDesign({objects}):undefined}
      moveView={canSave?async (viewId,position)=>{
        await saveViews(views=>{
          if(!views.some(view=>view.id===viewId))throw Error("This view is no longer saved.");
          return views.map(view=>view.id===viewId?{...view,position}:view);
        });
      }:undefined}
      saveView={canSave?async (view,initial)=>{
        const views=await saveViews(current=>{
          const prior=current.length||!initial?current:[initial];
          if(prior.length>=30)throw Error("The tour already has 30 saved views.");
          return [...prior,{...view,name:"View "+(prior.length+1)}];
        });
        return views.find(v=>v.id===view.id)!;
      }:undefined}/>;
  }
  return <main className="tour-library"><Link href={back}>← Back to floors</Link>
    {!error&&extraction&&<ExtractionProgress state={extraction}/>}
    <p role="status">{error||(!data?"Preparing your 3D walkthrough…":"Florp could not find enough walls for this floor.")}</p>
    {error?<button onClick={()=>location.reload()}>Retry</button>:data&&<Link href={"/plan/"+id}>Open plan editor</Link>}</main>;
}
