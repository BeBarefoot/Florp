'use client';
import {useEffect,useMemo,useState} from 'react';
import dynamic from 'next/dynamic';
import Link from 'next/link';
import {useParams} from 'next/navigation';
import {API,request,Geometry,Layout,Pt,Wall} from '../../../lib/api';
const Viewer=dynamic(()=>import('../../../components/Viewer3D'),{ssr:false});
type Candidate={x1:number;y1:number;x2:number;y2:number;score:number};
type Evidence={segments:(Candidate & {source:string})[];candidates:Candidate[];labels:{text:string;bbox:number[];source:string}[];vector_pdf:boolean;ocr_available:boolean};
const dist=(a:Pt,b:Pt)=>Math.hypot(a.x-b.x,a.y-b.y);
function inside(p:Pt,poly:Pt[]):boolean{
 let result=false;
 for(let i=0,j=poly.length-1;i<poly.length;j=i++){
  const a=poly[i],b=poly[j];
  if(((a.y>p.y)!==(b.y>p.y))&&(p.x<(b.x-a.x)*(p.y-a.y)/(b.y-a.y)+a.x))result=!result;
 }
 return result;
}
function nearPolygon(p:Pt,poly:Pt[],margin:number):boolean{
 if(inside(p,poly))return true;
 for(let i=0;i<poly.length;i++){
  const a=poly[i],b=poly[(i+1)%poly.length];
  const dx=b.x-a.x,dy=b.y-a.y,d=dx*dx+dy*dy;
  const t=d?Math.max(0,Math.min(1,((p.x-a.x)*dx+(p.y-a.y)*dy)/d)):0;
  if(Math.hypot(p.x-a.x-t*dx,p.y-a.y-t*dy)<=margin)return true;
 }
 return false;
}
function localPoint(svg:SVGSVGElement,clientX:number,clientY:number):Pt|null{
 const p=svg.createSVGPoint();p.x=clientX;p.y=clientY;
 const m=svg.getScreenCTM()?.inverse();return m?p.matrixTransform(m):null;
}
export default function Editor(){
 const {id}=useParams<{id:string}>();
 const [layout,setLayout]=useState<Layout|null>(null),[geometry,setGeometry]=useState<Geometry|null>(null);
 const [evidence,setEvidence]=useState<Evidence|null>(null);
 const [status,setStatus]=useState(''),[busy,setBusy]=useState(false);
 const [view,setView]=useState<'2d'|'3d'>('2d');
 const [grayscale,setGrayscale]=useState(true),[showRaw,setShowRaw]=useState(false),[showSuggestions,setShowSuggestions]=useState(false);
 const [mode,setMode]=useState<'edit'|'wall'>('edit'),[wallStart,setWallStart]=useState<Pt|null>(null);
 const [prompt,setPrompt]=useState('A sunlit Scandinavian living room with natural oak floors and green velvet furniture');
 useEffect(()=>{
  request<Layout>(`/blueprints/${id}/layout`).then(l=>{setLayout(l);setGeometry(l.geometry)}).catch(e=>setStatus(String(e)));
  request<Evidence>(`/blueprints/${id}/evidence`).then(setEvidence).catch(e=>setStatus('Evidence unavailable: '+String(e)));
 },[id]);
 const suggestions=useMemo(()=>{
  if(!geometry||!evidence)return [];
  // Conservative UI review: ignore sheet margins and very short strokes.
  const minLength=Math.max(65,Math.min(geometry.width_px,geometry.height_px)*.23);
  const margin=Math.max(14,Math.min(geometry.width_px,geometry.height_px)*.03);
  return evidence.candidates.filter(s=>{
   if(s.score<.59 || Math.hypot(s.x2-s.x1,s.y2-s.y1)<minLength)return false;
   const p={x:(s.x1+s.x2)/2,y:(s.y1+s.y2)/2};
   return geometry.rooms.some(r=>nearPolygon(p,r.points,margin));
  });
 },[evidence,geometry]);
 async function extract(){setBusy(true);setStatus('');try{
  const l=await request<Layout>(`/blueprints/${id}/extract`,{method:'POST'});
  setLayout(l);setGeometry(l.geometry);setStatus('AI proposal loaded. Review and calibrate all geometry before verifying.');
 }catch(e){setStatus(String(e))}finally{setBusy(false)}}
 async function save(verified=false){if(!geometry)return;setBusy(true);try{
  const l=await request<Layout>(`/blueprints/${id}/layout`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({geometry,verified})});
  setLayout(l);setGeometry(l.geometry);setStatus(verified?'Layout verified and saved.':'Draft layout saved.');
 }catch(e){setStatus(String(e))}finally{setBusy(false)}}
 function updatePoint(ri:number,pi:number,p:Pt){
  setGeometry(old=>{
   if(!old)return old;
   const source=old.rooms[ri]?.points[pi];if(!source)return old;
   const target={x:Math.round(Math.max(0,Math.min(old.width_px,p.x))),y:Math.round(Math.max(0,Math.min(old.height_px,p.y)))};
   // Shared joints and wall endpoints move together; eliminate stale 3D walls.
   const move=(q:Pt)=>dist(q,source)<2?target:q;
   return {...old,rooms:old.rooms.map(r=>({...r,points:r.points.map(move)})),
    walls:old.walls.map(w=>({...w,start:move(w.start),end:move(w.end)}))};
  });
 }
 function addWall(p:Pt){
  if(!geometry)return;
  if(!wallStart){setWallStart(p);setStatus('Choose the second endpoint of the new wall.');return;}
  if(dist(wallStart,p)<8){setStatus('Wall too short. Choose a more distant endpoint.');return;}
  const wall:Wall={id:'user-'+crypto.randomUUID(),start:wallStart,end:p,thickness_m:.15,height_m:2.8,inferred:true};
  setGeometry({...geometry,walls:[...geometry.walls,wall]});setWallStart(null);
  setStatus('Draft wall added; save the draft when finished.');
 }
 async function acceptSuggestion(c:Candidate){
  if(!window.confirm('Accept this uncertain suggestion as a draft wall?'))return;
  setBusy(true);
  try{const l=await request<Layout>(`/blueprints/${id}/wall-candidates/accept`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(c)});
   setLayout(l);setGeometry(l.geometry);setStatus('Suggestion accepted as a draft wall.');
  }catch(e){setStatus(String(e))}finally{setBusy(false)}
 }
 function removeWall(id:string){if(!geometry)return;setGeometry({...geometry,walls:geometry.walls.filter(w=>w.id!==id),openings:geometry.openings.filter(o=>o.wall_id!==id)});setStatus('Draft wall removed. Save to persist changes.')}
 return <div className="app"><aside><h2>✦ Florp</h2><Link href="/">← Projects</Link>
 <hr style={{borderColor:'#354053',margin:'22px 0'}}/><p>Layout v{layout?.version??'–'} · {layout?.verified?'Verified':'Unverified'}</p>
 <div className="stack"><button disabled={busy} onClick={extract}>Run real AI extraction</button>
 <button className="secondary" disabled={busy} onClick={()=>save(false)}>Save draft</button>
 <button disabled={busy} onClick={()=>save(true)}>Verify geometry</button></div>
 <p style={{opacity:.7,fontSize:12}}>Structural geometry must be reviewed. API keys remain server-side.</p></aside>
 <main><header><div><h1>Geometry studio</h1><p className="muted">The 2D outline now drives the 3D shell.</p></div>
 <div className="row"><button className={view==='2d'?'':'secondary'} onClick={()=>setView('2d')}>2D editor</button>
 <button className={view==='3d'?'':'secondary'} onClick={()=>setView('3d')}>3D shell</button></div></header>
 {status&&<p className="notice">{status}</p>}
 {geometry&&<div className="grid" style={{gridTemplateColumns:'minmax(0,2fr) minmax(290px,1fr)'}}>
 <div className="panel"><h2>{view==='2d'?'Floor-plan overlay':'3D shell · same outline'}</h2>
 {view==='2d'&&<div className="row" style={{marginBottom:12}}>
 <label><input type="checkbox" checked={grayscale} onChange={e=>setGrayscale(e.target.checked)}/> Grayscale</label>
 <label><input type="checkbox" checked={showSuggestions} onChange={e=>setShowSuggestions(e.target.checked)}/> Experimental suggestions ({suggestions.length})</label>
 <label><input type="checkbox" checked={showRaw} onChange={e=>setShowRaw(e.target.checked)}/> Raw lines ({evidence?.segments.length??0})</label>
 <button className={mode==='wall'?'':'secondary'} onClick={()=>{setMode(mode==='wall'?'edit':'wall');setWallStart(null)}}>{mode==='wall'?'Finish wall drawing':'Draw interior wall'}</button>
 </div>}
 {view==='2d'?<svg className="canvas" viewBox={`0 0 ${geometry.width_px} ${geometry.height_px}`}
 style={{aspectRatio:geometry.width_px/geometry.height_px,touchAction:'none',cursor:mode==='wall'?'crosshair':'default'}}
 onClick={e=>{if(mode!=='wall')return;const p=localPoint(e.currentTarget,e.clientX,e.clientY);if(p)addWall({x:Math.max(0,Math.min(geometry.width_px,Math.round(p.x))),y:Math.max(0,Math.min(geometry.height_px,Math.round(p.y)))})}}>
 <image href={`${API}/blueprints/${id}/preview`} width={geometry.width_px} height={geometry.height_px}
 style={{filter:grayscale?'grayscale(1) contrast(1.12) brightness(1.08)':'none'}}/>
 {showRaw&&evidence?.segments.map((s,i)=><line key={'raw'+i} x1={s.x1} y1={s.y1} x2={s.x2} y2={s.y2} stroke="#d98d26" strokeWidth={Math.max(1,geometry.width_px/700)} opacity={.3} pointerEvents="none"/>)}
 {showSuggestions&&suggestions.map((s,i)=><line key={'candidate'+i} x1={s.x1} y1={s.y1} x2={s.x2} y2={s.y2}
 stroke="#2563eb" strokeWidth={Math.max(3,geometry.width_px/230)} opacity={.82} style={{cursor:'pointer'}}
 onClick={e=>{e.stopPropagation();if(!busy)void acceptSuggestion(s)}}/>)}
 {geometry.rooms.map((r,ri)=><g key={r.id}>
 <polygon points={r.points.map(p=>`${p.x},${p.y}`).join(' ')} fill="#46b494" fillOpacity={.08} stroke="#008a70" strokeWidth={Math.max(2,geometry.width_px/400)} pointerEvents="none"/>
 {mode==='edit'&&r.points.map((p,pi)=><circle key={pi} cx={p.x} cy={p.y} r={Math.max(5,geometry.width_px/140)} fill="white" stroke="#008a70"
 strokeWidth={Math.max(2,geometry.width_px/650)} style={{cursor:'grab'}} onPointerDown={e=>{e.stopPropagation();e.currentTarget.setPointerCapture(e.pointerId)}}
 onPointerMove={e=>{if(!e.currentTarget.hasPointerCapture(e.pointerId))return;const svg=e.currentTarget.ownerSVGElement;if(!svg)return;const point=localPoint(svg,e.clientX,e.clientY);if(point)updatePoint(ri,pi,point)}}
 onPointerUp={e=>e.currentTarget.releasePointerCapture(e.pointerId)} />)}
 </g>)}
 {geometry.walls.filter(w=>w.id.startsWith('user-')).map(w=><line key={w.id} x1={w.start.x} y1={w.start.y} x2={w.end.x} y2={w.end.y} stroke="#d97706" strokeWidth={Math.max(3,geometry.width_px/260)} pointerEvents="none"/>)}
 {wallStart&&<circle cx={wallStart.x} cy={wallStart.y} r={Math.max(5,geometry.width_px/130)} fill="#d97706" pointerEvents="none"/>}
 </svg>:<Viewer geometry={geometry}/>}
 <p className="muted">{mode==='wall'?'Click two points on the blueprint to add a draft interior wall.':'Drag room vertices; connected endpoints and the 3D shell move with them.'} Suggestions are experimental and hidden by default.</p></div>
 <div className="stack"><div className="panel stack"><h2>Geometry</h2>
 <label>Pixels per meter <input type="number" min=".001" step=".1" value={geometry.px_per_meter??''}
 onChange={e=>setGeometry({...geometry,px_per_meter:e.target.value?Number(e.target.value):null})} placeholder="Set from reliable dimension"/></label>
 <span className="pill">{geometry.rooms.length} rooms · {geometry.walls.length} stored walls</span>
 <small>Detected {evidence?.segments.length??0} raw strokes · {evidence?.candidates.length??0} unfiltered possible walls · {suggestions.length} shown after local filtering</small>
 <small>3D: polygon-derived boundary + independent interior walls. Unverified and inferred dimensions are provisional.</small>
 {geometry.walls.filter(w=>w.id.startsWith('user-')).map(w=><div className="row" key={w.id}><small>{w.id.slice(0,18)}</small><button className="secondary" onClick={()=>removeWall(w.id)}>Remove</button></div>)}
 {geometry.warnings.map((w,i)=><div className="notice" key={i}>{w}</div>)}
 </div><div className="panel stack"><h2>Design assistant · upcoming</h2>
 <textarea rows={4} value={prompt} onChange={e=>setPrompt(e.target.value)}/>
 <button disabled title="Depth-conditioned generation is not integrated">Generate render (next milestone)</button>
 <p className="muted">No simulated AI output is produced.</p></div></div></div>}
 </main></div>;
}
