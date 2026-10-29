import {draftHistory,emptyHistory} from '../lib/draftHistory';
import {moveSharedJunction} from '../lib/geometryEditing';
import {test,expect,Page} from '@playwright/test';
const geometry={width_px:300,height_px:200,px_per_meter:50,scale_source:'user_confirmed',structure_reviewed:false,rooms:[],warnings:[],openings:[] as any[],walls:[{id:'a',start:{x:20,y:20},end:{x:220,y:20},thickness_m:.15,height_m:2.8,inferred:true}]};
const opening={id:'opening-1',source_detection_id:'window-1',kind:'window',wall_id:'a',offset_m:1,width_m:1,height_m:1,sill_m:1,inferred:true};
async function api(page:Page,{graph=false,stale=false,unresolved=false,rooms=false,partitionOpening=false,autoConnect=false}={}){
 const state={saved:[] as any[],mergedIds:null as null|string[],applied:false};
 const projected={...geometry,openings:[opening],walls:[...geometry.walls,{...geometry.walls[0],id:'b',start:{x:220,y:20},end:{x:220,y:180}}]};
 const roomGeometry={...geometry,walls:[
  {id:'top',start:{x:10,y:10},end:{x:290,y:10}},{id:'right',start:{x:290,y:10},end:{x:290,y:190}},
  {id:'bottom',start:{x:290,y:190},end:{x:10,y:190}},{id:'left',start:{x:10,y:190},end:{x:10,y:10}},
  {id:'partition',start:{x:150,y:10},end:{x:150,y:190}}].map(w=>({...geometry.walls[0],...w})),openings:partitionOpening?[{...opening,wall_id:'partition'}]:[]};
 let layout={id:'layout',blueprint_id:'test',version:1,verified:false,geometry:rooms?roomGeometry:geometry};
 await page.route('http://localhost:8000/**',async route=>{
  const path=new URL(route.request().url()).pathname;
  const method=route.request().method();
  const reply=(body:unknown,status=200)=>route.fulfill({status,headers:{'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'Content-Type','Access-Control-Allow-Methods':'GET, POST, OPTIONS'},contentType:'application/json',body:JSON.stringify(body)});
  if(method==='OPTIONS')return reply({});
  if(path.endsWith('/preview'))return route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="300" height="200"/>'});
  if(path.endsWith('/layout')){
   if(method==='POST'){const body=route.request().postDataJSON();state.saved.push(body);layout={...layout,version:layout.version+1,geometry:body.geometry};}
   return reply(layout);
  }
  if(path.endsWith('/quality')&&rooms){
   const draft=route.request().postDataJSON().geometry;
   const split=draft.walls.some((w:any)=>w.id==='partition');
   const face=(id:string,x0:number,x1:number,ids:string[])=>({id,points:[{x:x0,y:10},{x:x1,y:10},{x:x1,y:190},{x:x0,y:190}],source_wall_ids:ids,shared_source_wall_ids:split?['partition']:[],verified:false});
   return reply({structural_issues:[],metric_issues:['Review structure'],ready_for_metric_scene:false,loose_endpoints:[],room_faces:split?[face('left-face',10,150,['top','partition','bottom','left']),face('right-face',150,290,['top','right','bottom','partition'])]:[face('combined',10,290,['top','right','bottom','left'])]});
  }
  if(path.endsWith('/evidence'))return reply({scale_suggestions:[],segments:[],candidates:[],labels:[],vector_pdf:false,ocr_available:false});
  if(path.endsWith('/canonical-plan/revisions/latest'))return graph?reply({stale:false,revision:{id:'revision',version:2,parent_revision_id:'parent',graph:{...projected,nodes:[{id:'n1',point:{x:20,y:20}},{id:'n2',point:{x:220,y:20}},{id:'n3',point:{x:220,y:180}}],walls:[{id:'a',start_node_id:'n1',end_node_id:'n2'},{id:'b',start_node_id:'n2',end_node_id:'n3'}],pending_openings:[]}}}):reply({detail:'No canonical plan revision yet'},404);
  if(path.endsWith('/canonical-plan/revisions/revision/geometry'))return reply({geometry:projected});
  if(path.endsWith('/canonical-plan/revisions/revision/draft'))return stale?reply({detail:'Saved layout changed; reload'},409):reply({saved:false,geometry:projected});
  if(path.endsWith('/compare-extraction'))return reply({
   base_layout_version:1,proposal:geometry,candidates:[],opening_hints:[{candidate_id:'window-1',kind:'window',x1:70,y1:16,x2:120,y2:24,source_confidence:.9,wall_id:null,fraction:null,reason:'Review host'}],
   input_manifest:{source_preview_sha256:'a'.repeat(64)},comparison:{agreed_candidates:0,yytsi_only_candidates:0,yolo_only_candidates:0,topology:{disconnected_components:1,dangling_endpoints:2}},
   geometry_review:{suggestions:[],explanation:'',auto_applied:false},detections:null,segmentation:{provider:'test'},yolo_error:null,mask_overlay_png_base64:'',saved:false});
  if(path.endsWith('/fusion-draft/merge')){state.mergedIds=route.request().postDataJSON().candidate_ids;return reply({saved:false,geometry,added:0,already_present:0,ignored:0,layout_version:1});}
  if(path.endsWith('/connectivity/automatic')&&autoConnect){const g=route.request().postDataJSON().geometry;return reply({geometry:{...g,walls:[...g.walls,{...g.walls[0],id:'joined'}]},changes:[{wall_id:'joined'}],remaining_loose_endpoints:2});}
  if(path.endsWith('/opening-review/draft')){state.applied=true;return reply({geometry:unresolved?geometry:{...geometry,openings:[opening]},status:unresolved?'unresolved':'added'});}
  if(path.endsWith('/fusion-reviews'))return reply(method==='GET'?[]:{id:'review'});
  return reply([]);
 });
 page.on('dialog',d=>d.accept());
 await page.goto('/blueprint/test');
 await expect(page.getByRole('button',{name:'3 · Save corrected draft',exact:true})).toBeVisible();
 return state;
}

test('opening-only classifications must be applied before they enter the saved draft',async({page})=>{
 const state=await api(page);
 await page.getByRole('button',{name:'1 · Extract and compare',exact:true}).click();
 await page.getByRole('button',{name:'Openings (1)',exact:true}).click();
 await page.getByRole('button',{name:'Classify as window',exact:true}).click();
 await expect(page.getByText('1 / 1 classified',{exact:true})).toBeVisible();
 expect(state.applied).toBe(false);
 await page.getByRole('button',{name:'2 · Apply reviewed walls + openings',exact:true}).click();
 await expect(page.getByText(/Main draft: 1 walls · 1 physical openings/)).toBeVisible();
 expect(state.mergedIds).toEqual([]);
 await page.getByRole('button',{name:'3 · Save corrected draft',exact:true}).click();
 await expect.poll(()=>state.saved.length).toBe(1);
 expect(state.saved[0].geometry.openings).toEqual([opening]);
});

test('repaired graph feeds the main draft and protects unsaved changes',async({page})=>{
 const state=await api(page,{graph:true});
 await page.getByText('Repair walls, gaps and opening hosts',{exact:true}).click();
 await page.getByText('Repair connected geometry',{exact:true}).click();
 const use=page.getByRole('button',{name:'Use repaired graph in main 2D/3D draft',exact:true});
 await expect(use).toBeEnabled();await use.click();
 await expect(use).toBeDisabled();
 await expect(page.getByText('Repaired graph loaded into the main 2D/3D draft. Save corrected draft to persist.',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'3 · Save corrected draft',exact:true}).click();
 await expect.poll(()=>state.saved.length).toBe(1);
 expect(state.saved[0].geometry.walls).toHaveLength(2);
 expect(state.saved[0].geometry.openings).toEqual([opening]);
});

test('stale graph handoff does not overwrite the main draft',async({page})=>{
 const state=await api(page,{graph:true,stale:true});
 await page.getByText('Repair walls, gaps and opening hosts',{exact:true}).click();
 await page.getByText('Repair connected geometry',{exact:true}).click();
 await page.getByRole('button',{name:'Use repaired graph in main 2D/3D draft',exact:true}).click();
 await expect(page.getByText(/409: Saved layout changed/)).toBeVisible();
 await page.getByRole('button',{name:'3 · Save corrected draft',exact:true}).click();
 await expect.poll(()=>state.saved.length).toBe(1);
 expect(state.saved[0].geometry.walls).toHaveLength(1);
 expect(state.saved[0].geometry.openings).toHaveLength(0);
});

test('unresolved classifications remain visibly unresolved rather than fake cutouts',async({page})=>{
 const state=await api(page,{unresolved:true});
 await page.getByRole('button',{name:'1 · Extract and compare',exact:true}).click();
 await page.getByRole('button',{name:'Openings (1)',exact:true}).click();
 await page.getByRole('button',{name:'Classify as window',exact:true}).click();
 await page.getByRole('button',{name:'2 · Apply reviewed walls + openings',exact:true}).click();
 await expect(page.getByText(/window window-1: unresolved/)).toBeVisible();
 await expect(page.getByText(/Main draft: 1 walls · 0 physical openings/)).toBeVisible();
 expect(state.applied).toBe(true);
});

test('shared endpoint editing moves all incident walls and protects hosted openings',async()=>{
 const connected={...geometry,walls:[...geometry.walls,{...geometry.walls[0],id:'b',start:{x:220,y:20},end:{x:220,y:180}}]};
 expect(moveSharedJunction(connected as any,'a','end',{x:220,y:20})).toBe(connected);
 const moved=moveSharedJunction(connected as any,'a','end',{x:230,y:20});
 expect(moved.walls[0].end).toEqual({x:230,y:20});
 expect(moved.walls[1].start).toEqual({x:230,y:20});
 expect(connected.walls[0].end).toEqual({x:220,y:20});
 expect(()=>moveSharedJunction({...connected,openings:[opening]} as any,'a','end',{x:230,y:20})).toThrow(/openings/);
 expect(()=>moveSharedJunction(connected as any,'a','end',{x:20,y:20})).toThrow(/collapse/);
});


test('draft undo groups drag frames and redo is invalidated by a new edit',()=>{
 const first=geometry as any, second={...first,structure_reviewed:false},third={...second,walls:[]};
 let h=draftHistory(emptyHistory,{type:'reset',value:first});
 h=draftHistory(h,{type:'begin'});
 h=draftHistory(h,{type:'set',value:second});h=draftHistory(h,{type:'set',value:third});
 h=draftHistory(h,{type:'end'});
 expect(h.past).toEqual([first]);
 h=draftHistory(h,{type:'undo'});expect(h.present).toBe(first);
 h=draftHistory(h,{type:'redo'});expect(h.present).toBe(third);
 h=draftHistory(h,{type:'undo'});h=draftHistory(h,{type:'set',value:second});
 expect(h.future).toHaveLength(0);
 h=draftHistory(h,{type:'reset',value:third});expect(h.past).toHaveLength(0);
});

test('editor starts on the plan with research controls collapsed and reversible draft application',async({page})=>{
 await api(page);
 await expect(page.getByRole('heading',{name:'Plan editor',exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:'Save uncorrected model baseline',exact:true})).not.toBeVisible();
 await expect(page.getByRole('button',{name:'Reload graph',exact:true})).not.toBeVisible();
 await page.getByRole('button',{name:'1 · Extract and compare',exact:true}).click();
 await page.getByRole('button',{name:'Openings (1)',exact:true}).click();
 await page.getByRole('button',{name:'Classify as window',exact:true}).click();
 await page.getByRole('button',{name:'2 · Apply reviewed walls + openings',exact:true}).click();
 await expect(page.getByText(/Main draft: 1 walls · 1 physical openings/)).toBeVisible();
 await page.getByRole('button',{name:'Undo draft edit',exact:true}).click();
 await expect(page.getByText(/Main draft: 1 walls · 0 physical openings/)).toBeVisible();
 await page.getByRole('button',{name:'Redo draft edit',exact:true}).click();
 await expect(page.getByText(/Main draft: 1 walls · 1 physical openings/)).toBeVisible();
 await page.screenshot({path:'test-results/editor-clean-flow.png',fullPage:true});
});


test('room-first review selects on plan, removes a shared partition and undoes it',async({page})=>{
 const state=await api(page,{rooms:true});
 const region=page.getByRole('button',{name:'Review room region 1',exact:true});
 await expect(region).toBeVisible();await region.focus();await region.press('Enter');
 await expect(page.getByText('Selected enclosed region',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Boundary 2 · shared partition',exact:true}).click();
 await expect(page.getByText('Selected boundary',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Remove shared partition 2',exact:true}).click();
 await expect(page.getByText('1 enclosed regions · 0 loose endpoints',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Undo draft edit',exact:true}).click();
 await expect(page.getByText('2 enclosed regions · 0 loose endpoints',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'3 · Save corrected draft',exact:true}).click();
 await expect.poll(()=>state.saved.length).toBe(1);expect(state.saved[0].geometry.walls).toHaveLength(5);
 await expect(page.getByText('2 enclosed regions · 0 loose endpoints',{exact:true})).toBeVisible();
 await region.click();
 await page.screenshot({path:'test-results/room-first-review.png',fullPage:true});
 await page.setViewportSize({width:390,height:844});
 await expect(page.getByText('Selected enclosed region',{exact:true})).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
});

test('room merge cannot silently delete a hosted opening',async({page})=>{
 await api(page,{rooms:true,partitionOpening:true});
 await page.getByRole('button',{name:'Review room region 1',exact:true}).click();
 await expect(page.getByRole('button',{name:'Remove shared partition 2',exact:true})).toBeDisabled();
});


test('reviewed draft receives automatic connectivity corrections',async({page})=>{
 const state=await api(page,{autoConnect:true});
 await page.getByRole('button',{name:'1 · Extract and compare',exact:true}).click();
 await page.getByRole('button',{name:'Openings (1)',exact:true}).click();
 await page.getByRole('button',{name:'Classify as window',exact:true}).click();
 await page.getByRole('button',{name:'2 · Apply reviewed walls + openings',exact:true}).click();
 await expect(page.getByText(/Automatically adjusted 1 short/)).toBeVisible();
 await page.getByRole('button',{name:'3 · Save corrected draft',exact:true}).click();
 await expect.poll(()=>state.saved.length).toBe(1);
 expect(state.saved[0].geometry.walls).toHaveLength(2);
 expect(state.saved[0].geometry.openings).toHaveLength(1);
});
