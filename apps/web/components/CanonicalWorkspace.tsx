'use client';
import {useEffect,useState} from 'react';
import dynamic from 'next/dynamic';
import ReconstructionReview from './ReconstructionReview';
import {API,request,Geometry,Pt} from '../lib/api';
const Viewer=dynamic(()=>import('./Viewer3D'),{ssr:false});
type Graph={width_px:number;height_px:number;nodes:{id:string;point:Pt}[];walls:{id:string;start_node_id:string;end_node_id:string}[];rooms:{id:string;verified:boolean}[];pending_openings:unknown[]};
export type Revision={id:string;version:number;parent_revision_id:string|null;graph:Graph};
export default function CanonicalWorkspace({bid,layoutVersion,hasUnsavedChanges,onUseDraft}:{bid:string;layoutVersion:number;hasUnsavedChanges:boolean;onUseDraft:(g:Geometry)=>void}){
 const [revision,setRevision]=useState<Revision|null>(null),[stale,setStale]=useState(false);
 const [busy,setBusy]=useState(false),[message,setMessage]=useState(''),[selected,setSelected]=useState<string|null>(null);
 const [projection,setProjection]=useState<Geometry|null>(null),[view,setView]=useState<'2d'|'3d'>('2d');
 const [x,setX]=useState(''),[y,setY]=useState('');
 async function load(){
  setBusy(true);setProjection(null);
  try{const r=await request<{revision:Revision;stale:boolean}>(`/blueprints/${bid}/canonical-plan/revisions/latest`);setRevision(r.revision);setStale(r.stale);setMessage('');}
  catch(e){setRevision(null);setMessage(String(e).startsWith('Error: 404:')?'Initialize a graph from the saved layout to begin.':String(e));}
  finally{setBusy(false);}
 }
 useEffect(()=>{void load();},[bid,layoutVersion]);
 useEffect(()=>{
  let active=true;setProjection(null);setSelected(null);
  if(revision)request<{geometry:Geometry}>(`/blueprints/${bid}/canonical-plan/revisions/${revision.id}/geometry`).then(r=>{if(active)setProjection(r.geometry)}).catch(e=>{if(active)setMessage(String(e))});
  return()=>{active=false};
 },[bid,revision]);
 async function mutate(path:string,body:unknown){
  setBusy(true);setMessage('');
  try{const r=await request<Revision>(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});setRevision(r);setStale(false);}
  catch(e){setMessage(String(e));if(String(e).includes('409:'))setStale(true);}
  finally{setBusy(false);}
 }
 async function useInDraft(){
  if(!revision||hasUnsavedChanges)return;
  setBusy(true);setMessage('');
  try{
   const result=await request<{geometry:Geometry}>(`/blueprints/${bid}/canonical-plan/revisions/${revision.id}/draft`,{method:'POST'});
   onUseDraft(result.geometry);
   setMessage('Graph loaded into the main 2D/3D draft. Save the corrected draft to keep it.');
  }catch(e){setMessage(String(e));if(String(e).includes('409:'))setStale(true);}
  finally{setBusy(false);}
 }
 const base=`/blueprints/${bid}/canonical-plan/revisions`;
 const nodes=new Map(revision?.graph.nodes.map(n=>[n.id,n.point]));
 const disabled=busy||stale;
 return <details className="card"><summary>Repair connected geometry</summary>
  <p>Repair walls as connected geometry, then use the result in the main 2D/3D draft. Existing saved versions remain available. Proposed room faces are not verified floors.</p>
  <div className="toolbar">
   <button disabled={busy} onClick={()=>void load()}>Reload graph</button>
   {(!revision||stale)&&<button disabled={busy} onClick={()=>void mutate(base,{expected_layout_version:layoutVersion})}>Initialize from saved layout v{layoutVersion}</button>}
   {revision&&<><span>Revision {revision.version} · {revision.graph.walls.length} walls · {revision.graph.rooms.length} proposed faces · {revision.graph.pending_openings.length} pending openings</span>
    <button disabled={disabled||!revision.parent_revision_id} onClick={()=>void mutate(`${base}/${revision.id}/restore`,{target_revision_id:revision.parent_revision_id})}>Undo last revision</button>
    <button disabled={disabled||hasUnsavedChanges||!projection} onClick={()=>void useInDraft()}>Use repaired graph in main 2D/3D draft</button>
    <button disabled={!projection} onClick={()=>setView(view==='2d'?'3d':'2d')}>{view==='2d'?'Preview graph in 3D':'Show graph in 2D'}</button></>}
  </div>
  {hasUnsavedChanges&&<p>Save your main draft edits before importing repaired geometry.</p>}
  {stale&&<p role="alert">Saved layout changed. Reinitialize before editing this graph.</p>}
  {message&&<p role="status">{message}</p>}
  {revision&&view==='2d'&&<>
   <p>Select a junction, then enter its source-image coordinates. Every incident wall moves together.</p>
   <svg aria-label="Canonical wall graph" viewBox={`0 0 ${revision.graph.width_px} ${revision.graph.height_px}`} style={{width:'100%',maxHeight:600,background:'#eef2f6'}}>
    <image href={`${API}/blueprints/${bid}/preview`} width={revision.graph.width_px} height={revision.graph.height_px} opacity={.45}/>
    {(projection?.walls||revision.graph.walls.map(w=>({id:w.id,start:nodes.get(w.start_node_id)!,end:nodes.get(w.end_node_id)!}))).map(w=><line key={w.id} x1={w.start.x} y1={w.start.y} x2={w.end.x} y2={w.end.y} stroke="#126d9a" strokeWidth={3}/>)}
    {revision.graph.nodes.map(n=><circle key={n.id} cx={n.point.x} cy={n.point.y} r={selected===n.id?6:4} fill={selected===n.id?'#e76c24':'#126d9a'} tabIndex={0} role="button" aria-label={`Select junction ${n.id}`} onClick={()=>{setSelected(n.id);setX(String(n.point.x));setY(String(n.point.y));}} onKeyDown={e=>{if(e.key==='Enter'){setSelected(n.id);setX(String(n.point.x));setY(String(n.point.y));}}}/>)}
   </svg>
   {selected&&<form onSubmit={e=>{e.preventDefault();void mutate(`${base}/${revision.id}/operations`,{kind:'move_junction',node_id:selected,point:{x:Number(x),y:Number(y)}})}}>
    <label>X <input type="number" step="any" required value={x} onChange={e=>setX(e.target.value)}/></label>
    <label>Y <input type="number" step="any" required value={y} onChange={e=>setY(e.target.value)}/></label>
    <button disabled={disabled}>Save junction move</button>
   </form>}
  </>}
  {revision&&view==='3d'&&projection&&<Viewer geometry={projection}/>}
  {revision&&<ReconstructionReview bid={bid} revision={revision} disabled={disabled} onAccepted={setRevision}/>}
 </details>;
}
