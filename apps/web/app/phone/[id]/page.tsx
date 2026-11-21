"use client";
import {useEffect,useState} from "react";
import {useParams} from "next/navigation";
import dynamic from "next/dynamic";
import Link from "next/link";
import {request,type Blueprint} from "../../../lib/api";
import {metersPerPixel} from "../../../lib/plan/derive";
import type {PlanResponse} from "../../../lib/plan/model";

const Studio=dynamic(()=>import("../../../components/plan/Plan3D"),{ssr:false});
export default function PhonePlan(){
  const {id}=useParams<{id:string}>();
  const [plan,setPlan]=useState<PlanResponse|null>(null);
  const [info,setInfo]=useState<Blueprint|null>(null);
  const [error,setError]=useState("");
  useEffect(()=>{
    let current=true;
    Promise.all([request<PlanResponse>(`/blueprints/${id}/plan`),request<Blueprint>(`/blueprints/${id}/info`)])
      .then(([p,b])=>{if(current){setPlan(p);setInfo(b);}})
      .catch(e=>{if(current)setError(String(e));});
    return ()=>{current=false;};
  },[id]);
  return <main className="phone-studio">
    <nav><Link href={info?"/project/"+info.project_id:"/phone"}>← Floors</Link>
      <Link href={"/plan/"+id}>Review plan</Link></nav>
    <h1>{info?.filename||"Walkthrough"}</h1>
    {error?<p role="alert">{error} <button onClick={()=>location.reload()}>Retry</button></p>:
      !plan?<p>Opening plan…</p>:plan.model&&metersPerPixel(plan.model)?
      <Studio key={id} model={plan.model} phone/>:
      <p>Open Review plan to extract the floor plan and set a known measurement. Save it, then open the phone walkthrough.</p>}
  </main>;
}
