"use client";
import {useEffect,useRef,useState} from "react";
import Link from "next/link";
import {useParams} from "next/navigation";
import {ArrowLeft,ArrowUpRight,Camera,Upload} from "lucide-react";
import {API,request,type Blueprint,type Project} from "../../../../lib/api";

export default function PhoneSpace(){
  const {id}=useParams<{id:string}>();
  const [plans,setPlans]=useState<Blueprint[]|null>(null),[title,setTitle]=useState("Space");
  const [error,setError]=useState(""),[uploading,setUploading]=useState("");
  const lock=useRef(false);
  useEffect(()=>{
    let live=true;
    Promise.all([request<Project[]>("/projects"),request<Blueprint[]>("/projects/"+id+"/blueprints")])
      .then(([spaces,items])=>{if(live){setPlans(items);setTitle(spaces.find(s=>s.id===id)?.title||"Space");}})
      .catch(e=>{if(live)setError(String(e));});
    return ()=>{live=false;};
  },[id]);
  async function upload(input:HTMLInputElement){
    const files=Array.from(input.files??[]);input.value="";
    if(lock.current||!files.length)return;
    lock.current=true;setError("");
    try{
      for(const file of files){
        setUploading(file.name);
        const data=new FormData();data.append("file",file);
        const plan=await request<Blueprint>("/projects/"+id+"/blueprints",{method:"POST",body:data});
        setPlans(previous=>[plan,...(previous??[])]);
      }
    }catch(e){setError(String(e));}finally{lock.current=false;setUploading("");}
  }
  return <main className="tour-library">
    <Link className="tour-back" href="/phone"><ArrowLeft size={18}/> Your spaces</Link>
    <h1>{title}</h1><h2>Floor plans</h2>
    <div className="tour-upload">
      <label className="tour-primary"><Upload size={18}/> Upload plans<input disabled={!!uploading||!plans} type="file" multiple accept="application/pdf,image/png,image/jpeg,image/webp" onChange={e=>void upload(e.currentTarget)}/></label>
      <label><Camera size={18}/> Take photo<input disabled={!!uploading||!plans} type="file" accept="image/*" capture="environment" onChange={e=>void upload(e.currentTarget)}/></label>
    </div>
    {uploading&&<p role="status">Uploading {uploading}…</p>}
    {error&&<p role="alert">{error} <button onClick={()=>location.reload()}>Reload</button></p>}
    {!plans&&!error&&<p>Opening space…</p>}
    {plans?.length===0&&<p>Add a drawing or photograph to start your walkthrough.</p>}
    <div className="tour-grid">{plans?.map(p=><Link className="tour-floor" key={p.id} href={"/phone/"+p.id}>
      <img src={API+"/blueprints/"+p.id+"/preview"} alt=""/><span><strong>{p.filename}</strong><ArrowUpRight size={18}/></span>
    </Link>)}</div>
    {!!plans&&plans.length>=2&&<Link className="tour-back" href={"/project/"+id}>Review floor pairing <ArrowUpRight size={16}/></Link>}
  </main>;
}
