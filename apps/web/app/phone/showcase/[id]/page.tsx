"use client";
import dynamic from "next/dynamic";
import Link from "next/link";
import {useParams} from "next/navigation";
import {useEffect,useState} from "react";
import {API,request,type Blueprint} from "../../../../lib/api";
import type {PlanResponse} from "../../../../lib/plan/model";
import type {Job,Saved} from "../../../../lib/plan/scene";
import {metersPerPixel} from "../../../../lib/plan/derive";
import {samplePlan,sampleScene} from "../../../../lib/plan/showcaseSample";

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
    Promise.all([request<PlanResponse>(base+"/plan"),request<Saved>(base+"/scene"),request<Blueprint>(base+"/info")])
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
  if(id==="sample")return <Player plan={samplePlan} scene={sampleScene} title="Courtyard apartment" back="/phone" sample/>;
  const plan=data?.[0].model;
  if(data&&data[2].id===id&&plan&&metersPerPixel(plan)&&(!data[1].planRevision||data[1].planRevision===plan.revision)){
    return <Player plan={plan} scene={data[1].config} renders={renders} title={data[2].filename} back={"/phone/"+id}/>;
  }
  return <main className="tour-library"><Link href={"/phone/"+id}>← Back to floor</Link>
    <p role="status">{error||(!data?"Opening showcase…":"Check the scale and save the scene against the current floor plan before presenting.")}</p>
    {error&&<button onClick={()=>location.reload()}>Retry</button>}</main>;
}
