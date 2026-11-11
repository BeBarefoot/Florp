"use client";
import {useEffect, useState, useRef} from 'react';
import {request} from '../../lib/api';

export type ReviewState = {revision:number;status:'draft'|'reviewed';blockers:string[];elevations:'assumed'|'confirmed'|null;reviewedAt:string|null};
export default function PlanReview({id, revision, dirty}:{id:string;revision:number;dirty:boolean}) {
  const [review,setReview]=useState<ReviewState|null>(null);
  const [checks,setChecks]=useState([false,false,false]);
  const [elevations,setElevations]=useState<'assumed'|'confirmed'>('assumed');
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const path=`/blueprints/${id}/plan/review`;
  const identity=useRef('');
  identity.current=`${path}:${revision}:${dirty}`;
  useEffect(()=>{
    let cancelled=false;
    setReview(null);setChecks([false,false,false]);setError('');
    if(!dirty&&revision)request<ReviewState>(`${path}?revision=${revision}`).then(r=>{if(!cancelled)setReview(r);}).catch(e=>{if(!cancelled)setError(String(e));});
    return()=>{cancelled=true;};
  },[path,revision,dirty]);
  async function record(reopen=false){
    const submittedIdentity=identity.current;
    setBusy(true);setError('');
    try{
      const result=await request<ReviewState>(path,{method:reopen?'DELETE':'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify(reopen?{revision}:{revision,topology:checks[0],openings:checks[1],scale:checks[2],elevations})});
      if(submittedIdentity!==identity.current)return;
      setReview(result);
      setChecks([false,false,false]);
    }catch(e){setError(String(e));}finally{setBusy(false);}
  }
  return <details className="fe-section" aria-label="Architecture review">
    <summary>Architecture review: {!dirty&&review?.status==='reviewed'?'reviewed':'draft'}</summary>
    <p>Review records apply to one saved revision. Calibration and AI images do not verify a plan's accuracy.</p>
    {dirty?<p>Save your changes before recording review.</p>:review?.status==='reviewed'?<>
      <p>Revision {review.revision} reviewed. Elevations {review.elevations}. Any saved edit requires a new review.</p>
      <button disabled={busy} onClick={()=>void record(true)}>Reopen review</button>
    </>:<>
      {!!review?.blockers.length&&<ul>{review.blockers.map(issue=><li key={issue}>{issue}</li>)}</ul>}
      <fieldset disabled={busy||!review||!!review.blockers.length}>
        {['I checked wall connections, room boundaries and intentional open ends.','I checked all doors and windows against the source.','I confirmed the reference distance against a known measurement.'].map((label,i)=><label key={label} style={{display:'block'}}><input type="checkbox" checked={checks[i]} onChange={e=>setChecks(values=>values.map((v,j)=>i===j?e.target.checked:v))}/>{label}</label>)}
        <label>Elevations<select value={elevations} onChange={e=>setElevations(e.target.value as 'assumed'|'confirmed')}><option value="assumed">Wall/opening heights are explicit assumptions</option><option value="confirmed">I confirmed wall/opening heights</option></select></label>
        <button disabled={!checks.every(Boolean)} onClick={()=>void record()}>Record architecture review</button>
      </fieldset>
    </>}
    {error&&<p role="alert">{error}</p>}
  </details>;
}
