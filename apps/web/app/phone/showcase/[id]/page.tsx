"use client";
import dynamic from "next/dynamic";
import Link from "next/link";
import {useParams} from "next/navigation";
import {useEffect,useMemo,useState} from "react";
import {API,request,type Blueprint} from "../../../../lib/api";
import type {PlanModel,PlanResponse} from "../../../../lib/plan/model";
import type {Job,Saved,Scene} from "../../../../lib/plan/scene";
import {metersPerPixel} from "../../../../lib/plan/derive";
import {samplePlan,sampleScene} from "../../../../lib/plan/showcaseSample";

const emptyScene:Scene={views:[],objects:[],style:""};
function previewScale(plan:PlanModel):PlanModel {
  if(metersPerPixel(plan)||!plan.nodes.length)return plan;
  const xs=plan.nodes.map(n=>n.x),ys=plan.nodes.map(n=>n.y);
  const extent=Math.max(Math.max(...xs)-Math.min(...xs),Math.max(...ys)-Math.min(...ys));
  if(extent<5)return plan;
  // This reference is used only for the on-screen draft and is never written to the plan.
  return {...plan,scale:{metersPerPixel:10/extent,reference:{p1:{x:0,y:0},p2:{x:extent,y:0},lengthMeters:10}}};
}

async function openPlan(base:string){
  const path=base+"/plan";
  const existing=await request<PlanResponse>(path);
  if(existing.model||existing.revision!==0)return existing;
  try{
    return await request<PlanResponse>(path+"/extract?expected_revision=0",{method:"POST"});
  }catch(e){
    if(!(e instanceof Error)||!e.message.startsWith("409"))throw e;
    const current=await request<PlanResponse>(path);
    if(!current.model)throw e;
    return current;
  }
}

const Player=dynamic(()=>import("../../../../components/plan/Showcase"),{ssr:false});
export default function ShowcasePage(){
  const {id}=useParams<{id:string}>();
  const [data,setData]=useState<[PlanResponse,Saved,Blueprint]|null>(null),[error,setError]=useState("");
  const [renders,setRenders]=useState<Record<string,string>>({});
  useEffect(()=>{
    setError("");setData(null);setRenders({});
    if(id==="sample")return;
    let live=true;
    const base="/blueprints/"+encodeURIComponent(id);
    Promise.all([openPlan(base),request<Saved>(base+"/scene"),request<Blueprint>(base+"/info")])
      .then(async value=>{
        if(!live)return;
        setData(value);
        const jobs=await request<Job[]>(base+"/scene/renders").catch(()=>[]);
        const images:Record<string,string>={};
        for(const j of jobs){
          if(j.status==="complete"&&j.sceneRevision===value[1].revision&&j.planRevision===value[0].revision&&!images[j.viewId]){
            images[j.viewId]=API+base+"/scene/renders/"+encodeURIComponent(j.id)+"/result.png";
          }
        }
        if(live)setRenders(images);
      }).catch(e=>{if(live)setError(String(e));});
    return ()=>{live=false;};
  },[id]);
  const original=data?.[0].model;
  const plan=useMemo(()=>original?previewScale(original):null,[original]);
  if(id==="sample")return <Player plan={samplePlan} scene={sampleScene} title="Courtyard apartment" back="/phone" sample/>;
  const back=data?.[2].project_id?"/phone/spaces/"+data[2].project_id:"/phone";
  if(data&&data[2].id===id&&plan&&metersPerPixel(plan)&&plan.walls.length){
    const approximate=plan!==original;
    const currentScene=!approximate&&data[1].planRevision===plan.revision;
    return <Player key={id} plan={plan} scene={currentScene?data[1].config:emptyScene}
      approximate={approximate} renders={currentScene?renders:undefined} title={data[2].filename}
      back={back} edit={"/phone/"+id}/>;
  }
  return <main className="tour-library"><Link href={back}>← Back to floors</Link>
    <p role="status">{error||(!data?"Preparing your 3D walkthrough…":"Florp could not find enough walls for this floor.")}</p>
    {error?<button onClick={()=>location.reload()}>Retry</button>:data&&<Link href={"/plan/"+id}>Open plan editor</Link>}</main>;
}
