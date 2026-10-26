'use client';
import {useEffect,useMemo,useState} from 'react';
import dynamic from 'next/dynamic';
import Link from 'next/link';
import {useParams} from 'next/navigation';
import {API,request,Geometry,Layout,Pt,Wall,Opening} from '../../../lib/api';
import {editableEdges,snapPoint,openingPlacement,segmentDistance} from '../../../lib/geometryEditing';
const Viewer=dynamic(()=>import('../../../components/Viewer3D'),{ssr:false});
type Candidate={x1:number;y1:number;x2:number;y2:number;score:number};
type ModelBox={category:string;confidence:number;x1:number;y1:number;x2:number;y2:number};
type ModelDetections={provider:string;output_type:string;image_width:number;image_height:number;boxes:ModelBox[];warning:string};
type DetectorAudit={wall_boxes:number;accepted_wall_boxes:number;below_confidence:number;too_short:number;not_elongated:number;duplicate:number;door_boxes:number;window_boxes:number;diagnostic:string};
type Reconstructed={layout:Layout;detections:ModelDetections;detection_audit?:DetectorAudit};
type ScaleSuggestion={text:string;source:string;confidence:number;dimension_m:number;pixels:number;px_per_meter:number};
type Evidence={automatic_scale?:{px_per_meter:number;confidence:number;evidence_count:number;supporting_labels:string[]}|null;scale_suggestions:ScaleSuggestion[];segments:(Candidate & {source:string})[];candidates:Candidate[];labels:{text:string;bbox:number[];source:string}[];vector_pdf:boolean;ocr_available:boolean};
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
 const [modelDetections,setModelDetections]=useState<ModelDetections|null>(null);
 type EvidenceCandidate={id:string;start:Pt;end:Pt;sources:string[];mask_support:number};
 type UnifiedComparison={
   base_layout_version:number;proposal:Geometry;candidates:EvidenceCandidate[];
   comparison:{mask_lines:number;yolo_wall_boxes:number;accepted_yolo_candidates:number;
     rejected_yolo_candidates:number;fused_walls:number;
     topology:{connected_components:number;dangling_nodes:string[]}};
   detections:ModelDetections|null;segmentation:{provider:string};
   yolo_error:string|null;mask_overlay_png_base64:string;saved:boolean;
 };
 const [unified,setUnified]=useState<UnifiedComparison|null>(null);
 const [showUnifiedWalls,setShowUnifiedWalls]=useState(true);
 const [showComparisonBoxes,setShowComparisonBoxes]=useState(false);
  const [segmentationOverlay,setSegmentationOverlay]=useState<string|null>(null);
 const [showSegmentationOverlay,setShowSegmentationOverlay]=useState(true);
 const [detectorAudit,setDetectorAudit]=useState<DetectorAudit|null>(null);
 type GapProposal={id:string;start:Pt;end:Pt;axis:string;image_support:number};
 const [missingGaps,setMissingGaps]=useState<GapProposal[]>([]);
 const [dismissedGaps,setDismissedGaps]=useState<string[]>([]);
 const [gapMessage,setGapMessage]=useState('');
 const [gapVersion,setGapVersion]=useState<number|null>(null);
  const [topology,setTopology]=useState<{wall_count:number;junction_count:number;disconnected_components:number;dangling_endpoints:number;crossing_pairs:[string,string][];notes:string[]}|null>(null);
 const [showModelDetections,setShowModelDetections]=useState(false),[modelBusy,setModelBusy]=useState(false);
 const [grayscale,setGrayscale]=useState(true),[showRaw,setShowRaw]=useState(false),[showSuggestions,setShowSuggestions]=useState(false);
 const [reviewScope,setReviewScope]=useState<'all'|'near'>('all');
 const [reviewLabels,setReviewLabels]=useState<Record<string,string>>({}),[selectedCandidate,setSelectedCandidate]=useState<Candidate|null>(null);
 const [selectedWall,setSelectedWall]=useState<string|null>(null);
 const [selectedDetection,setSelectedDetection]=useState<number|null>(null);
 const [rejectedDetections,setRejectedDetections]=useState<string[]>([]);
 const [mode,setMode]=useState<'edit'|'wall'|'door'|'window'>('edit'),[wallStart,setWallStart]=useState<Pt|null>(null);
 const [prompt,setPrompt]=useState('A sunlit Scandinavian living room with natural oak floors and green velvet furniture');
 useEffect(()=>{
  request<Layout>(`/blueprints/${id}/layout`).then(l=>{setLayout(l);setGeometry(l.geometry)}).catch(e=>setStatus(String(e)));
  request<Evidence>(`/blueprints/${id}/evidence`).then(setEvidence).catch(e=>setStatus('Evidence unavailable: '+String(e)));
  request<{candidate_key:string;label:string}[]>(`/blueprints/${id}/wall-annotations`).then(a=>setReviewLabels(Object.fromEntries(a.map(x=>[x.candidate_key,x.label])))).catch(()=>{});
 },[id]);
 const edges=useMemo(()=>geometry?editableEdges(geometry):[],[geometry]);
 const suggestions=useMemo(()=>{
  if(!geometry||!evidence)return [];
  // Conservative UI review: ignore sheet margins and very short strokes.
  const minLength=Math.max(65,Math.min(geometry.width_px,geometry.height_px)*.23);
  const margin=Math.max(14,Math.min(geometry.width_px,geometry.height_px)*.03);
  if(reviewScope==='all')return evidence.candidates;
  return evidence.candidates.filter(s=>{
   if(s.score<.59 || Math.hypot(s.x2-s.x1,s.y2-s.y1)<minLength)return false;
   const p={x:(s.x1+s.x2)/2,y:(s.y1+s.y2)/2};
   return geometry.rooms.some(r=>nearPolygon(p,r.points,margin));
  });
 },[evidence,geometry,reviewScope]);
 async function runPretrained(){
   if(geometry?.walls.some(w=>w.id.startsWith('user-'))&&!window.confirm('Generate a new model-based draft? Previously saved versions remain in the database.'))return;
   setModelBusy(true);setStatus('');
   try{
     const result=await request<Reconstructed>(`/blueprints/${id}/pretrained-reconstruct`,{method:'POST'});
     setModelDetections(result.detections);setDetectorAudit(result.detection_audit||null);setShowModelDetections(true);setSegmentationOverlay(null);setUnified(null);
     setLayout(result.layout);setGeometry(result.layout.geometry);setSelectedDetection(null);setRejectedDetections([]);
     setStatus('Pretrained model generated '+result.layout.geometry.walls.length+' draft walls, '+result.layout.geometry.rooms.length+' proposed enclosed rooms and '+result.layout.geometry.openings.length+' provisional openings. Review all results before confirming.');
   }catch(err){setStatus(String(err))}
   finally{setModelBusy(false)}
 }
 async function compareUnified(){
   if(!layout||!geometry)return;
   if(geometry!==layout.geometry){
     setStatus('Save or discard your unsaved corrections before comparison; no edits will be overwritten.');
     return;
   }
   setModelBusy(true);setStatus('');
   try{
     const result=await request<UnifiedComparison>(`/blueprints/${id}/compare-extraction`,{method:'POST'});
     setUnified(result);setShowUnifiedWalls(true);setShowComparisonBoxes(false);
     setSegmentationOverlay('data:image/png;base64,'+result.mask_overlay_png_base64);
     setShowSegmentationOverlay(true);
     setStatus('Comparison ready — no layout was saved or replaced. Review the proposed walls before applying.');
   }catch(err){setStatus(String(err))}
   finally{setModelBusy(false)}
 }
 function applyUnified(){
   if(!unified||!layout||!geometry)return;
   if(layout.version!==unified.base_layout_version){
     setStatus('Saved layout changed since comparison. Run comparison again.');return;
   }
   if(geometry!==layout.geometry){
     setStatus('Unsaved edits exist. Save them or compare again before applying.');return;
   }
   if(!window.confirm('Load the fused wall proposal into your UNSAVED editor draft? This does not approve its geometry. Previous saved version remains unchanged.'))return;
   setGeometry(unified.proposal);setSelectedWall(null);
   setStatus('Fused proposal loaded locally. Review and correct walls, then Save draft. No previous version was overwritten.');
 }
 async function trySegmentation(){
   if(!window.confirm('Run experimental local wall segmentation? This creates a new draft and may replace all unreviewed wall proposals. Existing saved versions remain available.'))return;
   setModelBusy(true);setStatus('');
   try{
     const result=await request<{layout:Layout;mask_overlay_png_base64:string;report:{provider:string;checkpoint:string;line_count:number;raw_mask_line_count:number;normalized_mask_line_count:number;coverage_fraction:number}}>(
       `/blueprints/${id}/segmentation/propose`,{method:'POST'});
     setLayout(result.layout);setGeometry(result.layout.geometry);
     setSegmentationOverlay('data:image/png;base64,'+result.mask_overlay_png_base64);
     setShowSegmentationOverlay(true);
     setModelDetections(null);setDetectorAudit(null);setUnified(null);setSelectedDetection(null);setSelectedWall(null);
     setStatus(result.report.provider+' segmentation: '+result.report.raw_mask_line_count+' detected axes → '+result.report.normalized_mask_line_count+
       ' consolidated wall runs. Check the mask against the 3D solids; geometry and openings are unverified.');
   }catch(err){setStatus(String(err))}
   finally{setModelBusy(false)}
 }
 async function proposeRooms(){
   if(!window.confirm('Create a new unverified connected-wall/room proposal from the last saved draft? Existing versions will be preserved.'))return;
   setBusy(true);setStatus('');
   try{
     const result=await request<{layout:Layout;topology:{notes:string[]}}>(`/blueprints/${id}/topology/propose`,{method:'POST'});
     setLayout(result.layout);setGeometry(result.layout.geometry);
     setSelectedWall(null);
     setStatus('Graph solver proposed '+result.layout.geometry.rooms.length+
       ' enclosed room(s). Open boundaries remain without floors. Review corners and walls before confirming.');
   }catch(error){setStatus(String(error))}
   finally{setBusy(false)}
 }
 async function findMissingWalls(){
   if(!geometry||!layout)return;
   if(geometry!==layout.geometry){
     setGapMessage('Save your edited walls before searching for gaps, so results match the current layout.');
     return;
   }
   setBusy(true);setGapMessage('');
   try{
     const result=await request<{layout_version:number;suggestions:GapProposal[];warning:string}>(`/blueprints/${id}/missing-wall-suggestions`);
     setMissingGaps(result.suggestions);setDismissedGaps([]);setGapVersion(result.layout_version);
     setGapMessage(result.suggestions.length+' source-supported wall candidates; none are added automatically.');
   }catch(error){setGapMessage(String(error))}
   finally{setBusy(false)}
 }
 function acceptGap(gap:GapProposal){
   setGeometry(old=>{
     if(!old)return old;
     if(old.walls.some(w=>(dist(w.start,gap.start)<5&&dist(w.end,gap.end)<5)||
                       (dist(w.start,gap.end)<5&&dist(w.end,gap.start)<5)))return old;
     const wall:Wall={id:'user-gap-'+crypto.randomUUID(),start:gap.start,end:gap.end,
       thickness_m:.15,height_m:2.8,inferred:true};
     return {...old,structure_reviewed:false,walls:[...old.walls,wall]};
   });
   setMissingGaps(old=>old.filter(item=>item.id!==gap.id));
   setGapMessage('Connection added to unsaved draft. Check alignment, then Save draft.');
 }
  async function inspectTopology(){
   try{
     const result=await request<{wall_count:number;junction_count:number;disconnected_components:number;dangling_endpoints:number;crossing_pairs:[string,string][];notes:string[]}>(`/blueprints/${id}/topology`);
     setTopology(result);
     setStatus('Topology audit read from last saved layout. Save draft first to include current edits.');
   }catch(e){setStatus(String(e))}
 }
 async function extract(){setBusy(true);setStatus('');try{
  const l=await request<Layout>(`/blueprints/${id}/extract`,{method:'POST'});
  setLayout(l);setGeometry(l.geometry);setStatus('AI proposal loaded. Review and calibrate all geometry before verifying.');
 }catch(e){setStatus(String(e))}finally{setBusy(false)}}
 async function save(verified=false,structureReviewed=false){if(!geometry)return;setBusy(true);try{
  const l=await request<Layout>(`/blueprints/${id}/layout`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({geometry,verified,structure_reviewed:structureReviewed})});
  setLayout(l);setGeometry(l.geometry);setStatus(verified?'Metric geometry verified.':structureReviewed?'Wall positions reviewed and saved; measurements are still provisional.':'Draft saved.');
 }catch(e){setStatus(String(e))}finally{setBusy(false)}}
 function updatePoint(ri:number,pi:number,p:Pt){
  setGeometry(old=>{
   if(!old)return old;
   const source=old.rooms[ri]?.points[pi];if(!source)return old;
   const target=snapPoint(p,old,undefined,9);
   // Shared joints and wall endpoints move together; eliminate stale 3D walls.
   const move=(q:Pt)=>dist(q,source)<2?target:q;
   return {...old,rooms:old.rooms.map(r=>({...r,points:r.points.map(move)})),
    walls:old.walls.map(w=>({...w,start:move(w.start),end:move(w.end)}))};
  });
 }
 function moveWallEndpoint(wallId:string,which:'start'|'end',point:Pt){
  setGeometry(current=>{
    if(!current)return current;
    const wall=current.walls.find(w=>w.id===wallId);
    if(!wall)return current;
    const other=which==='start'?wall.end:wall.start;
    const dx=point.x-other.x,dy=point.y-other.y;
    let snapped=snapPoint(point,current,other,9);
    // When nearly horizontal/vertical, preserve axis and existing wall length direction.
    if(Math.abs(dy)<Math.abs(dx)*.12)snapped={...snapped,y:other.y};
    else if(Math.abs(dx)<Math.abs(dy)*.12)snapped={...snapped,x:other.x};
    if(dist(other,snapped)<4)return current;
    return {...current,structure_reviewed:false,
      walls:current.walls.map(w=>w.id===wallId?{...w,[which]:snapped}:w)};
  });
 }
 function addWall(raw:Pt){
  const p=geometry?snapPoint(raw,geometry,wallStart||undefined):raw;
  if(!geometry)return;
  if(!wallStart){setWallStart(p);setStatus('Choose the second endpoint of the new wall.');return;}
  if(dist(wallStart,p)<8){setStatus('Wall too short. Choose a more distant endpoint.');return;}
  const wall:Wall={id:'user-'+crypto.randomUUID(),start:wallStart,end:p,thickness_m:.15,height_m:2.8,inferred:true};
  setGeometry({...geometry,walls:[...geometry.walls,wall]});setWallStart(null);
  setStatus('Draft wall added; save the draft when finished.');
 }
 const candidateKey=(c:Candidate)=>[c.x1,c.y1,c.x2,c.y2].map(v=>v.toFixed(1)).join(':');
 async function labelCandidate(c:Candidate,label:'wall'|'not_wall'|'unsure'){
   try{
     await request(`/blueprints/${id}/wall-annotations`,{method:'POST',headers:{'Content-Type':'application/json'},
       body:JSON.stringify({...c,label})});
     setReviewLabels(old=>({...old,[candidateKey(c)]:label}));
     setStatus('Saved '+label+' label for future detector evaluation/training.');
   }catch(e){setStatus(String(e))}
 }
 async function exportLabels(){
   try{const data=await request(`/blueprints/${id}/training-export`);
     const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'});
     const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='florp-training-'+id+'.json';a.click();URL.revokeObjectURL(url);
   }catch(e){setStatus(String(e))}
 }
 async function acceptSuggestion(c:Candidate){
  if(!window.confirm('Accept this uncertain suggestion as a draft wall?'))return;
  setBusy(true);
  try{const l=await request<Layout>(`/blueprints/${id}/wall-candidates/accept`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(c)});
   setLayout(l);setGeometry(l.geometry);setStatus('Suggestion accepted as a draft wall.');
  }catch(e){setStatus(String(e))}finally{setBusy(false)}
 }
 const sourceId=(i:number)=>'model-box-'+i;
 const openingQueue=modelDetections?.boxes.map((box,index)=>({box,index})).filter(item=>item.box.category==='door'||item.box.category==='window')||[];
 const pendingQueue=openingQueue.filter(({index})=>!rejectedDetections.includes(sourceId(index))&&
   !geometry?.openings.some(o=>o.source_detection_id===sourceId(index)&&o.reviewed));
 const currentQueueIndex=openingQueue.findIndex(item=>item.index===selectedDetection);
 function nextOpening(direction=1){
   if(!openingQueue.length)return;
   const current=currentQueueIndex<0?(direction>0?-1:0):currentQueueIndex;
   const next=(current+direction+openingQueue.length)%openingQueue.length;
   setSelectedDetection(openingQueue[next].index);
   setSelectedWall(null);setMode('edit');
 }
 function nextPending(){
   const after=pendingQueue.find(item=>item.index>(selectedDetection??-1));
   const next=after||pendingQueue[0];
   setSelectedDetection(next?next.index:null);
   setSelectedWall(null);
 }
 const selectedBox=selectedDetection===null?null:modelDetections?.boxes[selectedDetection]||null;
 const selectedSourceId=selectedDetection===null?null:sourceId(selectedDetection);
 const selectedOpening=selectedSourceId?geometry?.openings.find(o=>o.source_detection_id===selectedSourceId):null;
 function approveDetectedOpening(){
  if(!geometry||!selectedBox||selectedDetection===null)return;
  const kind=selectedBox.category;
  if(kind!=='door'&&kind!=='window')return;
  const detectionId=sourceId(selectedDetection);
  if(geometry.openings.some(o=>o.source_detection_id===detectionId)){
   setGeometry(current=>current?{...current,structure_reviewed:false,
      openings:current.openings.map(o=>o.source_detection_id===detectionId?{...o,reviewed:true}:o)}:current);
   setRejectedDetections(current=>current.filter(value=>value!==detectionId));
   setStatus('Opening approved. Continue with Next item; save all edits together.');return;
  }
  const point={x:(selectedBox.x1+selectedBox.x2)/2,y:(selectedBox.y1+selectedBox.y2)/2};
  const ranked=edges.map(edge=>({edge,d:segmentDistance(point,edge)})).sort((a,b)=>a.d-b.d);
  if(!ranked.length||ranked[0].d>Math.max(32,Math.min(geometry.width_px,geometry.height_px)*.1)){
   setStatus('No reliable wall near this detection. Correct the wall first, then approve.');return;
  }
  const choice=ranked.find(item=>item.edge.id.startsWith('model-')&&item.d<=Math.max(20,ranked[0].d+10))||ranked[0];
  const edge=choice.edge;
  const dx=edge.end.x-edge.start.x,dy=edge.end.y-edge.start.y;
  const lengthPx=Math.hypot(dx,dy);
  const ppm=geometry.px_per_meter||60;
  const wallLength=lengthPx/ppm;
  if(wallLength<.2){setStatus('Wall is too short for an opening.');return;}
  const fraction=Math.max(0,Math.min(1,((point.x-edge.start.x)*dx+(point.y-edge.start.y)*dy)/(lengthPx*lengthPx)));
  const width=Math.min(kind==='door'?.9:1.2,wallLength*.6);
  const offset=Math.max(0,Math.min(wallLength-width,fraction*wallLength-width/2));
  const conflicting=geometry.openings.find(o=>o.wall_id===edge.id&&offset<o.offset_m+o.width_m&&o.offset_m<offset+width);
  if(conflicting){
    setStatus('An opening already occupies this wall span. Select and review the existing opening instead of creating a duplicate.');
    return;
  }
  const opening:Opening={
    id:'reviewed-'+crypto.randomUUID(),source_detection_id:detectionId,reviewed:true,
    kind,wall_id:edge.id,offset_m:Number(offset.toFixed(3)),
    width_m:Number(width.toFixed(3)),height_m:kind==='door'?2.1:1.2,
    sill_m:kind==='door'?0:.9,inferred:true
  };
  setGeometry(current=>current?{...current,structure_reviewed:false,openings:[...current.openings,opening]}:current);
  setRejectedDetections(current=>current.filter(value=>value!==detectionId));
  setStatus('Opening added to draft. Continue with Next item; save when finished.');
 }
 function rejectDetectedOpening(){
  if(!selectedSourceId)return;
  if(selectedOpening){
    setGeometry(current=>current?{...current,openings:current.openings.filter(o=>o.source_detection_id!==selectedSourceId)}:current);
  }
  setRejectedDetections(current=>current.includes(selectedSourceId)?current:[...current,selectedSourceId]);
  setStatus('Detection dismissed from this review session. No layout version created.');
 }
 function addOpening(edge:{id:string;start:Pt;end:Pt;thickness_m:number;height_m:number},p:Pt,kind:'door'|'window'){
  if(!geometry||busy)return;
  const dx=edge.end.x-edge.start.x,dy=edge.end.y-edge.start.y,len2=dx*dx+dy*dy;
  if(len2<100){setStatus('Wall segment is too short.');return;}
  const ppm=geometry.px_per_meter||60;
  const length=Math.sqrt(len2)/ppm;
  const fraction=Math.max(0,Math.min(1,((p.x-edge.start.x)*dx+(p.y-edge.start.y)*dy)/len2));
  const width=Math.min(kind==='door'?.9:1.2,length*.6);
  const offset=Math.max(0,Math.min(length-width,fraction*length-width/2));
  if(geometry.openings.some(o=>o.wall_id===edge.id&&offset<o.offset_m+o.width_m&&o.offset_m<offset+width)){
    setStatus('An opening already exists here. Edit that opening in the sidebar.');return;
  }
  const opening:Opening={id:'user-opening-'+crypto.randomUUID(),reviewed:true,kind,wall_id:edge.id,
   offset_m:Number(offset.toFixed(3)),width_m:Number(width.toFixed(3)),
   height_m:kind==='door'?2.1:1.2,sill_m:kind==='door'?0:.9,inferred:true};
  setGeometry(old=>old?{...old,structure_reviewed:false,openings:[...old.openings,opening]}:old);
  setStatus('Opening added to UNSAVED draft. Save to keep your edits.');
 }
 function removeOpening(id:string){if(!geometry)return;setGeometry({...geometry,openings:geometry.openings.filter(o=>o.id!==id)});}
 function changeOpening(id:string,field:'width_m'|'height_m'|'offset_m'|'sill_m',raw:string){
  if(!geometry)return;const value=Number(raw);if(!Number.isFinite(value)||value<0)return;
  setGeometry({...geometry,openings:geometry.openings.map(o=>o.id===id?{...o,[field]:value,inferred:true}:o)});
 }
 function removeWall(id:string){if(!geometry)return;setSelectedWall(null);setGeometry({...geometry,structure_reviewed:false,walls:geometry.walls.filter(w=>w.id!==id),openings:geometry.openings.filter(o=>o.wall_id!==id)});setStatus('Draft wall removed. Save to persist changes.')}
 return <div className="app"><aside><h2>✦ Florp</h2><Link href="/">← Projects</Link>
 <hr style={{borderColor:'#354053',margin:'22px 0'}}/><p>Saved layout v{layout?.version??'–'} · {layout?.verified?'Verified':'Unverified'}</p>
 {geometry&&layout&&<p className="notice">{geometry===layout.geometry?'All changes saved':'● Unsaved edits — Save draft when ready'}</p>}
 <div className="stack"><button disabled={busy} onClick={extract}>Run real AI extraction</button>
 <button className="secondary" disabled={busy} onClick={()=>save(false)}>Save draft</button>
 <button className="secondary" disabled={busy} onClick={()=>save(false,true)}>Confirm wall positions</button>
 <button disabled={busy} onClick={()=>save(true)}>Verify physical dimensions</button></div>
 <p style={{opacity:.7,fontSize:12}}>Confirm wall positions without scale; physical verification requires reliable dimensions. API keys remain server-side.</p></aside>
 <main><header><div><h1>Geometry studio</h1><p className="muted">2D and 3D display the same draft walls.</p></div>
 <div className="row"><button className={view==='2d'?'':'secondary'} onClick={()=>setView('2d')}>2D editor</button>
 <button className={view==='3d'?'':'secondary'} onClick={()=>setView('3d')}>3D shell</button></div></header>
 {status&&<p className="notice">{status}</p>}
 {geometry&&<div className="grid" style={{gridTemplateColumns:'minmax(0,2fr) minmax(290px,1fr)'}}>
 <div className="panel"><h2>{view==='2d'?'Floor-plan overlay':'3D shell · same outline'}</h2>
 {view==='2d'&&unified&&<div style={{border:'1px solid #94a3b8',borderRadius:12,padding:12,marginBottom:12,background:'#f1f5f9',color:'#0f172a'}}>
 <strong>Same-image extraction comparison</strong>
 <div className="row" style={{flexWrap:'wrap',marginTop:8}}>
 <span>Yytsi mask axes: {unified.comparison.mask_lines}</span>
 <span>YOLO wall boxes: {unified.comparison.yolo_wall_boxes}</span>
 <span>YOLO supported by mask: {unified.comparison.accepted_yolo_candidates}</span>
 <span>Fused wall proposals: {unified.comparison.fused_walls}</span>
 <span>Disconnected groups: {unified.comparison.topology.connected_components}</span>
 </div>
 {unified.yolo_error&&<small>YOLO unavailable: {unified.yolo_error}. Showing mask-only evidence.</small>}
 <div className="row" style={{flexWrap:'wrap',marginTop:8}}>
 <label><input type="checkbox" checked={showSegmentationOverlay} onChange={e=>setShowSegmentationOverlay(e.target.checked)}/> Yytsi pixels</label>
 <label><input type="checkbox" checked={showUnifiedWalls} onChange={e=>setShowUnifiedWalls(e.target.checked)}/> Fused wall proposals</label>
 <label><input type="checkbox" checked={showComparisonBoxes} onChange={e=>setShowComparisonBoxes(e.target.checked)}/> YOLO boxes</label>
 <button disabled={busy||modelBusy} onClick={applyUnified}>Use fused proposal in draft</button>
 </div>
 <small>Comparison is read-only. Teal pixels = Yytsi; blue lines = proposed fused geometry. None are verified.</small>
 <div><a href={`${API}/blueprints/${id}/training-export`} target="_blank" rel="noreferrer">View corrected wall labels (training JSON)</a></div>
 </div>}
  {view==='2d'&&modelDetections&&<div style={{border:'1px solid #9fc7d5',borderRadius:12,padding:12,marginBottom:12,background:'#f1f9fa',color:'#18364a'}}>
 <div className="row" style={{justifyContent:'space-between',alignItems:'center'}}>
 <strong>Review detected openings · {openingQueue.length-pendingQueue.length}/{openingQueue.length} resolved</strong>
 <button className="secondary" disabled={!pendingQueue.length} onClick={nextPending}>Next item →</button>
 </div>
 {selectedBox&&(selectedBox.category==='door'||selectedBox.category==='window')?
 <div className="stack">
 <small>Item {currentQueueIndex+1} of {openingQueue.length} · {selectedBox.category} · {Math.round(selectedBox.confidence*100)}% model score
  · {selectedOpening?.reviewed?'Approved':selectedOpening?'Proposed':'Needs review'}</small>
 <div className="row">
 <button className="secondary" onClick={()=>nextOpening(-1)}>← Previous</button>
 {!selectedOpening?.reviewed&&<button onClick={()=>{approveDetectedOpening()}}>Approve opening</button>}
 <button className="secondary" onClick={()=>{rejectDetectedOpening()}}>Reject detection</button>
 <button className="secondary" onClick={()=>nextOpening(1)}>Next →</button>
 </div>
 </div>:<small>Choose Next item to inspect the first unresolved door/window. Each selected box is highlighted on the plan.</small>}
 <small>Corrections stay in your current draft. Click Save draft when done.</small>
 </div>}
 {view==='2d'&&<div style={{border:'1px solid #d5dee7',borderRadius:10,padding:12,marginBottom:12}}>
 <div className="row">
 <strong>Missing-wall recovery</strong>
 <button className="secondary" disabled={busy} onClick={()=>void findMissingWalls()}>Recover missing wall candidates</button>
 </div>
 {gapMessage&&<small>{gapMessage}</small>}
 {gapVersion!==null&&layout&&gapVersion!==layout.version&&<small>Suggestions are outdated; scan again.</small>}
 {missingGaps.filter(g=>!dismissedGaps.includes(g.id)).slice(0,8).map(g=>
 <div key={g.id} className="row" style={{justifyContent:'space-between',padding:'6px 0'}}>
 <small>{g.id.startsWith('bottom-')?'Lower exterior run':'Endpoint gap'} · {Math.round(g.image_support*100)}% source-pixel support</small>
 <button className="secondary" onClick={()=>acceptGap(g)}>Add wall</button>
 <button className="secondary" onClick={()=>setDismissedGaps(prev=>[...prev,g.id])}>Dismiss</button>
 </div>)}
 <small>Includes connected gaps and bottom exterior-run proposals. All require visual review before being added to the 3D model.</small>
 </div>}
  {view==='2d'&&selectedWall&&<div style={{border:'2px solid #16a34a',borderRadius:10,padding:12,marginBottom:12,background:'#f0fdf4',color:'#14532d'}}>
 <strong>Selected wall: {selectedWall}</strong>
 <div className="row">
 <button onClick={()=>removeWall(selectedWall)}>Reject false wall</button>
 <button className="secondary" onClick={()=>setSelectedWall(null)}>Keep / deselect</button>
 </div>
 <small>Reject removes this wall from 2D and 3D, along with its attached provisional openings. Save to persist.</small>
 </div>}
 {view==='2d'&&<div className="notice" style={{marginBottom:12}}>
 {mode==='door'||mode==='window'?'Click near a wall to place a provisional opening. No manual scale entry required.':
 mode==='wall'?'Click two points to draw a wall; snapping is enabled.':
 'Select an orange/cyan detection to review it, then choose Add opening or Dismiss. Your wall edits remain untouched.'}
 </div>}
 {view==='2d'&&<div className="row" style={{marginBottom:12}}>
 <button disabled={modelBusy||busy} onClick={()=>void compareUnified()}>
 {modelBusy?'Comparing extraction…':'Compare YOLO + Yytsi (recommended)'}</button>
  <button disabled={modelBusy||busy} onClick={()=>void trySegmentation()}>
 {modelBusy?'Running wall segmentation…':'Reconstruct walls (multi-scale)'}</button>
 {segmentationOverlay&&<label><input type="checkbox" checked={showSegmentationOverlay}
 onChange={e=>setShowSegmentationOverlay(e.target.checked)}/> Show actual wall pixels</label>}
 <details><summary>Alternative: YOLO box-based build</summary>
 <p className="muted">Legacy wall-box reconstruction. It can miss interior walls; use for comparison or door/window detection, not verified architectural geometry.</p>
 <button className="secondary" disabled={modelBusy||busy} onClick={()=>void runPretrained()}>
 {modelBusy?'Running YOLO…':'Auto-build from YOLO boxes'}</button>
 </details>
 {modelDetections&&<label><input type="checkbox" checked={showModelDetections} onChange={e=>setShowModelDetections(e.target.checked)}/> Model boxes ({modelDetections.boxes.length})</label>}
 <label><input type="checkbox" checked={grayscale} onChange={e=>setGrayscale(e.target.checked)}/> Grayscale</label>
 <details><summary>Advanced: diagnostic lines (not used in 3D)</summary>
 <label title="Legacy OpenCV research candidates. Use model wall review above for training."><input type="checkbox" checked={showSuggestions} onChange={e=>setShowSuggestions(e.target.checked)}/> Legacy line hints ({suggestions.length}/{evidence?.candidates.length??0})</label>
 <select value={reviewScope} onChange={e=>setReviewScope(e.target.value as 'all'|'near')} aria-label="Candidate filter">
 <option value="all">All detections</option><option value="near">Near current outline</option></select>
 <label><input type="checkbox" checked={showRaw} onChange={e=>setShowRaw(e.target.checked)}/> Raw lines ({evidence?.segments.length??0})</label></details>
 {(['wall','door','window'] as const).map(tool=><button key={tool} className={mode===tool?'':'secondary'} onClick={()=>{setMode(mode===tool?'edit':tool);setWallStart(null)}}>{tool==='wall'?'Draw wall':tool==='door'?'Add door':'Add window'}</button>)}
 </div>}
 {view==='2d'?<svg className="canvas" viewBox={`0 0 ${geometry.width_px} ${geometry.height_px}`}
 style={{aspectRatio:geometry.width_px/geometry.height_px,touchAction:'none',cursor:mode!=='edit'?'crosshair':'default'}}
 onClick={e=>{const p=localPoint(e.currentTarget,e.clientX,e.clientY);if(!p)return;
 if(mode==='wall'){addWall({x:Math.max(0,Math.min(geometry.width_px,Math.round(p.x))),y:Math.max(0,Math.min(geometry.height_px,Math.round(p.y)))});return;}
 if(mode==='door'||mode==='window'){
  const ranked=edges.map(edge=>({edge,d:segmentDistance(p,edge)})).sort((a,b)=>a.d-b.d);
  const closest=ranked.find(item=>item.edge.id.startsWith('model-')&&item.d<=Math.max(20,ranked[0]?.d+10))||ranked[0];
  if(!closest||closest.d>Math.max(25,Math.min(geometry.width_px,geometry.height_px)*.05)){setStatus('No nearby wall found. Click closer to a wall centerline.');return;}
  addOpening(closest.edge,p,mode);
 }
 }}>
 <image href={`${API}/blueprints/${id}/preview`} width={geometry.width_px} height={geometry.height_px}
 style={{filter:grayscale?'grayscale(1) contrast(1.12) brightness(1.08)':'none'}}/>
 {segmentationOverlay&&showSegmentationOverlay&&<image href={segmentationOverlay}
 width={geometry.width_px} height={geometry.height_px} pointerEvents="none"/>}
 {unified&&showUnifiedWalls&&unified.candidates.map(item=>
 <line key={'fused-'+item.id} x1={item.start.x} y1={item.start.y}
 x2={item.end.x} y2={item.end.y} pointerEvents="none"
 stroke={item.sources.some(source=>source.startsWith('yolo_box:'))?'#1d4ed8':'#0ea5e9'}
 strokeWidth={Math.max(3,geometry.width_px/420)} strokeDasharray="4 2">
 <title>{item.sources.join(' + ')}; mask support {Math.round(item.mask_support*100)}%</title>
 </line>)}
 {unified&&showComparisonBoxes&&unified.detections?.boxes.filter(b=>b.category==='wall').map((b,i)=>
 <rect key={'compare-box-'+i} x={b.x1} y={b.y1} width={b.x2-b.x1} height={b.y2-b.y1}
 fill="none" stroke="#a855f7" strokeWidth="2" strokeDasharray="7 4" pointerEvents="none"/>)}
  {missingGaps.filter(g=>!dismissedGaps.includes(g.id)).map(g=>
 <line key={'gap-'+g.id} x1={g.start.x} y1={g.start.y} x2={g.end.x} y2={g.end.y}
 stroke="#d97706" strokeWidth={Math.max(4,geometry.width_px/260)} strokeDasharray="7 5"
 pointerEvents="none"><title>Unverified missing-wall gap · {Math.round(g.image_support*100)}% ink support</title></line>)}
  {showModelDetections&&modelDetections?.boxes.map((b,i)=>
 <g key={'model-'+i} pointerEvents={b.category==='door'||b.category==='window'?'all':'none'}
 onClick={e=>{if(b.category==='door'||b.category==='window'){e.stopPropagation();setSelectedDetection(i);setMode('edit')}}}
 style={{cursor:b.category==='door'||b.category==='window'?'pointer':'default'}}>
 <rect x={b.x1} y={b.y1} width={b.x2-b.x1} height={b.y2-b.y1}
 stroke={geometry.openings.some(o=>o.source_detection_id===sourceId(i)&&o.reviewed)?'#16a34a':selectedDetection===i?'#22c55e':rejectedDetections.includes(sourceId(i))?'#9ca3af':b.category.includes('wall')?'#8b5cf6':b.category.includes('door')?'#ea580c':b.category.includes('window')?'#0891b2':'#737373'}
 strokeWidth={Math.max(selectedDetection===i?5:2,geometry.width_px/420)} fill={b.category==='door'||b.category==='window'?'rgba(56,189,248,.08)':'none'} strokeDasharray="8 5"/>
 <title>{b.category+' · '+(b.confidence*100).toFixed(1)+'% · '+(geometry.openings.some(o=>o.source_detection_id===sourceId(i)&&o.reviewed)?'reviewed':geometry.openings.some(o=>o.source_detection_id===sourceId(i))?'proposed':'unreviewed')}</title></g>)}
 {showRaw&&evidence?.segments.map((s,i)=><line key={'raw'+i} x1={s.x1} y1={s.y1} x2={s.x2} y2={s.y2} stroke="#d98d26" strokeWidth={Math.max(1,geometry.width_px/700)} opacity={.3} pointerEvents="none"/>)}
 {showSuggestions&&suggestions.map((s,i)=><line key={'candidate'+i} x1={s.x1} y1={s.y1} x2={s.x2} y2={s.y2}
 stroke={reviewLabels[candidateKey(s)]==='not_wall'?'#b91c1c':reviewLabels[candidateKey(s)]==='wall'?'#16a34a':'#2563eb'} strokeWidth={Math.max(3,geometry.width_px/230)} opacity={.82} style={{cursor:'pointer'}}
 pointerEvents={mode==='edit'?'stroke':'none'}
 onClick={e=>{e.stopPropagation();setSelectedCandidate(s)}}/>)}
 {geometry.rooms.map((r,ri)=><g key={r.id}>
 <polygon points={r.points.map(p=>`${p.x},${p.y}`).join(' ')} fill="#46b494" fillOpacity={.08} stroke="#008a70" strokeWidth={Math.max(2,geometry.width_px/400)} pointerEvents="none"/>
 {mode==='edit'&&r.points.map((p,pi)=><circle key={pi} cx={p.x} cy={p.y} r={Math.max(5,geometry.width_px/140)} fill="white" stroke="#008a70"
 strokeWidth={Math.max(2,geometry.width_px/650)} style={{cursor:'grab'}} onPointerDown={e=>{e.stopPropagation();e.currentTarget.setPointerCapture(e.pointerId)}}
 onPointerMove={e=>{if(!e.currentTarget.hasPointerCapture(e.pointerId))return;const svg=e.currentTarget.ownerSVGElement;if(!svg)return;const point=localPoint(svg,e.clientX,e.clientY);if(point)updatePoint(ri,pi,point)}}
 onPointerUp={e=>e.currentTarget.releasePointerCapture(e.pointerId)} />)}
 </g>)}
 {edges.map(e=><line key={'edge-'+e.id} x1={e.start.x} y1={e.start.y} x2={e.end.x} y2={e.end.y}
 stroke="transparent" strokeWidth={Math.max(18,geometry.width_px/75)} style={{cursor:mode==='door'||mode==='window'?'crosshair':'inherit'}}
 pointerEvents="none"
 onClick={event=>{if(mode!=='door'&&mode!=='window')return;event.stopPropagation();const svg=event.currentTarget.ownerSVGElement;if(!svg)return;const p=localPoint(svg,event.clientX,event.clientY);if(p)addOpening(e,p,mode)}}/>)}
 {geometry.openings.map(o=>{const e=edges.find(e=>e.id===o.wall_id);if(!e)return null;
  const scale=geometry.px_per_meter||60,len=dist(e.start,e.end),t=o.offset_m*scale/len,u=(o.offset_m+o.width_m)*scale/len;
  const x1=e.start.x+(e.end.x-e.start.x)*t,y1=e.start.y+(e.end.y-e.start.y)*t,x2=e.start.x+(e.end.x-e.start.x)*u,y2=e.start.y+(e.end.y-e.start.y)*u;
  return <line key={o.id} x1={x1} y1={y1} x2={x2} y2={y2} stroke={o.kind==='door'?'#f97316':'#0284c7'} strokeDasharray={o.kind==='door'?'10 6':undefined} strokeWidth={Math.max(7,geometry.width_px/160)} pointerEvents="none"/>;
 })}
 {geometry.walls.filter(w=>w.id.startsWith('user-')||w.id.startsWith('model-')).map(w=><line key={w.id} x1={w.start.x} y1={w.start.y} x2={w.end.x} y2={w.end.y} stroke={selectedWall===w.id?"#16a34a":w.id.startsWith("model-")?"#0284c7":"#d97706"}
 strokeWidth={Math.max(selectedWall===w.id?5:3,geometry.width_px/220)}
 pointerEvents={mode==='edit'?'stroke':'none'} style={{cursor:mode==='edit'?'pointer':'default'}}
 onClick={e=>{if(mode==='edit'){e.stopPropagation();setSelectedWall(w.id)}}}/>)}
 {mode==='edit'&&geometry.walls.filter(w=>w.id===selectedWall).flatMap(w=>(
  (['start','end'] as const).map(which=>{
   const p=w[which];
   return <circle key={w.id+which} cx={p.x} cy={p.y} r={Math.max(7,geometry.width_px/130)}
    fill="white" stroke="#16a34a" strokeWidth={3} style={{cursor:'grab',touchAction:'none'}}
    onPointerDown={e=>{e.stopPropagation();e.currentTarget.setPointerCapture(e.pointerId)}}
    onPointerMove={e=>{
      if(!e.currentTarget.hasPointerCapture(e.pointerId))return;
      const svg=e.currentTarget.ownerSVGElement;
      if(!svg)return;
      const point=localPoint(svg,e.clientX,e.clientY);
      if(point)moveWallEndpoint(w.id,which,point);
    }}
    onPointerUp={e=>{if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId)}}
    onClick={e=>e.stopPropagation()}/>;
  })
 ))}
 {wallStart&&<circle cx={wallStart.x} cy={wallStart.y} r={Math.max(5,geometry.width_px/130)} fill="#d97706" pointerEvents="none"/>}
 </svg>:<Viewer geometry={geometry}/>}
 <p className="muted">{mode==='wall'?'Click two points to add a missing wall.':mode==='door'||mode==='window'?'Click near a wall or on a detected opening box to add or correct it.':'Review model walls and detected openings; tap a wall to adjust or reject it.'}</p></div>
 <div className="stack"><div className="panel stack"><h2>Geometry</h2>
 <details><summary>Advanced scale override (optional)</summary><label>Pixels per meter <input type="number" min=".001" step=".1" value={geometry.px_per_meter??''}
 onChange={e=>setGeometry({...geometry,px_per_meter:e.target.value?Number(e.target.value):null,scale_source:'user_confirmed'})} placeholder="Use confirmed dimension"/></label></details>
 <span className="pill">{geometry.rooms.length} rooms · {geometry.walls.length} stored walls</span>
 {geometry.walls.some(w=>w.id.startsWith('model-'))&&<div className="notice">Model geometry is active. Blue centerlines in 2D correspond to 3D walls. Any enclosed rooms/floors are unverified geometry proposals; wall and opening positions remain provisional.</div>}
 <small>Detected {evidence?.segments.length??0} raw strokes · {evidence?.candidates.length??0} unfiltered possible walls · {suggestions.length} shown after local filtering</small>
 <small>Review automatically reconstructed walls. Click a cyan/orange detection box to propose or update a window/door; drag wall endpoints only where necessary.</small>
 <details><summary>Detection details</summary><h2>Pretrained object detection</h2>
 <small>Purple dashed boxes: walls. Orange: doors. Cyan: windows. Gray: other classes. Boxes do NOT provide exact wall endpoints or opening locations.</small>
 {modelDetections?<div className="stack">
 <strong>{modelDetections.provider}: {modelDetections.boxes.length} detected objects</strong>
 {Object.entries(modelDetections.boxes.reduce<Record<string,number>>((count,b)=>({...count,[b.category]:(count[b.category]||0)+1}),{})).map(([name,count])=><small key={name}>{name}: {count}</small>)}
 <small>{modelDetections.warning}</small></div>:
 <small>Click Run pretrained model above after installing the optional local checkpoint. No API token required.</small>}
 {detectorAudit&&<div className="stack"><h2>Where detected walls were lost</h2>
 <small>YOLO wall boxes: {detectorAudit.wall_boxes} · used for 3D: {detectorAudit.accepted_wall_boxes}</small>
 <small>Rejected: short {detectorAudit.too_short}, non-elongated {detectorAudit.not_elongated}, low-confidence {detectorAudit.below_confidence}, duplicates {detectorAudit.duplicate}</small>
 <small>YOLO door boxes: {detectorAudit.door_boxes}; window boxes: {detectorAudit.window_boxes}. These may not attach to a wall.</small>
 <small>{detectorAudit.diagnostic}</small></div>}
 </details>
 <details><summary>Advanced: experimental line-candidate labeling</summary>
 <h2>Legacy OpenCV line review</h2>
 <small>Blue: unreviewed · green: wall · red: not wall. All candidates are heuristic, not a trained segmentation model.</small>
 {selectedCandidate&&<div className="stack" style={{border:'1px solid #ccd5e0',padding:9,borderRadius:8}}>
 <strong>Selected detected segment</strong><small>score {selectedCandidate.score.toFixed(2)} (not calibrated)</small>
 <div className="row"><button onClick={()=>void labelCandidate(selectedCandidate,'wall')}>Wall ✓</button>
 <button className="secondary" onClick={()=>void labelCandidate(selectedCandidate,'not_wall')}>Not wall ×</button>
 <button className="secondary" onClick={()=>void labelCandidate(selectedCandidate,'unsure')}>Unsure</button>
 <button className="secondary" onClick={()=>void acceptSuggestion(selectedCandidate)}>Accept as draft</button></div>
 </div>}
 <button className="secondary" onClick={()=>void exportLabels()}>Export training annotations (JSON)</button>
 </details>
 <h2>Dimension evidence</h2>
 {geometry.px_per_meter?<p><small>Scale set: {geometry.px_per_meter.toFixed(2)} px/m — confirm against plan dimensioning.</small></p>:
 <p className="notice">No confirmed scale yet. Openings can be drafted, but their physical widths need confirmation.</p>}
 {evidence?.automatic_scale&&<div className="notice">Auto-estimated scale from {evidence.automatic_scale.evidence_count} matching dimensions: {Math.round(evidence.automatic_scale.px_per_meter)} px/m (provisional). <button className="secondary" onClick={()=>setGeometry({...geometry,px_per_meter:evidence.automatic_scale!.px_per_meter,scale_source:'user_confirmed'})}>Confirm scale</button></div>}
 {(evidence?.scale_suggestions||[]).length===0&&<small>No confidently paired OCR dimensions. Check PDF quality or confirm a labeled dimension later.</small>}
 {(evidence?.scale_suggestions||[]).map((s,i)=><div key={i} className="row">
 <small>{s.text} cm? alongside {Math.round(s.pixels)} px → {Math.round(s.px_per_meter)} px/m (low confidence)</small>
 <button className="secondary" onClick={()=>{if(!geometry)return;
   setGeometry({...geometry,px_per_meter:s.px_per_meter,scale_source:'user_confirmed',warnings:geometry.warnings.filter(w=>!w.toLowerCase().includes('provisional'))});
   setStatus('Scale hypothesis selected. Confirm that '+s.text+' is centimeters and refers to the highlighted plan dimension.');}}>Use estimate</button></div>)}
 <h2>Wall graph health</h2>
 <button className="secondary" disabled={busy} onClick={()=>void proposeRooms()}>Propose connected rooms</button>
 <button className="secondary" onClick={()=>void inspectTopology()}>Inspect saved wall connections</button>
 {topology&&<div className="stack">
 <small>{topology.wall_count} walls · {topology.junction_count} joined endpoints · {topology.disconnected_components} groups · {topology.dangling_endpoints} loose ends · {topology.crossing_pairs.length} crossings</small>
 {topology.notes.map((note,i)=><div className="notice" key={i}>{note}</div>)}
 </div>}
 <h2>Wall corrections</h2>
 {selectedWall?<div className="stack">
 <small>Selected {selectedWall}: drag the green endpoint handles in the plan. Changes appear in 3D.</small>
 <button className="secondary" onClick={()=>removeWall(selectedWall)}>Reject / delete selected wall</button>
 <button className="secondary" onClick={()=>setSelectedWall(null)}>Finish correction</button>
 </div>:<small>Click a blue model wall line to edit or remove it; drag its endpoint handles. This corrects the reconstructed geometry, not the original YOLO box.</small>}
 <small>Use Confirm wall positions after reviewing the proposed structure; physical measurements are a separate step.</small>
 <h2>Opening review</h2>
 <span className="pill">{geometry.openings.filter(o=>o.source_detection_id&&o.reviewed).length} reviewed · {geometry.openings.filter(o=>o.source_detection_id&&!o.reviewed).length} awaiting review · {geometry.openings.length} total in draft</span>
 {selectedBox&&(selectedBox.category==='door'||selectedBox.category==='window')&&
 <div className="stack" style={{border:'2px solid #16a34a',borderRadius:10,padding:12}}>
 <strong>Selected {selectedBox.category} detection</strong>
 <small>{Math.round(selectedBox.confidence*100)}% model confidence · {selectedOpening?.reviewed?'Reviewed ✓':selectedOpening?'Proposed — approval needed':selectedSourceId&&rejectedDetections.includes(selectedSourceId)?'Dismissed':'Needs review'}</small>
 <div className="row">
 {!selectedOpening?.reviewed&&<button disabled={busy} onClick={approveDetectedOpening}>{selectedOpening?'Approve detected opening':'Add proposed '+selectedBox.category}</button>}
 {selectedOpening?.reviewed&&<span className="pill">Reviewed ✓ — save pending edits</span>}
 <button className="secondary" onClick={rejectDetectedOpening}>Dismiss</button>
 <button className="secondary" onClick={()=>setSelectedDetection(null)}>Close</button>
 </div>
 <small>Clicks only select. Approving changes the local draft; no new layout version until you save.</small>
 </div>}

 {modelDetections&&<small>Model found {modelDetections.boxes.filter(b=>b.category==='door').length} door boxes and {modelDetections.boxes.filter(b=>b.category==='window').length} window boxes. Toggle Model boxes to see orange/cyan detections and click one to propose or update the nearest wall opening. Not every detection can be safely attached.</small>}
 {geometry.openings.map(o=><div className="stack" key={o.id} style={{padding:10,border:'1px solid #dce2e8',borderRadius:8}}>
 <div className="row"><strong>{o.kind} · {o.wall_id.slice(0,25)}</strong><button className="secondary" onClick={()=>removeOpening(o.id)}>Remove</button></div>
 {(['offset_m','width_m','height_m','sill_m'] as const).map(k=><label key={k}>{k.replace('_m','')} (m) <input type="number" min="0" step=".05" value={o[k]} onChange={e=>changeOpening(o.id,k,e.target.value)}/></label>)}
 <div className="row"><small>{o.inferred?'Provisional opening — dimensions not confirmed':'Opening dimensions confirmed by user'}</small>
 {o.inferred&&<button className="secondary" onClick={()=>{
   setGeometry({...geometry,openings:geometry.openings.map(item=>item.id===o.id?{...item,inferred:false}:item)});
   setStatus('Opening dimensions marked confirmed. Save the draft or verify physical dimensions.');
 }}>Confirm dimensions</button>}</div>
 </div>)}
 {geometry.walls.filter(w=>w.id.startsWith('user-')||w.id.startsWith('model-')).map(w=><div className="row" key={w.id}><small>{w.id.slice(0,18)}</small><button className="secondary" onClick={()=>removeWall(w.id)}>Remove</button></div>)}
 {geometry.warnings.map((w,i)=><div className="notice" key={i}>{w}</div>)}
 </div><div className="panel stack"><h2>Design assistant · upcoming</h2>
 <textarea rows={4} value={prompt} onChange={e=>setPrompt(e.target.value)}/>
 <button disabled title="Depth-conditioned generation is not integrated">Generate render (next milestone)</button>
 <p className="muted">No simulated AI output is produced.</p></div></div></div>}
 </main></div>;
}
