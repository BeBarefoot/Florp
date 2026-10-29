'use client';
import {useEffect,useMemo,useState} from 'react';
import {useDraftHistory} from '../../../lib/draftHistory';
import dynamic from 'next/dynamic';
import Link from 'next/link';
import CanonicalWorkspace from '../../../components/CanonicalWorkspace';
import {SpatialOverlay,SpatialInspector,SpatialQuality,LooseEndpoint} from '../../../components/SpatialReview';
import {useParams} from 'next/navigation';
import {API,request,Geometry,Layout,Pt,Wall,Opening} from '../../../lib/api';
import {editableEdges,snapPoint,openingPlacement,segmentDistance,moveSharedJunction} from '../../../lib/geometryEditing';
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
 const [layout,setLayout]=useState<Layout|null>(null);
 const history=useDraftHistory();
 const {geometry,setGeometry,resetGeometry}=history;
 const [evidence,setEvidence]=useState<Evidence|null>(null);
 const [status,setStatus]=useState(''),[busy,setBusy]=useState(false);
 const [qualityError,setQualityError]=useState('');
 const [quality,setQuality]=useState<SpatialQuality|null>(null);
 useEffect(()=>{setQuality(null);setQualityError('');if(!geometry)return;let active=true;const timer=setTimeout(()=>{request<any>(`/blueprints/${id}/quality`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({geometry})}).then(r=>{if(active&&Array.isArray(r.structural_issues))setQuality(r)}).catch(error=>{if(active)setQualityError(String(error))});},300);return()=>{active=false;clearTimeout(timer)};},[id,geometry]);
 const [spatialReview,setSpatialReview]=useState(true);
 const [selectedRoom,setSelectedRoom]=useState<string|null>(null);
 const [gapIndex,setGapIndex]=useState(-1);
 const [view,setView]=useState<'2d'|'3d'>('2d');
 const [modelDetections,setModelDetections]=useState<ModelDetections|null>(null);
 type OpeningHint={candidate_id:string;kind:'door'|'window';x1:number;y1:number;x2:number;y2:number;source_confidence:number;wall_id:string|null;fraction:number|null;reason:string};
 type EvidenceCandidate={id:string;start:Pt;end:Pt;sources:string[];mask_support:number;category:'agreed'|'yolo_only'|'yytsi_only';review_priority:number;yolo_confidence?:number|null};
 type UnifiedComparison={
   base_layout_version:number;proposal:Geometry;candidates:EvidenceCandidate[];opening_hints:OpeningHint[];
   geometry_review:{auto_applied:boolean;explanation:string;suggestions:{
     candidate_id:string;reason:string;category:string;priority:number;mask_support:number;
     connects_to_structure:boolean;start:Pt;end:Pt}[]};
   input_manifest:{source_preview_sha256:string;[key:string]:unknown};
   comparison:{mask_lines:number;yolo_wall_boxes:number;accepted_yolo_candidates:number;
     rejected_yolo_candidates:number;fused_walls:number;
     yolo_only_candidates:number;yytsi_only_candidates:number;agreed_candidates:number;
     topology:{disconnected_components:number;dangling_endpoints:number}};
   detections:ModelDetections|null;segmentation:{provider:string};
   yolo_error:string|null;mask_overlay_png_base64:string;saved:boolean;
 };
 const [unified,setUnified]=useState<UnifiedComparison|null>(null);
 type EvaluationRecord={id:string;provider:string;status:string;metrics?:{walls:{precision:number;recall:number;f1:number};openings:{f1:number};room_area_iou:number|null;relative_scale_error:number|null};correction_seconds:number|null;notes:string;created_at:string};
 const [evaluations,setEvaluations]=useState<EvaluationRecord[]>([]);
 const [activeEvaluation,setActiveEvaluation]=useState<string|null>(null);
 const [evaluationBusy,setEvaluationBusy]=useState(false);
 const [correctionMinutes,setCorrectionMinutes]=useState('');
 const [evaluationNotes,setEvaluationNotes]=useState('');
 const [reviewAttested,setReviewAttested]=useState(false);
 const [evaluationError,setEvaluationError]=useState('');

 type Raster2SeqResult={saved:false;image_sha256:string;base_layout_version:number;width_px:number;height_px:number;rooms:{category_id:number;points:[number,number][]}[];opening_symbols:{kind:'door'|'window';points:[number,number][]}[];metadata:{provider:string;checkpoint:string;predicted_rooms:number};note:string};
 const [r2s,setR2s]=useState<Raster2SeqResult|null>(null);
 const [r2sVisible,setR2sVisible]=useState(true);
 const [r2sBusy,setR2sBusy]=useState(false);
 const [r2sStatus,setR2sStatus]=useState('');

 const [reviewType,setReviewType]=useState<'wall'|'opening'>('wall');
 const [reviewFocus,setReviewFocus]=useState(false);
 const [fusionIndex,setFusionIndex]=useState(0);
 const [fusionDecisions,setFusionDecisions]=useState<Record<string,'accept'|'reject'|'unsure'|'door'|'window'>>({});
 const [fusionSaving,setFusionSaving]=useState(false);
 const [openingIndex,setOpeningIndex]=useState(0);
 const [openingDecisions,setOpeningDecisions]=useState<Record<string,'accept'|'reject'|'unsure'>>({});
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
 const [sharedGraph,setSharedGraph]=useState<{layout_version:number;graph:{
 nodes:{id:string;position:Pt;degree:number}[];
 edges:{id:string;source_wall_id:string;start_node_id:string;end_node_id:string}[];
 disconnected_components:number;dangling_nodes:number;intersections:number;warnings:string[]}}|null>(null);
 const [showModelDetections,setShowModelDetections]=useState(false),[modelBusy,setModelBusy]=useState(false);
 const [showLegacyRoomOutline,setShowLegacyRoomOutline]=useState(false);
 const [grayscale,setGrayscale]=useState(true),[showRaw,setShowRaw]=useState(false),[showSuggestions,setShowSuggestions]=useState(false);
 const [reviewScope,setReviewScope]=useState<'all'|'near'>('all');
 const [reviewLabels,setReviewLabels]=useState<Record<string,string>>({}),[selectedCandidate,setSelectedCandidate]=useState<Candidate|null>(null);
 type ConnectivityChange={wall_id:string;endpoint:'start'|'end';original:Pt;proposed:Pt;distance_px:number;reason:string};
 type ConnectivityProposal={geometry:Geometry;changes:ConnectivityChange[];before_components:number;after_components:number;before_dangling:number;after_dangling:number;removed_starter_ids:string[];warning:string;saved:false};
 const [connectivity,setConnectivity]=useState<{source:string;proposal:ConnectivityProposal}|null>(null);
 const [connectivityBusy,setConnectivityBusy]=useState(false);
 const [selectedJunction,setSelectedJunction]=useState<number|null>(null);
 type OpeningMatch={candidate_id:string;kind:'door'|'window';start:Pt;end:Pt;host_wall_id:string|null;fraction:number|null;status:'proposed'|'unresolved';reason:string};
 const [association,setAssociation]=useState<{source:string;items:OpeningMatch[];proposed:number;unresolved:number}|null>(null);
 const [associationBusy,setAssociationBusy]=useState(false);
 const [selectedWall,setSelectedWall]=useState<string|null>(null);
 const [selectedDetection,setSelectedDetection]=useState<number|null>(null);
 const [rejectedDetections,setRejectedDetections]=useState<string[]>([]);
 const [mode,setMode]=useState<'edit'|'wall'|'door'|'window'>('edit'),[wallStart,setWallStart]=useState<Pt|null>(null);
 const [prompt,setPrompt]=useState('A sunlit Scandinavian living room with natural oak floors and green velvet furniture');
 useEffect(()=>{
  request<Layout>(`/blueprints/${id}/layout`).then(l=>{setLayout(l);resetGeometry(l.geometry)}).catch(e=>setStatus(String(e)));
  request<Evidence>(`/blueprints/${id}/evidence`).then(setEvidence).catch(e=>setStatus('Evidence unavailable: '+String(e)));
  request<{candidate_key:string;label:string}[]>(`/blueprints/${id}/wall-annotations`).then(a=>setReviewLabels(Object.fromEntries(a.map(x=>[x.candidate_key,x.label])))).catch(()=>{});
  request<EvaluationRecord[]>(`/blueprints/${id}/evaluations`).then(rows=>{
    setEvaluations(rows);
    setActiveEvaluation(rows.find(r=>r.status==='baseline')?.id||null);
  }).catch(()=>{});
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
     setLayout(result.layout);resetGeometry(result.layout.geometry);setSelectedDetection(null);setRejectedDetections([]);
     setStatus('Pretrained model generated '+result.layout.geometry.walls.length+' draft walls, '+result.layout.geometry.rooms.length+' proposed enclosed rooms and '+result.layout.geometry.openings.length+' provisional openings. Review all results before confirming.');
   }catch(err){setStatus(String(err))}
   finally{setModelBusy(false)}
 }

 async function downloadReviewedGeometry(){
   try{
     const data=await request<unknown>(`/blueprints/${id}/reviewed-geometry-export`);
     const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'});
     const url=URL.createObjectURL(blob);
     const link=document.createElement('a');
     link.href=url;link.download=`florp-reviewed-geometry-${id}.json`;
     link.click();URL.revokeObjectURL(url);
   }catch(error){setStatus('Reviewed dataset export failed: '+String(error))}
 }
 async function downloadEvaluation(recordId:string){
   try{
     const data=await request<unknown>(`/blueprints/${id}/evaluations/${recordId}`);
     const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'});
     const url=URL.createObjectURL(blob);
     const anchor=document.createElement('a');
     anchor.href=url;anchor.download=`florp-evaluation-${recordId}.json`;
     anchor.click();URL.revokeObjectURL(url);
   }catch(err){setEvaluationError('Unable to export evaluation: '+String(err))}
 }
 async function captureBaseline(){
   if(!unified||!layout||!geometry)return;
   if(geometry!==layout.geometry){
     setEvaluationError('Save or discard draft edits before capturing the model baseline.');
     return;
   }
   setEvaluationBusy(true);setEvaluationError('');
   try{
     const result=await request<{id:string;status:string}>(`/blueprints/${id}/evaluations`,{
       method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
       provider:unified.yolo_error?'florp-yytsi':'florp-fusion',image_sha256:unified.input_manifest.source_preview_sha256,
       base_layout_version:unified.base_layout_version,geometry:unified.proposal})});
     setActiveEvaluation(result.id);
     const rows=await request<EvaluationRecord[]>(`/blueprints/${id}/evaluations`);
     setEvaluations(rows);
     setStatus('Model baseline saved independently. Correct walls and openings; then measure accuracy.');
   }catch(err){setEvaluationError(String(err))}
   finally{setEvaluationBusy(false)}
 }
 async function finishEvaluation(){
   if(!geometry||!activeEvaluation)return;
   if(!reviewAttested){setEvaluationError('Review all walls and openings before attesting reference accuracy.');return}
   const minutes=Number(correctionMinutes);
   if(correctionMinutes.trim()===''||!Number.isFinite(minutes)||minutes<0||minutes>1440){
     setEvaluationError('Enter actual correction minutes (0 to 1440).');return;
   }
   setEvaluationBusy(true);setEvaluationError('');
   try{
     const result=await request<{status:string;metrics:EvaluationRecord['metrics']}>(`/blueprints/${id}/evaluations/${activeEvaluation}/finish`,{
       method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
       geometry,correction_seconds:Math.round(minutes*60),notes:evaluationNotes,
       human_reviewed:true})});
     const rows=await request<EvaluationRecord[]>(`/blueprints/${id}/evaluations`);
     setEvaluations(rows);setActiveEvaluation(null);
     setReviewAttested(false);
     setStatus('Evaluation stored. Wall recall: '+Math.round((result.metrics?.walls.recall??0)*100)+'%.');
   }catch(err){setEvaluationError(String(err))}
   finally{setEvaluationBusy(false)}
 }
 async function compareRaster2Seq(){
   setR2sBusy(true);setR2sStatus('');setR2s(null);
   try{
     const result=await request<Raster2SeqResult>(`/blueprints/${id}/compare-raster2seq`,{method:'POST'});
     if(geometry&&(result.width_px!==geometry.width_px||result.height_px!==geometry.height_px))
       throw new Error('Raster2Seq source coordinates do not match this blueprint');
     setR2s(result);setR2sVisible(true);
     setR2sStatus(result.rooms.length+' room polygons predicted. Experimental, not verified.');
   }catch(err){setR2sStatus(String(err))}
   finally{setR2sBusy(false)}
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
     const previous=await request<Array<{
       preview_sha256:string;candidate_id:string;decision:'accept'|'reject'|'unsure'|'door'|'window';
       candidate:EvidenceCandidate;input_manifest?:Record<string,unknown>}>>(`/blueprints/${id}/fusion-reviews`);
     const matches:Record<string,'accept'|'reject'|'unsure'|'door'|'window'>={};
     const openingMatches:Record<string,'accept'|'reject'|'unsure'>={};
     for(const event of previous){
       if(event.preview_sha256!==result.input_manifest.source_preview_sha256)continue;
       if(event.input_manifest&&Object.keys(event.input_manifest).length&&
          JSON.stringify(event.input_manifest)!==JSON.stringify(result.input_manifest))continue;
       const current=result.candidates.find(c=>c.id===event.candidate_id);
       if(current){
         // IDs alone are not sufficient if model weights/config change.
         if(JSON.stringify({start:current.start,end:current.end,sources:current.sources,
                            category:current.category})!==
            JSON.stringify({start:event.candidate.start,end:event.candidate.end,
                            sources:event.candidate.sources,category:event.candidate.category}))continue;
         matches[current.id]=event.decision;
         continue;
       }
       const hint=result.opening_hints.find(h=>h.candidate_id===event.candidate_id);
       if(!hint)continue;
       const horizontal=hint.x2-hint.x1>=hint.y2-hint.y1;
       const start=horizontal?{x:hint.x1,y:(hint.y1+hint.y2)/2}:{x:(hint.x1+hint.x2)/2,y:hint.y1};
       const end=horizontal?{x:hint.x2,y:(hint.y1+hint.y2)/2}:{x:(hint.x1+hint.x2)/2,y:hint.y2};
       if(JSON.stringify(event.candidate.start)!==JSON.stringify(start)||
          JSON.stringify(event.candidate.end)!==JSON.stringify(end)||
          !event.candidate.sources?.includes('yolo_'+hint.kind))continue;
       if(event.decision===hint.kind)openingMatches[hint.candidate_id]='accept';
       else if(event.decision==='reject'||event.decision==='unsure')
         openingMatches[hint.candidate_id]=event.decision;
     }
     setUnified(result);setFusionIndex(0);setFusionDecisions(matches);setOpeningIndex(0);setOpeningDecisions(openingMatches);setReviewType('wall');setReviewFocus(false);
     setShowUnifiedWalls(true);setShowComparisonBoxes(false);
     setSegmentationOverlay('data:image/png;base64,'+result.mask_overlay_png_base64);
     setShowSegmentationOverlay(false);setShowModelDetections(false);
     setSpatialReview(false);setSelectedRoom(null);setStatus('Comparison ready — no layout was saved or replaced. Review the proposed walls before applying.');
   }catch(err){setStatus(String(err))}
   finally{setModelBusy(false)}
 }
 async function reviewAgentCandidate(candidateId:string,decision:'accept'|'reject'){
   if(!unified||fusionSaving)return;
   const candidate=unified.candidates.find(c=>c.id===candidateId);
   if(!candidate){setStatus('Suggested candidate is no longer in comparison. Re-run extraction.');return;}
   setFusionSaving(true);
   try{
     await request(`/blueprints/${id}/fusion-reviews`,{method:'POST',
       headers:{'Content-Type':'application/json'},body:JSON.stringify({
         preview_sha256:unified.input_manifest.source_preview_sha256,
         candidate,decision,input_manifest:unified.input_manifest})});
     setFusionDecisions(old=>({...old,[candidateId]:decision}));
     setStatus('Saved '+decision+' for '+candidateId+'. Accepting only labels it for inclusion in the draft.');
   }catch(err){setStatus('Unable to save suggestion review: '+String(err))}
   finally{setFusionSaving(false)}
 }
 const reviewCandidate=unified?.candidates[fusionIndex]||null;
 const fusionResolved=unified?.candidates.filter(c=>fusionDecisions[c.id]&&fusionDecisions[c.id]!=='unsure').length||0;
 async function decideFusion(decision:'accept'|'reject'|'unsure'|'door'|'window'){
   if(!unified||!reviewCandidate||fusionSaving)return;
   setFusionSaving(true);
   try{
     await request(`/blueprints/${id}/fusion-reviews`,{method:'POST',
       headers:{'Content-Type':'application/json'},body:JSON.stringify({
       preview_sha256:unified.input_manifest.source_preview_sha256,
       candidate:reviewCandidate,decision,input_manifest:unified.input_manifest})});
     setFusionDecisions(old=>({...old,[reviewCandidate.id]:decision}));
     setFusionIndex(current=>Math.min(current+1,unified.candidates.length-1));
     setStatus('Review saved for '+reviewCandidate.id+'. Continue through the candidate queue.');
   }catch(err){setStatus('Unable to save review: '+String(err))}
   finally{setFusionSaving(false)}
 }
 const currentOpening=unified?.opening_hints[openingIndex]||null;
 async function reviewDetectedOpening(decision:'accept'|'reject'|'unsure'){
   if(!unified||!currentOpening||fusionSaving)return;
   setFusionSaving(true);
   try{
     // Persist classification through the same audit stream as reviewed wall
     // proposals. Opening geometry is NOT added by the review action.
     const horizontal=currentOpening.x2-currentOpening.x1>=currentOpening.y2-currentOpening.y1;
     const candidate:EvidenceCandidate={id:currentOpening.candidate_id,
       start:horizontal?{x:currentOpening.x1,y:(currentOpening.y1+currentOpening.y2)/2}:{x:(currentOpening.x1+currentOpening.x2)/2,y:currentOpening.y1},
       end:horizontal?{x:currentOpening.x2,y:(currentOpening.y1+currentOpening.y2)/2}:{x:(currentOpening.x1+currentOpening.x2)/2,y:currentOpening.y2},
       sources:['yolo_'+currentOpening.kind],mask_support:0,
       category:'yolo_only',review_priority:currentOpening.source_confidence};
     await request(`/blueprints/${id}/fusion-reviews`,{method:'POST',
       headers:{'Content-Type':'application/json'},body:JSON.stringify({
       preview_sha256:unified.input_manifest.source_preview_sha256,candidate,
       decision:decision==='accept'?currentOpening.kind:decision,
       input_manifest:unified.input_manifest})});
     setOpeningDecisions(old=>({...old,[currentOpening.candidate_id]:decision}));
     setOpeningIndex(i=>Math.min(i+1,unified.opening_hints.length-1));
     setStatus(decision==='accept'?'Opening classified. Apply reviewed draft to attach it to a wall.':'Opening review saved.');
   }catch(err){setStatus(String(err))}
   finally{setFusionSaving(false)}
 }
 // CVAT-inspired shortcuts: only when reviewing (not when typing/editing).
 useEffect(()=>{
   if(!unified||view!=='2d'||mode!=='edit')return;
   const handler=(event:KeyboardEvent)=>{
     if(event.altKey||event.ctrlKey||event.metaKey||event.shiftKey)return;
     const target=event.target;
     if(target instanceof HTMLElement &&
         (target.isContentEditable||['INPUT','TEXTAREA','SELECT','BUTTON'].includes(target.tagName)))return;
     if(event.key==='ArrowRight'||event.key==='ArrowLeft'){
       event.preventDefault();
       const delta=event.key==='ArrowRight'?1:-1;
       if(reviewType==='wall')setFusionIndex(i=>Math.max(0,Math.min(unified.candidates.length-1,i+delta)));
       else setOpeningIndex(i=>Math.max(0,Math.min(unified.opening_hints.length-1,i+delta)));
       return;
     }
     if(event.key.toLowerCase()==='f'){event.preventDefault();setReviewFocus(f=>!f);return;}
     if(fusionSaving)return;
     if(reviewType==='wall'){
       const choice:Record<string,'accept'|'reject'|'unsure'|'door'|'window'>={
         '1':'accept','2':'door','3':'window','4':'reject','5':'unsure'};
       if(choice[event.key]){event.preventDefault();void decideFusion(choice[event.key]);}
     }else{
       const choice:Record<string,'accept'|'reject'|'unsure'>={'1':'accept','4':'reject','5':'unsure'};
       if(choice[event.key]){event.preventDefault();void reviewDetectedOpening(choice[event.key]);}
     }
   };
   window.addEventListener('keydown',handler);
   return ()=>window.removeEventListener('keydown',handler);
 },[unified,view,mode,reviewType,fusionSaving,fusionIndex,openingIndex,reviewCandidate,currentOpening]);
 async function applyReviewedOpenings(draft:Geometry):Promise<{geometry:Geometry;messages:string[]}>{
   if(!unified)return {geometry:draft,messages:[]};
   let current=draft;const messages:string[]=[];
   for(const hint of unified.opening_hints){
     if(openingDecisions[hint.candidate_id]!=='accept')continue;
     try{
       const res=await request<{geometry:Geometry;status:string;hint:OpeningHint}>(
         `/blueprints/${id}/opening-review/draft`,{method:'POST',
         headers:{'Content-Type':'application/json'},body:JSON.stringify({geometry:current,hint})});
       current=res.geometry;
       if(res.status!=='added'&&res.status!=='updated'){
         messages.push(hint.kind+' '+hint.candidate_id+': '+res.status+' — requires manual review');
       }
     }catch(err){messages.push(hint.kind+' '+hint.candidate_id+': '+String(err))}
   }
   return {geometry:current,messages};
 }
 async function applyUnified(){
   if(!unified||!layout||!geometry)return;
   if(geometry!==layout.geometry){
     setStatus('You have unsaved geometry edits. Save the draft first, then apply the approved wall labels; your corrections will be preserved.');
     return;
   }
   const selected=unified.candidates.filter(c=>fusionDecisions[c.id]==='accept');
   const openingCount=unified.opening_hints.filter(h=>openingDecisions[h.candidate_id]==='accept').length;
   if(!selected.length&&!openingCount){
     setStatus('Classify walls or openings first, then apply them to the draft.');return;
   }
   if(!window.confirm('Apply '+selected.length+' reviewed walls and '+openingCount+' classified openings to the current UNSAVED draft? Existing walls, room boundaries and openings will be preserved. Review in 2D before saving.'))return;
   setBusy(true);
   try{
     const merged=await request<{saved:false;geometry:Geometry;added:number;already_present:number;ignored:number;layout_version:number}>(
       `/blueprints/${id}/fusion-draft/merge`,{
       method:'POST',headers:{'Content-Type':'application/json'},
       body:JSON.stringify({
         preview_sha256:unified.input_manifest.source_preview_sha256,
         layout_version:layout.version,geometry,candidate_ids:selected.map(c=>c.id)
       })});
     if(selected.length>0&&merged.added===0&&merged.already_present===0){
       setStatus('No approved wall labels could be merged. Re-run extraction and review the new proposals.');return;
     }
     const openings=await applyReviewedOpenings(merged.geometry);
     setGeometry(openings.geometry);setSelectedWall(null);setView('2d');
     setStatus(merged.added+' approved walls added to your UNSAVED draft ('+
       merged.already_present+' already present, '+merged.ignored+' skipped). Geometry now has '+
       openings.geometry.walls.length+' walls and '+openings.geometry.openings.length+' physical openings. Review them and click Save corrected draft. '+
       openings.messages.join('; '));
   }catch(error){setStatus(String(error))}
   finally{setBusy(false)}
 }
 async function trySegmentation(){
   if(!window.confirm('Run experimental local wall segmentation? This creates a new draft and may replace all unreviewed wall proposals. Existing saved versions remain available.'))return;
   setModelBusy(true);setStatus('');
   try{
     const result=await request<{layout:Layout;mask_overlay_png_base64:string;report:{provider:string;checkpoint:string;line_count:number;raw_mask_line_count:number;normalized_mask_line_count:number;coverage_fraction:number}}>(
       `/blueprints/${id}/segmentation/propose`,{method:'POST'});
     setLayout(result.layout);resetGeometry(result.layout.geometry);
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
     setLayout(result.layout);resetGeometry(result.layout.geometry);
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
 async function inspectSharedGraph(){
   if(!layout)return;
   if(geometry!==layout.geometry){
     setStatus('Save your edits first so junctions reflect your latest geometry.');
     return;
   }
   try{
     const result=await request<NonNullable<typeof sharedGraph>>(`/blueprints/${id}/structural-graph`);
     setSharedGraph(result);
     setStatus('Shared-junction graph inspected (read only); no walls or openings were changed.');
   }catch(error){setStatus(String(error))}
 }
 async function extract(){setBusy(true);setStatus('');try{
  const l=await request<Layout>(`/blueprints/${id}/extract`,{method:'POST'});
  setLayout(l);resetGeometry(l.geometry);setStatus('AI proposal loaded. Review and calibrate all geometry before verifying.');
 }catch(e){setStatus(String(e))}finally{setBusy(false)}}
 async function save(verified=false,structureReviewed=false){if(!geometry)return;setBusy(true);try{
  const l=await request<Layout>(`/blueprints/${id}/layout`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({geometry,verified,structure_reviewed:structureReviewed})});
  setLayout(l);resetGeometry(l.geometry);setStatus(verified?'Metric geometry verified.':structureReviewed?'Wall positions reviewed and saved; measurements are still provisional.':'Draft saved.');
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
    try{return moveSharedJunction(current,wallId,which,snapped)}
    catch(error){setStatus(String(error));return current;}
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
   setLayout(l);resetGeometry(l.geometry);setStatus('Suggestion accepted as a draft wall.');
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
 function removeUntouchedStarterWalls(){
   if(!geometry)return;
   const pad=Math.min(geometry.width_px,geometry.height_px)*.12;
   const x0=pad,y0=pad,x1=geometry.width_px-pad,y1=geometry.height_px-pad;
   const match=(a:Pt,b:Pt,c:Pt,d:Pt)=>(
     (Math.hypot(a.x-c.x,a.y-c.y)<.1&&Math.hypot(b.x-d.x,b.y-d.y)<.1)||
     (Math.hypot(a.x-d.x,a.y-d.y)<.1&&Math.hypot(b.x-c.x,b.y-c.y)<.1));
   const segments:[Pt,Pt][]=[
     [{x:x0,y:y0},{x:x1,y:y0}],
     [{x:x1,y:y0},{x:x1,y:y1}],
     [{x:x1,y:y1},{x:x0,y:y1}],
     [{x:x0,y:y1},{x:x0,y:y0}]];
   const placeholders=geometry.walls.filter(w=>/^w[0-3]$/.test(w.id)&&
     segments.some(([a,b])=>match(w.start,w.end,a,b)));
   if(!placeholders.length){setStatus('No untouched starter walls found.');return;}
   if(!window.confirm('Remove '+placeholders.length+' unmodified starter wall(s) from this UNSAVED draft? Only placeholders matching the initial rectangle will be removed. Inspect the result before saving.'))return;
   const ids=new Set(placeholders.map(w=>w.id));
   setGeometry({...geometry,structure_reviewed:false,
     rooms:geometry.rooms.filter(r=>r.id!=='room-1'),
     walls:geometry.walls.filter(w=>!ids.has(w.id)),
     openings:geometry.openings.filter(o=>!ids.has(o.wall_id)),
     warnings:geometry.warnings.filter(w=>!w.includes('Starter geometry'))});
   setStatus('Removed '+placeholders.length+' untouched starter walls from unsaved draft. Review the remaining walls before saving or scoring.');
 }
 async function previewOpeningAssociations(){
   if(!geometry||associationBusy)return;
   setAssociationBusy(true);
   try{
     const source=JSON.stringify(geometry);
     const result=await request<{items:OpeningMatch[];proposed:number;unresolved:number}>(`/blueprints/${id}/openings/association-preview`,{
       method:'POST',headers:{'Content-Type':'application/json'},
       body:JSON.stringify({geometry})});
     if(source!==JSON.stringify(geometry))return;
     setAssociation({source,...result});
     setStatus(result.proposed+' visual opening-to-wall matches proposed, '+result.unresolved+
       ' unresolved. These are NOT metric 3D openings.');
   }catch(error){setStatus(String(error))}
   finally{setAssociationBusy(false)}
 }
 async function previewConnections(){
   if(!geometry||!layout||connectivityBusy)return;
   setConnectivityBusy(true);setStatus('');
   try{
     const source=JSON.stringify(geometry);
     const proposal=await request<ConnectivityProposal>(`/blueprints/${id}/connectivity/preview`,{
       method:'POST',headers:{'Content-Type':'application/json'},
       body:JSON.stringify({geometry,tolerance_px:5})});
     if(JSON.stringify(geometry)!==source)return;
     setConnectivity({source,proposal});setSelectedJunction(null);
     setStatus(proposal.changes.length?
       proposal.changes.length+' endpoint adjustments and '+proposal.removed_starter_ids.length+' starter placeholders proposed for removal (NOT saved). Review on the 2D plan.':
       'No unambiguous near-junction corrections found. Missing walls must be drawn from image evidence.');
   }catch(error){setStatus(String(error))}
   finally{setConnectivityBusy(false)}
 }
 function applyConnections(){
   if(!geometry||!connectivity)return;
   if(JSON.stringify(geometry)!==connectivity.source){
     setConnectivity(null);setStatus('Geometry changed since connectivity preview. Preview again before applying.');return;
   }
   if(!connectivity.proposal.changes.length&&!connectivity.proposal.removed_starter_ids.length){setStatus('No topology corrections to apply.');return;}
   if(!window.confirm('Apply '+connectivity.proposal.changes.length+
     ' endpoint adjustments and remove '+connectivity.proposal.removed_starter_ids.length+
     ' exact starter placeholders from the UNSAVED 2D/3D draft? This does not add missing walls or verify dimensions.'))return;
   setGeometry(connectivity.proposal.geometry);setConnectivity(null);setSelectedWall(null);
   setStatus('Connectivity adjustments applied to UNSAVED draft. Inspect all joints and click Save corrected draft.');
 }
 function applySelectedJunction(index:number){
  if(!geometry||!connectivity||JSON.stringify(geometry)!==connectivity.source)return;
  const change=connectivity.proposal.changes[index];if(!change)return;
  const group=change.reason==='perpendicular corner'
    ?connectivity.proposal.changes.filter(c=>c.reason===change.reason&&dist(c.proposed,change.proposed)<.01)
    :[change];
  if(change.reason==='perpendicular corner'&&group.length!==2){
   setStatus('Incomplete corner proposal; no geometry changed.');return;
  }
  setGeometry({...geometry,structure_reviewed:false,walls:geometry.walls.map(w=>{
   const updates=group.filter(c=>c.wall_id===w.id);
   if(!updates.length)return w;
   const modified={...w};
   for(const c of updates)modified[c.endpoint]={...c.proposed};
   return modified;
  })});
  setConnectivity(null);setSelectedJunction(null);
  setStatus('Selected junction applied to UNSAVED draft. Save corrected draft, then preview remaining junctions.');
 }
 function removeWall(id:string){if(!geometry)return;setSelectedWall(null);setGeometry({...geometry,structure_reviewed:false,walls:geometry.walls.filter(w=>w.id!==id),openings:geometry.openings.filter(o=>o.wall_id!==id)});setStatus('Draft wall removed. Save to persist changes.')}
 function selectGap(gap:LooseEndpoint){
  setSelectedRoom(null);setSelectedWall(gap.source_wall_ids[0]||null);setMode('edit');setReviewFocus(false);
  setStatus('Inspect the highlighted endpoint against the source. Connect only a real wall junction.');
 }
 function removeSharedPartition(wallId:string){
  if(!geometry||!quality?.room_faces?.some(r=>r.id===selectedRoom&&r.shared_source_wall_ids.includes(wallId)))return;
  if(geometry.openings.some(o=>o.wall_id===wallId)){setStatus('Reconcile hosted openings before removing this partition.');return;}
  const wall=geometry.walls.find(w=>w.id===wallId);if(!wall)return;
  const middle={x:(wall.start.x+wall.end.x)/2,y:(wall.start.y+wall.end.y)/2};
  setGeometry({...geometry,structure_reviewed:false,walls:geometry.walls.filter(w=>w.id!==wallId),
   rooms:geometry.rooms.filter(r=>!r.points.some((p,i)=>segmentDistance(middle,{start:p,end:r.points[(i+1)%r.points.length]})<.01))});
  setSelectedRoom(null);setSelectedWall(null);setStatus('Shared partition removed from draft. Review the combined region; Undo restores the partition.');
 }
 return <div className="app plan-editor"><aside><h2>✦ Florp</h2><Link href="/">← Projects</Link>
 <hr style={{borderColor:'#354053',margin:'22px 0'}}/><p>Saved layout v{layout?.version??'–'} · {layout?.verified?'Verified':'Unverified'}</p>
 {geometry&&layout&&<p className="notice">{geometry===layout.geometry?'All changes saved':'● Unsaved edits — Save draft when ready'}</p>}
 <div className="stack">
 <button disabled={modelBusy||busy} onClick={()=>void compareUnified()}>1 · Extract and compare</button>
 <button disabled={!unified||busy||modelBusy||fusionSaving} onClick={()=>void applyUnified()}>2 · Apply reviewed walls + openings</button>
 <button className="secondary" disabled={busy} onClick={()=>save(false)}>3 · Save corrected draft</button>
 {unified&&<small>Review decisions are labels until applied. The draft currently contains {geometry?.walls.length||0} walls and {geometry?.openings.length||0} physical openings.</small>}
 <button className="secondary" disabled={busy} onClick={()=>save(false,true)}>Confirm reviewed walls</button>
 </div>
 <details style={{marginTop:12}}><summary>Advanced geometry actions</summary>
 <div className="stack">
 <button className="secondary" disabled={busy} onClick={extract}>LLM geometry extraction</button>
 <button className="secondary" disabled={busy} onClick={()=>save(true)}>Verify calibrated physical dimensions</button>
 </div><small>Metric verification requires a confirmed reference dimension.</small>
 </details>
 <div className="stack" style={{marginTop:16,borderTop:'1px solid #475569',paddingTop:12}}>
 <details><summary>Training & evaluation</summary><div className="stack"><strong>Measure extraction quality</strong>
 <button className="secondary" disabled={!layout} onClick={()=>void downloadReviewedGeometry()}>
 Export saved walls + labels JSON</button>
 <small>Keep a model snapshot, correct the drawing, then score it against your reviewed geometry.</small>
 <button className="secondary" disabled={!unified||evaluationBusy} onClick={()=>void captureBaseline()}>
 Save uncorrected model baseline</button>
 {unified?.yolo_error&&<small role="status">YOLO unavailable — this baseline will be labeled Yytsi-only. Re-run extraction after YOLO is fixed to compare both models.</small>}
 {activeEvaluation&&<><small>Active evaluation: {activeEvaluation.slice(0,8)} · baseline stored</small>
 <label>Correction time (minutes)<input type="number" min="0" max="1440" step=".5"
 value={correctionMinutes} onChange={e=>setCorrectionMinutes(e.target.value)}/></label>
 <label>Missed walls / opening notes<textarea rows={2} value={evaluationNotes}
 onChange={e=>setEvaluationNotes(e.target.value)}/></label>
 <label><input type="checkbox" checked={reviewAttested} onChange={e=>setReviewAttested(e.target.checked)}/>
 I independently checked every wall and opening against the original plan</label>
 <button disabled={!reviewAttested||evaluationBusy} onClick={()=>void finishEvaluation()}>
 Score reviewed geometry</button></>}
 {evaluationError&&<small role="alert">{evaluationError}</small>}
 <details><summary>Saved evaluations ({evaluations.length})</summary>
 {evaluations.map(r=><div key={r.id} style={{padding:'6px 0',borderBottom:'1px solid #475569'}}>
 <small>{r.provider} · {r.status} · {r.id.slice(0,8)}</small>
 {r.status==='completed'&&r.metrics?.walls&&<small> Wall precision {Math.round(r.metrics.walls.precision*100)}% · recall {Math.round(r.metrics.walls.recall*100)}% · F1 {Math.round(r.metrics.walls.f1*100)}% · {(r.correction_seconds??0)/60} min</small>}
 {r.status==='baseline'&&<small>Not scored yet — correct and review this drawing.</small>}
 {r.status==='baseline'&&<button className="secondary" onClick={()=>setActiveEvaluation(r.id)}>Resume</button>}
 <button className="secondary" onClick={()=>void downloadEvaluation(r.id)}>Export JSON</button>
 </div>)}
 </details>
 </div></details></div></aside>
 <main><header><div><h1>Plan editor</h1><p className="muted">Extract → review walls and gaps → openings and scale → save</p></div>
 <div className="row"><button className="secondary" disabled={!history.canUndo||busy||modelBusy} onClick={()=>{history.undo();setConnectivity(null);setSelectedWall(null);}}>Undo draft edit</button><button className="secondary" disabled={!history.canRedo||busy||modelBusy} onClick={()=>{history.redo();setConnectivity(null);setSelectedWall(null);}}>Redo draft edit</button><button className={view==='2d'?'':'secondary'} onClick={()=>setView('2d')}>2D editor</button>
 <button className={view==='3d'?'':'secondary'} onClick={()=>setView('3d')}>3D shell</button></div></header>
 {status&&<p className="notice">{status}</p>}
 {qualityError&&<p role="alert" className="notice">Geometry checks unavailable: {qualityError}</p>}
 {quality&&<details className="notice"><summary>{quality.ready_for_metric_scene?'Geometry checks passed — independent accuracy review still required':'Incomplete plan — 3D is a draft preview'}</summary><ul>{[...quality.structural_issues,...quality.metric_issues].map(issue=><li key={issue}>{issue}</li>)}</ul></details>}
 {geometry&&<div className="grid" style={{gridTemplateColumns:'minmax(0,1fr)'}}>
 <div className="panel"><h2>{view==='2d'?'Floor-plan overlay':'3D shell · draft geometry'}</h2>
 {unified&&<p className="notice">{Object.values(fusionDecisions).filter(d=>d==='accept').length} walls accepted · {Object.values(openingDecisions).filter(d=>d==='accept').length} openings classified. Main draft: {geometry.walls.length} walls · {geometry.openings.length} physical openings. Apply reviewed walls + openings to update this view; unresolved opening hosts still need correction.</p>}
 {view==='2d'&&<div className="row" style={{marginBottom:12}}>
 <button className={spatialReview?'':'secondary'} onClick={()=>{setSpatialReview(true);setReviewFocus(false);setMode('edit')}}>Rooms & gaps</button>
 <button className={!spatialReview?'':'secondary'} onClick={()=>setSpatialReview(false)}>Model candidates</button>
 <button className={mode==='edit'?'':'secondary'} onClick={()=>{setMode('edit');setWallStart(null);setStatus('Click any saved wall on the floor plan, then drag either green endpoint handle. Save corrected draft to persist.')}}>Edit wall endpoints</button>
  {(['wall','door','window'] as const).map(tool=><button key={tool} className={mode===tool?'':'secondary'} onClick={()=>{setMode(mode===tool?'edit':tool);setWallStart(null)}}>{tool==='wall'?'Draw missing wall':tool==='door'?'Add door':'Add window'}</button>)}
 </div>}
 {view==='2d'?<div className="annotation-workspace">
 <svg className="canvas" viewBox={reviewFocus&&unified?(()=>{
 const selected=reviewType==='wall'?
   {x1:reviewCandidate?.start.x??0,y1:reviewCandidate?.start.y??0,x2:reviewCandidate?.end.x??0,y2:reviewCandidate?.end.y??0}:
   currentOpening;
 if(!selected)return `0 0 ${geometry.width_px} ${geometry.height_px}`;
 const w=Math.min(geometry.width_px,Math.max(Math.abs(selected.x2-selected.x1)*2.8,geometry.width_px*.30));
 const h=Math.min(geometry.height_px,Math.max(Math.abs(selected.y2-selected.y1)*2.8,w*geometry.height_px/geometry.width_px));
 const x=Math.max(0,Math.min(geometry.width_px-w,(selected.x1+selected.x2-w)/2));
 const y=Math.max(0,Math.min(geometry.height_px-h,(selected.y1+selected.y2-h)/2));
 return `${x} ${y} ${w} ${h}`;
})():`0 0 ${geometry.width_px} ${geometry.height_px}`}
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
 {spatialReview&&mode==='edit'&&<SpatialOverlay quality={quality} roomId={selectedRoom} width={geometry.width_px} onRoom={id=>{setSelectedRoom(id);setSelectedWall(null);setReviewFocus(false)}} onGap={selectGap}/>}
 {r2s&&r2sVisible&&r2s.rooms.map((room,i)=>
 <polygon key={'r2s-'+i}
 points={room.points.map(([x,y])=>`${x},${y}`).join(' ')}
 fill="#f59e0b" fillOpacity={.1} stroke="#d97706"
 strokeWidth={Math.max(2,geometry.width_px/420)} strokeDasharray="8 4"
 pointerEvents="none"/>)}
 {r2s&&r2sVisible&&r2s.opening_symbols.map((symbol,i)=>
 <polygon key={'r2s-opening-'+i}
 points={symbol.points.map(([x,y])=>`${x},${y}`).join(' ')}
 fill={symbol.kind==='door'?'#ea580c':'#06b6d4'} fillOpacity={.15}
 stroke={symbol.kind==='door'?'#ea580c':'#0891b2'}
 strokeWidth={Math.max(3,geometry.width_px/360)} strokeDasharray="3 3"
 pointerEvents="none"/>)}
 {segmentationOverlay&&showSegmentationOverlay&&<image href={segmentationOverlay}
 width={geometry.width_px} height={geometry.height_px} pointerEvents="none"/>}
 {unified&&showUnifiedWalls&&unified.candidates.map((item,i)=>
 <g key={'review-wall-'+item.id}>
 <line x1={item.start.x} y1={item.start.y} x2={item.end.x} y2={item.end.y}
 stroke="transparent" strokeWidth={Math.max(18,geometry.width_px/95)}
 style={{cursor:'pointer'}} pointerEvents={mode==='edit'?'stroke':'none'} onClick={e=>{e.stopPropagation();setFusionIndex(i);setReviewType('wall');setReviewFocus(true)}}/>
 </g>)}
 {unified&&showUnifiedWalls&&unified.candidates.map((item,i)=>
 <line key={'fused-'+item.id} x1={item.start.x} y1={item.start.y}
 x2={item.end.x} y2={item.end.y}
 onClick={e=>{e.stopPropagation();setFusionIndex(i);setReviewType('wall');setReviewFocus(true)}}
 style={{cursor:'pointer'}}
 stroke={fusionDecisions[item.id]==='reject'?'#9ca3af':
 fusionDecisions[item.id]==='accept'?'#16a34a':
 item.category==='agreed'?'#1d4ed8':item.category==='yolo_only'?'#d97706':'#9333ea'}
 strokeWidth={Math.max(reviewType==='wall'&&i===fusionIndex?8:3,geometry.width_px/360)}
 strokeDasharray={reviewType==='wall'&&i===fusionIndex?'none':'5 3'}
 opacity={reviewType==='wall'&&i===fusionIndex?1:fusionDecisions[item.id]==='reject'?.15:.45}>
 <title>{item.category}; mask support {Math.round(item.mask_support*100)}%</title>
 </line>)}
 {unified&&unified.opening_hints.map((hint,i)=>
 <rect key={'opening-hint-'+hint.candidate_id} x={hint.x1} y={hint.y1}
 width={hint.x2-hint.x1} height={hint.y2-hint.y1}
 pointerEvents={mode==='edit'?'all':'none'} onClick={e=>{e.stopPropagation();setOpeningIndex(i);setReviewType('opening');setReviewFocus(true)}}
 stroke={openingDecisions[hint.candidate_id]==='reject'?'#9ca3af':
 openingDecisions[hint.candidate_id]==='accept'?'#16a34a':
 hint.kind==='door'?'#ea580c':'#0891b2'}
 strokeWidth={reviewType==='opening'&&i===openingIndex?Math.max(5,geometry.width_px/270):2}
 strokeDasharray={reviewType==='opening'&&i===openingIndex?'none':'6 4'}
 opacity={reviewType==='opening'&&i===openingIndex?1:.5}
 fill="transparent" style={{cursor:'pointer'}}><title>{hint.kind}: {hint.reason}</title></rect>)}
  {unified&&reviewType==='wall'&&reviewCandidate&&<g pointerEvents="none">
   <line x1={reviewCandidate.start.x} y1={reviewCandidate.start.y}
         x2={reviewCandidate.end.x} y2={reviewCandidate.end.y}
         stroke="#fff" strokeWidth={Math.max(15,geometry.width_px/140)} strokeLinecap="round"/>
   <line x1={reviewCandidate.start.x} y1={reviewCandidate.start.y}
         x2={reviewCandidate.end.x} y2={reviewCandidate.end.y}
         stroke="#f97316" strokeWidth={Math.max(8,geometry.width_px/250)}
         strokeLinecap="round"/>
   <circle cx={reviewCandidate.start.x} cy={reviewCandidate.start.y}
           r={Math.max(6,geometry.width_px/190)} fill="#fff" stroke="#ea580c" strokeWidth="3"/>
   <circle cx={reviewCandidate.end.x} cy={reviewCandidate.end.y}
           r={Math.max(6,geometry.width_px/190)} fill="#fff" stroke="#ea580c" strokeWidth="3"/>
  </g>}
  {unified&&reviewType==='opening'&&currentOpening&&<rect
    x={currentOpening.x1} y={currentOpening.y1}
    width={currentOpening.x2-currentOpening.x1}
    height={currentOpening.y2-currentOpening.y1}
    fill="#f97316" fillOpacity={.12} stroke="#f97316"
    strokeWidth={Math.max(6,geometry.width_px/220)} pointerEvents="none"/>}
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
 {showLegacyRoomOutline&&geometry.rooms.map((r,ri)=><g key={r.id}>
 <polygon points={r.points.map(p=>`${p.x},${p.y}`).join(' ')} fill="#46b494" fillOpacity={.08} stroke="#008a70" strokeWidth={Math.max(2,geometry.width_px/400)} pointerEvents="none"/>
 {mode==='edit'&&r.points.map((p,pi)=><circle key={pi} cx={p.x} cy={p.y} r={Math.max(5,geometry.width_px/140)} fill="white" stroke="#008a70"
 strokeWidth={Math.max(2,geometry.width_px/650)} style={{cursor:'grab'}} onPointerDown={e=>{e.stopPropagation();history.begin();e.currentTarget.setPointerCapture(e.pointerId)}}
 onPointerMove={e=>{if(!e.currentTarget.hasPointerCapture(e.pointerId))return;const svg=e.currentTarget.ownerSVGElement;if(!svg)return;const point=localPoint(svg,e.clientX,e.clientY);if(point)updatePoint(ri,pi,point)}}
 onLostPointerCapture={()=>history.end()} onPointerUp={e=>e.currentTarget.releasePointerCapture(e.pointerId)} />)}
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
 {geometry.walls.map(w=><line key={w.id} x1={w.start.x} y1={w.start.y} x2={w.end.x} y2={w.end.y} stroke={selectedWall===w.id?"#16a34a":w.id.startsWith('user-')?'#d97706':'#0284c7'}
 strokeWidth={Math.max(selectedWall===w.id?5:3,geometry.width_px/220)}
 pointerEvents={mode==='edit'?'stroke':'none'} style={{cursor:mode==='edit'?'pointer':'default'}}
 onClick={e=>{if(mode==='edit'){e.stopPropagation();setSelectedWall(w.id)}}}/>)}
 {mode==='edit'&&geometry.walls.filter(w=>w.id===selectedWall).flatMap(w=>(
  (['start','end'] as const).map(which=>{
   const p=w[which];
   return <circle key={w.id+which} cx={p.x} cy={p.y} r={Math.max(7,geometry.width_px/130)}
    fill="white" stroke="#16a34a" strokeWidth={3} style={{cursor:'grab',touchAction:'none'}}
    onPointerDown={e=>{e.stopPropagation();history.begin();e.currentTarget.setPointerCapture(e.pointerId)}}
    onPointerMove={e=>{
      if(!e.currentTarget.hasPointerCapture(e.pointerId))return;
      const svg=e.currentTarget.ownerSVGElement;
      if(!svg)return;
      const point=localPoint(svg,e.clientX,e.clientY);
      if(point)moveWallEndpoint(w.id,which,point);
    }}
    onLostPointerCapture={()=>history.end()} onPointerUp={e=>{if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId)}}
    onClick={e=>e.stopPropagation()}/>;
  })
 ))}
 {connectivity&&JSON.stringify(geometry)===connectivity.source&&
 connectivity.proposal.changes.map((c,i)=><g key={'connect-'+i}>
 <line x1={c.original.x} y1={c.original.y} x2={c.proposed.x} y2={c.proposed.y}
 stroke="#0891b2" strokeWidth={Math.max(3,geometry.width_px/300)}
 strokeDasharray="4 3" pointerEvents="none"/>
 <circle cx={c.original.x} cy={c.original.y} r={Math.max(4,geometry.width_px/250)}
 fill="#fff" stroke="#0891b2" strokeWidth="2" pointerEvents="none"/>
 <circle cx={c.proposed.x} cy={c.proposed.y} r={Math.max(4,geometry.width_px/250)}
 fill={selectedJunction===i?'#16a34a':'#0891b2'} stroke="white" strokeWidth="2" pointerEvents="none"/>
 <circle cx={c.proposed.x} cy={c.proposed.y} r={Math.max(12,geometry.width_px/80)} fill="transparent" stroke="transparent" style={{cursor:'pointer'}}
  onClick={e=>{e.stopPropagation();setSelectedJunction(i);setMode('edit')}}><title>Review {c.reason} for {c.wall_id}</title></circle>
 </g>)}
 {association&&JSON.stringify(geometry)===association.source&&association.items.map((item,i)=>
 <line key={'opening-assoc-'+i} x1={item.start.x} y1={item.start.y}
 x2={item.end.x} y2={item.end.y} pointerEvents="none"
 stroke={item.status==='proposed'?'#06b6d4':'#f97316'}
 strokeWidth={Math.max(6,geometry.width_px/210)} strokeDasharray="7 3"/>)}
 {wallStart&&<circle cx={wallStart.x} cy={wallStart.y} r={Math.max(5,geometry.width_px/130)} fill="#d97706" pointerEvents="none"/>}
 </svg>
 <div className="annotation-inspector">
 {spatialReview?<SpatialInspector quality={quality} geometry={geometry} roomId={selectedRoom} wallId={selectedWall}
  onBoundary={id=>{setSelectedWall(id);setMode('edit')}} onPartition={removeSharedPartition}
  onDraw={()=>{setMode('wall');setWallStart(null);setStatus('Click two boundary points to draw a partition. Review the resulting regions, then save.')}}
  onNextGap={()=>{const gaps=quality?.loose_endpoints||[];if(gaps.length){const next=(gapIndex+1)%gaps.length;setGapIndex(next);selectGap(gaps[next]);}}}/>:<><strong>Review on plan</strong>
 {!unified?<p className="muted">Run Extract and compare to review detected walls and openings here.</p>:<>
 <div className="row" style={{margin:'12px 0',flexWrap:'wrap',gap:4}}>
 <button className={reviewType==='wall'?'':'secondary'} onClick={()=>{setReviewType('wall');setReviewFocus(false)}}>Walls ({unified.candidates.length})</button>
 <button className={reviewType==='opening'?'':'secondary'} onClick={()=>{setReviewType('opening');setReviewFocus(false)}}>Openings ({unified.opening_hints.length})</button>
 </div>
 <small>{reviewType==='wall'?
 `${unified.candidates.filter(c=>fusionDecisions[c.id]&&fusionDecisions[c.id]!=='unsure').length} / ${unified.candidates.length} classified`:
 `${unified.opening_hints.filter(h=>openingDecisions[h.candidate_id]&&openingDecisions[h.candidate_id]!=='unsure').length} / ${unified.opening_hints.length} classified`}</small>
 <div style={{height:5,background:'#e2e8f0',borderRadius:8,margin:'8px 0 14px'}}>
 <div style={{width:((reviewType==='wall'?unified.candidates.filter(c=>fusionDecisions[c.id]&&fusionDecisions[c.id]!=='unsure').length:unified.opening_hints.filter(h=>openingDecisions[h.candidate_id]&&openingDecisions[h.candidate_id]!=='unsure').length)/
 Math.max(1,reviewType==='wall'?unified.candidates.length:unified.opening_hints.length)*100)+'%',height:'100%',background:'#059669',borderRadius:8}}/>
 </div>
 {reviewType==='wall'&&reviewCandidate&&<>
 <strong>Wall candidate {fusionIndex+1} / {unified.candidates.length}</strong>
 <p style={{fontSize:13,margin:'6px 0'}}>{unified.geometry_review?.suggestions.some(h=>h.candidate_id===reviewCandidate.id)?'Potential missing partition · ':''}{reviewCandidate.category.replaceAll('_',' ')} · mask support {Math.round(reviewCandidate.mask_support*100)}%</p>
 <p style={{fontSize:13}}>Decision: <strong>{fusionDecisions[reviewCandidate.id]||'Pending'}</strong></p>
 <div className="row" style={{flexWrap:'wrap',gap:5}}>
 <button disabled={fusionSaving} onClick={()=>void decideFusion('accept')}>Wall</button>
 <button className="secondary" disabled={fusionSaving} onClick={()=>void decideFusion('door')}>Door</button>
 <button className="secondary" disabled={fusionSaving} onClick={()=>void decideFusion('window')}>Window</button>
 <button className="secondary" disabled={fusionSaving} onClick={()=>void decideFusion('reject')}>Not wall</button>
 <button className="secondary" disabled={fusionSaving} onClick={()=>void decideFusion('unsure')}>Unsure</button>
 </div>
 </>}
 {reviewType==='opening'&&currentOpening&&<>
 <strong>{currentOpening.kind==='door'?'Door':'Window'} {openingIndex+1} / {unified.opening_hints.length}</strong>
 <p style={{fontSize:13}}>Detector confidence {Math.round(currentOpening.source_confidence*100)}%. {currentOpening.reason}</p>
 <p style={{fontSize:13}}>Decision: <strong>{openingDecisions[currentOpening.candidate_id]||'Pending'}</strong></p>
 <div className="row" style={{flexWrap:'wrap',gap:5}}>
 <button disabled={fusionSaving} onClick={()=>void reviewDetectedOpening('accept')}>Classify as {currentOpening.kind}</button>
 <button className="secondary" disabled={fusionSaving} onClick={()=>void reviewDetectedOpening('reject')}>Not opening</button>
 <button className="secondary" disabled={fusionSaving} onClick={()=>void reviewDetectedOpening('unsure')}>Unsure</button>
 </div>
 </>}
 <div className="row" style={{marginTop:12,gap:6,flexWrap:'wrap'}}>
 <button className="secondary" onClick={()=>{if(reviewType==='wall')setFusionIndex(i=>Math.max(0,i-1));else setOpeningIndex(i=>Math.max(0,i-1));}}>← Previous</button>
 <button className="secondary" onClick={()=>{if(reviewType==='wall')setFusionIndex(i=>Math.min(unified.candidates.length-1,i+1));else setOpeningIndex(i=>Math.min(unified.opening_hints.length-1,i+1));}}>Next →</button>
 <button className="secondary" onClick={()=>{
 if(reviewType==='wall'){const i=unified.candidates.findIndex((c,i)=>i>fusionIndex&&!fusionDecisions[c.id]);setFusionIndex(i<0?Math.max(0,unified.candidates.findIndex(c=>!fusionDecisions[c.id])):i);}
 else{const i=unified.opening_hints.findIndex((h,j)=>j>openingIndex&&!openingDecisions[h.candidate_id]);setOpeningIndex(i<0?Math.max(0,unified.opening_hints.findIndex(h=>!openingDecisions[h.candidate_id])):i);}
 }}>Next pending</button>
 </div>
 <label style={{display:'block',marginTop:12}}><input type="checkbox" checked={reviewFocus} onChange={e=>setReviewFocus(e.target.checked)}/> Zoom to selected item</label>
 <small style={{display:'block',margin:'8px 0'}}>Select geometry on the plan. Shortcuts: ← / → navigate, 1 wall/confirm, 2 door, 3 window, 4 reject, 5 unsure, F zoom. Shortcuts are inactive while typing.</small>
 <button disabled={busy||modelBusy||fusionSaving} onClick={()=>void applyUnified()}>Apply reviewed walls + openings to draft</button>
 <small style={{display:'block',marginTop:8}}>Review decisions are saved separately. Applying changes only your unsaved 2D/3D draft.</small>
 </>}
 </>} </div></div>:<Viewer geometry={geometry}/>}
 <p className="muted">{mode==='wall'?'Click two points to add a missing wall.':mode==='door'||mode==='window'?'Click near a wall or on a detected opening box to add or correct it.':'Review model walls and detected openings; tap a wall to adjust or reject it.'}</p></div>
 <details className="panel"><summary>Repair walls, gaps and opening hosts</summary>{layout&&geometry&&<CanonicalWorkspace bid={id} layoutVersion={layout.version} hasUnsavedChanges={geometry!==layout.geometry} onUseDraft={g=>{setGeometry(g);setView('2d');setSelectedWall(null);setStatus('Repaired graph loaded into the main 2D/3D draft. Save corrected draft to persist.');}}/>} {view==='2d'&&geometry.walls.length>0&&<div style={{border:'1px solid #cbd5e1',padding:10,borderRadius:10,marginBottom:12}}>
 <div className="row" style={{justifyContent:'space-between'}}>
 <strong>Connect reviewed wall endpoints</strong>
 <button className="secondary" disabled={connectivityBusy||busy}
 onClick={()=>void previewConnections()}>{connectivityBusy?'Analyzing…':'Preview connections'}</button>
 </div>
 {connectivity&&<div style={{marginTop:8}}>
 <small>{connectivity.proposal.changes.length} proposed adjustments · {connectivity.proposal.removed_starter_ids.length} starter placeholders to remove · structural groups {connectivity.proposal.before_components} → {connectivity.proposal.after_components} · loose endpoints {connectivity.proposal.before_dangling} → {connectivity.proposal.after_dangling}</small>
 <div className="row" style={{marginTop:8}}>
 {selectedJunction!==null&&connectivity.proposal.changes[selectedJunction]&&<div role="status" style={{marginTop:8,padding:10,border:'2px solid #0891b2',borderRadius:8}}>
   <strong>Selected junction: {connectivity.proposal.changes[selectedJunction].wall_id}</strong>
   <div><small>{connectivity.proposal.changes[selectedJunction].reason} · {connectivity.proposal.changes[selectedJunction].distance_px.toFixed(1)}px</small></div>
   <div className="row" style={{marginTop:6}}>
    <button onClick={()=>applySelectedJunction(selectedJunction)}>Apply this junction</button>
    <button className="secondary" onClick={()=>setSelectedJunction(null)}>Keep unchanged</button>
   </div>
  </div>}
  <small>Click a cyan endpoint marker on the plan to inspect one junction. Perpendicular corner endpoints move together.</small>
 <button disabled={connectivity.proposal.changes.length===0&&connectivity.proposal.removed_starter_ids.length===0} onClick={applyConnections}>Apply preview to unsaved draft</button>
 <button className="secondary" onClick={()=>setConnectivity(null)}>Discard preview</button>
 </div>
 <small>Dashed cyan arrows show short endpoint movements. Existing approved walls, openings and rooms are kept. No new partitions are invented.</small>
 </div>}
 </div>}
 {view==='2d'&&geometry.walls.length>0&&<div style={{border:'1px solid #cbd5e1',padding:10,borderRadius:10,marginBottom:12}}>
 <div className="row" style={{justifyContent:'space-between'}}>
 <strong>Reviewed doors and windows</strong>
 <button className="secondary" disabled={associationBusy} onClick={()=>void previewOpeningAssociations()}>
 {associationBusy?'Checking…':'Preview opening hosts'}</button>
 </div>
 {association&&<div style={{marginTop:6}}>
 <small>{association.proposed} provisional host matches · {association.unresolved} unresolved. Cyan = proposed; orange = needs review. Nothing saved or cut in 3D.</small>
 <button className="secondary" onClick={()=>setAssociation(null)}>Hide opening preview</button>
 </div>}
 </div>}
 {view==='2d'&&r2s&&<div className="notice" style={{marginBottom:12}}>
 <strong>Raster2Seq · {r2s.rooms.length} rooms · {r2s.opening_symbols.length} opening symbols</strong>
 <p>Orange dashed polygons = Raster2Seq rooms; orange/cyan small polygons = its door/window hypotheses. Compare with YOLO/Yytsi walls. This is a read-only overlay, not a verified 3D structure.</p>
 <small>Checkpoint: {r2s.metadata.checkpoint} · Source layout v{r2s.base_layout_version}</small>
 </div>}
 {view==='2d'&&unified&&<details style={{marginBottom:10}}>
 <summary style={{cursor:'pointer',fontSize:13,color:'#475569'}}>Extraction diagnostics · {unified.comparison.agreed_candidates} agreed · {unified.comparison.yytsi_only_candidates} mask-only</summary>
 <div className="notice" style={{marginTop:8}}>
 <small>YOLO walls {unified.comparison.yolo_wall_boxes} · segmentation axes {unified.comparison.mask_lines} · disconnected components {unified.comparison.topology.disconnected_components}. All proposals require review.</small>
 {unified.yolo_error&&<p role="alert">{unified.yolo_error}</p>}
 <label><input type="checkbox" checked={showComparisonBoxes} onChange={e=>setShowComparisonBoxes(e.target.checked)}/> YOLO boxes</label>
 <label><input type="checkbox" checked={showSegmentationOverlay} onChange={e=>setShowSegmentationOverlay(e.target.checked)}/> Segmentation mask</label>
 <a href={`${API}/blueprints/${id}/training-export`} target="_blank" rel="noreferrer">Export annotation history</a>
 </div>
 </details>}
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
 selectedWall?'Drag the green endpoint handles on the selected wall. Save corrected draft when finished.':'Click any blue saved wall to select it and drag its green endpoints, or select an orange/cyan opening detection to review.'}
 </div>}
 {view==='2d'&&<details style={{marginBottom:12}}><summary>Research tools and model diagnostics (optional)</summary>
 <div className="row" style={{flexWrap:'wrap',marginTop:8}}>
 <button className="secondary" disabled={r2sBusy||busy} onClick={()=>void compareRaster2Seq()}>
 {r2sBusy?'Running Raster2Seq…':'Compare Raster2Seq rooms (experimental)'}</button>
 {r2s&&<label><input type="checkbox" checked={r2sVisible}
 onChange={e=>setR2sVisible(e.target.checked)}/> Show Raster2Seq room polygons ({r2s.rooms.length})</label>}
 {r2sStatus&&<small role="status">{r2sStatus}</small>}
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
 <label><input type="checkbox" checked={showLegacyRoomOutline}
 onChange={e=>setShowLegacyRoomOutline(e.target.checked)}/> Show/edit legacy room outline</label>
 <label title="Legacy OpenCV research candidates. Use model wall review above for training."><input type="checkbox" checked={showSuggestions} onChange={e=>setShowSuggestions(e.target.checked)}/> Legacy line hints ({suggestions.length}/{evidence?.candidates.length??0})</label>
 <select value={reviewScope} onChange={e=>setReviewScope(e.target.value as 'all'|'near')} aria-label="Candidate filter">
 <option value="all">All detections</option><option value="near">Near current outline</option></select>
 <label><input type="checkbox" checked={showRaw} onChange={e=>setShowRaw(e.target.checked)}/> Raw lines ({evidence?.segments.length??0})</label></details>
 </div></details>}
</details>
 <details className="panel"><summary>Scale, dimensions and selected geometry</summary><div className="stack"><div className="panel stack"><h2>Geometry</h2>
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
 <details><summary>Advanced: wall graph health</summary>
 <button className="secondary" disabled={busy} onClick={()=>void proposeRooms()}>Propose connected rooms</button>
 <button className="secondary" onClick={()=>void inspectTopology()}>Inspect saved wall connections</button>
 <button className="secondary" onClick={()=>void inspectSharedGraph()}>Inspect shared junction graph</button>
 {sharedGraph&&<div className="stack">
 <small>Shared graph v{sharedGraph.layout_version}: {sharedGraph.graph.nodes.length} nodes · {sharedGraph.graph.edges.length} edges · {sharedGraph.graph.disconnected_components} groups · {sharedGraph.graph.dangling_nodes} loose nodes</small>
 {sharedGraph.graph.warnings.map((warning,i)=><div key={i} className="notice">{warning}</div>)}
 </div>}
 {topology&&<div className="stack">
 <small>{topology.wall_count} walls · {topology.junction_count} joined endpoints · {topology.disconnected_components} groups · {topology.dangling_endpoints} loose ends · {topology.crossing_pairs.length} crossings</small>
 {topology.notes.map((note,i)=><div className="notice" key={i}>{note}</div>)}
 </div>}
 </details>
 {geometry.warnings.some(w=>w.includes('Starter geometry'))&&<div className="notice">
 Starter rectangle is a placeholder, not extracted architecture.
 <button className="secondary" onClick={removeUntouchedStarterWalls}>Remove untouched starter outline</button>
 </div>}
 <h2>Wall corrections</h2>
 {selectedWall?<div className="stack">
 <small>Selected {selectedWall}: drag the green endpoint handles in the plan. Changes appear in 3D.</small>
 <button className="secondary" onClick={()=>removeWall(selectedWall)}>Reject / delete selected wall</button>
 <button className="secondary" onClick={()=>setSelectedWall(null)}>Finish correction</button>
 </div>:<small>Choose Edit wall endpoints, click any stored wall on the plan (including reviewed YOLO and mask walls), and drag its green endpoint handles. Save corrected draft to persist.</small>}
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
 </div></div></details></div>}
 </main></div>;
}
