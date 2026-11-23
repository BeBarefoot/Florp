"use client";
import {useEffect,useState} from "react";
import Link from "next/link";
import {useRouter} from "next/navigation";
import {ArrowUpRight, Box, Plus} from "lucide-react";
import {request,type Project} from "../../lib/api";

export default function PhoneLibrary(){
  const router=useRouter();
  const [spaces,setSpaces]=useState<Project[]|null>(null);
  const [creating,setCreating]=useState(false),[busy,setBusy]=useState(false);
  const [name,setName]=useState(""),[error,setError]=useState("");
  async function load(){
    setError("");
    try{setSpaces(await request<Project[]>("/projects"));}catch(e){setError(String(e));}
  }
  useEffect(()=>{void load();},[]);
  async function create(e:React.FormEvent){
    e.preventDefault();
    if(!name.trim()||busy)return;
    setBusy(true);setError("");
    try{
      const space=await request<Project>("/projects",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({title:name.trim()})});
      router.push("/phone/spaces/"+space.id);
    }catch(e){setError(String(e));setBusy(false);}
  }
  return <main className="tour-library">
    <section className="tour-cover"><div>
      <h1>Your walkthroughs</h1>
      <div className="tour-cover-actions"><Link className="tour-primary show-launch" href="/phone/showcase/sample">Explore sample tour <ArrowUpRight size={17}/></Link>
      <button className="show-new" onClick={()=>setCreating(true)}><Plus size={18}/> New space</button></div>
    </div></section>
    {creating&&<form className="tour-create" onSubmit={create}>
      <label>Space name<input autoFocus required value={name} onChange={e=>setName(e.target.value)} placeholder="Garden apartment"/></label>
      <button disabled={busy||!name.trim()}>Create space</button><button type="button" disabled={busy} onClick={()=>setCreating(false)}>Cancel</button>
    </form>}
    {error&&<p role="alert">{error} <button onClick={load}>Retry</button></p>}
    <h2>Your spaces</h2>
    {spaces===null&&!error&&<p>Loading spaces…</p>}
    {spaces?.length===0&&<p>Create a space to upload your first floor plan.</p>}
    <div className="tour-grid">{spaces?.map(space=><Link className="tour-card" href={"/phone/spaces/"+space.id} key={space.id}>
      <span className="tour-glyph"><Box/></span><strong>{space.title}</strong><ArrowUpRight size={19}/>
    </Link>)}</div>
  </main>;
}
