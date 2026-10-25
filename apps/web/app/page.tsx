'use client';
import {useEffect,useState} from 'react';
import Link from 'next/link';
import {request,Project} from '../lib/api';
export default function Home(){const [projects,setProjects]=useState<Project[]>([]);const [title,setTitle]=useState('');const [error,setError]=useState('');const [health,setHealth]=useState('Checking API…');
 async function load(){try{setProjects(await request('/projects'));const h=await request<{ok:boolean}>('/health');setHealth(h.ok?'Local API connected':'API not ready')}catch(e){setHealth('Backend not connected');setError(String(e))}}
 useEffect(()=>{void load()},[]);
 async function removeProject(project:Project){
  if(!window.confirm('Delete "'+project.title+'" and all its blueprints, layouts and render records? This cannot be undone.'))return;
  try{
   await request('/projects/'+project.id,{method:'DELETE'});
   setProjects(current=>current.filter(item=>item.id!==project.id));
   setError('');
  }catch(e){setError(String(e))}
 }
 async function create(){try{const p=await request<Project>('/projects',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title})});setProjects([p,...projects]);setTitle('');setError('')}catch(e){setError(String(e))}}
 return <div className="app"><aside><h2>✦ Florp</h2><p style={{opacity:.7}}>From blueprint to possibility.</p><hr style={{borderColor:'#354053'}}/><p>Projects</p><small>{health}</small></aside><main><header><div><h1>Your spaces</h1><p className="muted">Turn floor plans into verified, editable spaces.</p></div><span className="pill">Developer preview</span></header><div className="panel" style={{marginBottom:20}}><h2>Create a project</h2><div className="row"><input placeholder="e.g. Garden apartment" value={title} onChange={e=>setTitle(e.target.value)} onKeyDown={e=>e.key==='Enter'&&create()}/><button onClick={create}>Create project</button></div></div>{error&&<p className="notice">{error}</p>}<div className="grid">{projects.map(p=><div key={p.id} className="panel"><Link href={'/project/'+p.id}><h2>{p.title} →</h2><p className="muted">Open workspace</p></Link><button className="secondary" onClick={()=>void removeProject(p)}>Delete project</button></div>)}</div>{!projects.length&&<div className="notice">Start by creating a project. The backend runs locally, and no AI calls are made until explicitly requested.</div>}</main></div>}
