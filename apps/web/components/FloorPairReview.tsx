"use client";
import {useEffect,useState} from "react";
import {SiteOutline} from "./SiteOutline";
import Link from "next/link";
import {API,Blueprint,request} from "../lib/api";

type Point=[number,number];
type Kind="stairs"|"garden";
type Region={kind:Kind; points:Point[]; holes?:Point[][]};
type Regions=Record<string,Region[]>;
type Pair={first:string;second:string;regions:Regions};
type Suggestion={first:string|null;reason:string;regions:Regions};

function FloorMap({plan,level,regions,change}:{plan:Blueprint;level:string;regions:Region[];change:(r:Region[])=>void}){
  const [kind,setKind]=useState<Kind|null>(null);
  const [points,setPoints]=useState<Point[]>([]);
  function end(){setKind(null);setPoints([]);}
  return <section><h3>{level} · {plan.filename}</h3>
    <svg aria-label={level+" region map"} viewBox="0 0 1 1" preserveAspectRatio="none"
      style={{width:"100%",aspectRatio:plan.width+"/"+plan.height,background:"#eee",cursor:kind?"crosshair":"default"}}
      onClick={e=>{
        if(!kind || points.length>=256)return;
        const rect=e.currentTarget.getBoundingClientRect();
        setPoints([...points,[(e.clientX-rect.left)/rect.width,(e.clientY-rect.top)/rect.height]]);
      }}>
      <image href={API+"/blueprints/"+plan.id+"/preview"} width="1" height="1" preserveAspectRatio="none"/>
      {regions.map((region,i)=><SiteOutline key={i} region={region}/>)}
      <polyline points={points.map(p=>p.join(",")).join(" ")} fill="none" stroke="#c31548" strokeWidth="3" vectorEffect="non-scaling-stroke"/>
    </svg>
    {regions.map((r,i)=><button key={i} onClick={()=>change(regions.filter((_,j)=>j!==i))}>Remove {r.kind} {i+1}</button>)}
    {kind?<><p>Click around the {kind} on the drawing.</p><button disabled={points.length<3} onClick={()=>{change([...regions,{kind,points}]);end();}}>Finish outline</button> <button onClick={end}>Cancel outline</button></>:
    <>{(["garden","stairs"] as const).map(k=><button key={k} onClick={()=>setKind(k)}>Outline {k}</button>)}</>}
    <p><Link href={"/plan/"+plan.id}>Open {level.toLowerCase()} editor →</Link></p>
  </section>;
}

export default function FloorPairReview({pid,plans}:{pid:string;plans:Blueprint[]}){
  const [saved,setSaved]=useState<Pair|null>(null);
  const [pair,setPair]=useState<Pair|null>(null);
  const [a,setA]=useState(""),[b,setB]=useState("");
  const [busy,setBusy]=useState(true),[message,setMessage]=useState("");
  const path="/projects/"+pid+"/floor-pair";
  useEffect(()=>{
    let active=true;
    request<Pair|null>(path).then(v=>{if(active){setPair(v);setSaved(v);}}).catch(e=>{if(active)setMessage(String(e));}).finally(()=>{if(active)setBusy(false);});
    return ()=>{active=false;};
  },[path]);
  const left=a||plans[0].id,right=b||plans[1].id;
  async function review(){
    setBusy(true);
    try {
      const s=await request<Suggestion>(path+"/suggestions?a="+encodeURIComponent(left)+"&b="+encodeURIComponent(right));
      setPair({first:s.first??"",second:s.first===left?right:left,regions:s.regions});
      setMessage(s.reason);
    }catch(e){setMessage(String(e));}finally{setBusy(false);}
  }
  async function save(){
    setBusy(true);
    try{const v=await request<Pair>(path,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(pair)});
      setSaved(v);setMessage("Floor pair saved.");}catch(e){setMessage(String(e));}finally{setBusy(false);}
  }
  return <fieldset className="panel stack" disabled={busy}><legend>Two-floor review</legend>
    {["Drawing A","Drawing B"].map((label,i)=><label key={label}>{label} <select value={i?right:left} onChange={e=>i?setB(e.target.value):setA(e.target.value)}>
      {plans.map(p=><option key={p.id} value={p.id}>{p.filename}</option>)}</select></label>)}
    <button disabled={left===right} onClick={review}>Identify floors, garden and stairs</button>
    {message&&<p role="status">{message}</p>}
    {pair&&<>
      <label>First floor (garden level) <select value={pair.first} onChange={e=>setPair({...pair,first:e.target.value,second:Object.keys(pair.regions).find(k=>k!==e.target.value)!})}>
        {!pair.first&&<option value="">Choose first floor</option>}
        {plans.filter(p=>p.id===pair.first||p.id===pair.second||p.id in pair.regions).map(p=><option key={p.id} value={p.id}>{p.filename}</option>)}</select></label>
      <p>Green marks lawn, tan marks paving, and orange marks stair footprints. Review both drawings, then save.</p>
      {(pair.first?[pair.first,pair.second]:Object.keys(pair.regions)).map((id,i)=>{
        const plan=plans.find(p=>p.id===id);
        return plan&&<FloorMap key={id} plan={plan} level={pair.first?(i?"Second floor":"First floor"):"Unassigned drawing"} regions={pair.regions[id]??[]}
          change={r=>setPair({...pair,regions:{...pair.regions,[id]:r}})}/>;
      })}
      <button disabled={!pair.first||pair===saved} onClick={save}>Save floor pair</button>
    </>}
  </fieldset>;
}
