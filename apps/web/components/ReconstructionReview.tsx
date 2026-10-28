'use client';
import {useEffect,useState} from 'react';
import {API,request,Pt} from '../lib/api';
import type {Revision} from './CanonicalWorkspace';
type Stats={components:number;dangling:number;faces:number;walls:number};
type Proposal={preview_token:string;source_sha256:string;parameters:{max_gap_px:number;min_support:number};before:Stats;after:Stats;warning:string;rejected:Record<string,number>;recommended_ids:string[];candidates:{id:string;kind:string;points:Pt[];raster_support:number;recommended:boolean;reason:string}[]};
export default function ReconstructionReview({bid,revision,disabled,onAccepted}:{bid:string;revision:Revision;disabled:boolean;onAccepted:(r:Revision)=>void}){
 const [proposal,setProposal]=useState<Proposal|null>(null),[selected,setSelected]=useState<string[]>([]);
 const [busy,setBusy]=useState(false),[message,setMessage]=useState('');
 useEffect(()=>{setProposal(null);setSelected([]);setMessage('');},[revision.id]);
 const base=`/blueprints/${bid}/canonical-plan/revisions/${revision.id}/reconstruction`;
 async function preview(){
  setBusy(true);setMessage('');setProposal(null);setSelected([]);
  try{const p=await request<Proposal>(`${base}/preview`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({})});setProposal(p);}
  catch(e){setMessage(String(e));}finally{setBusy(false);}
 }
 async function accept(){
  if(!proposal)return;setBusy(true);setMessage('');
  try{const r=await request<Revision>(`${base}/accept`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...proposal.parameters,preview_token:proposal.preview_token,candidate_ids:selected})});onAccepted(r);setProposal(null);}
  catch(e){setMessage(String(e));}finally{setBusy(false);}
 }
 const nodes=new Map(revision.graph.nodes.map(n=>[n.id,n.point]));
 return <section><h3>Reconstruct missing connections</h3>
  <p>Find source-supported continuations and corners across the graph. Review the orange lines against the plan before accepting.</p>
  <button disabled={disabled||busy} onClick={()=>void preview()}>{busy?'Working…':'Preview reconstruction'}</button>
  {message&&<p role="alert">{message}</p>}
  {proposal&&<>
   <p>{proposal.warning}</p>
   <p>Current: {proposal.before.components} components, {proposal.before.dangling} loose ends, {proposal.before.faces} faces. Recommended set: {proposal.after.components} components, {proposal.after.dangling} loose ends, {proposal.after.faces} faces.</p>
   <svg aria-label="Reconstruction proposal overlay" viewBox={`0 0 ${revision.graph.width_px} ${revision.graph.height_px}`} style={{width:'100%',maxHeight:600,background:'#eef2f6'}}>
    <image href={`${API}/blueprints/${bid}/preview`} width={revision.graph.width_px} height={revision.graph.height_px} opacity={.65}/>
    {revision.graph.walls.map(w=><line key={w.id} x1={nodes.get(w.start_node_id)!.x} y1={nodes.get(w.start_node_id)!.y} x2={nodes.get(w.end_node_id)!.x} y2={nodes.get(w.end_node_id)!.y} stroke="#126d9a" strokeWidth={2}/>)}
    {proposal.candidates.map((c,i)=><g key={c.id}><polyline points={c.points.map(p=>`${p.x},${p.y}`).join(' ')} fill="none" stroke={selected.includes(c.id)?'#d44c09':'#a36c24'} strokeWidth={selected.includes(c.id)?5:3} strokeDasharray="5 3"/><text x={c.points[0].x+5} y={c.points[0].y-5} fill="#a33a00" fontSize={12}>{i+1}</text></g>)}
   </svg>
   {proposal.candidates.map((c,i)=><label key={c.id} style={{display:'block'}}><input type="checkbox" disabled={disabled||busy} checked={selected.includes(c.id)} onChange={e=>setSelected(e.target.checked?[...selected,c.id]:selected.filter(id=>id!==c.id))}/>{i+1}. {c.kind} · {Math.round(c.raster_support*100)}% raster support · {c.reason}</label>)}
   {proposal.candidates.length===0&&<p>No supported repairs found. Remaining gaps need manual review.</p>}
   {Object.entries(proposal.rejected).map(([reason,count])=><p key={reason}>{reason.replaceAll('_',' ')}: {count}</p>)}
   <button disabled={disabled||busy||!selected.length} onClick={()=>void accept()}>Accept {selected.length} selected repairs as a new revision</button>
  </>}
 </section>;
}
