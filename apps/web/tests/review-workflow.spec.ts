import {draftHistory,emptyHistory} from '../lib/draftHistory';
import {moveSharedJunction} from '../lib/geometryEditing';
import {test,expect,Page} from '@playwright/test';
const geometry={width_px:300,height_px:200,px_per_meter:50,scale_source:'user_confirmed',structure_reviewed:false,rooms:[],warnings:[],openings:[] as any[],walls:[{id:'a',start:{x:20,y:20},end:{x:220,y:20},thickness_m:.15,height_m:2.8,inferred:true}]};
const opening={id:'opening-1',source_detection_id:'window-1',kind:'window',wall_id:'a',offset_m:1,width_m:1,height_m:1,sill_m:1,inferred:true};
async function api(page:Page,{graph=false,stale=false,unresolved=false}={}){
 const state={saved:[] as any[],mergedIds:null as null|string[],applied:false};
 const projected={...geometry,openings:[opening],walls:[...geometry.walls,{...geometry.walls[0],id:'b',start:{x:220,y:20},end:{x:220,y:180}}]};
 let layout={id:'layout',blueprint_id:'test',version:1,verified:false,geometry};
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
  if(path.endsWith('/evidence'))return reply({scale_suggestions:[],segments:[],candidates:[],labels:[],vector_pdf:false,ocr_available:false});
  if(path.endsWith('/canonical-plan/revisions/latest'))return graph?reply({stale:false,revision:{id:'revision',version:2,parent_revision_id:'parent',graph:{...projected,nodes:[{id:'n1',point:{x:20,y:20}},{id:'n2',point:{x:220,y:20}},{id:'n3',point:{x:220,y:180}}],walls:[{id:'a',start_node_id:'n1',end_node_id:'n2'},{id:'b',start_node_id:'n2',end_node_id:'n3'}],pending_openings:[]}}}):reply({detail:'No canonical plan revision yet'},404);
  if(path.endsWith('/canonical-plan/revisions/revision/geometry'))return reply({geometry:projected});
  if(path.endsWith('/canonical-plan/revisions/revision/draft'))return stale?reply({detail:'Saved layout changed; reload'},409):reply({saved:false,geometry:projected});
  if(path.endsWith('/compare-extraction'))return reply({
   base_layout_version:1,proposal:geometry,candidates:[],opening_hints:[{candidate_id:'window-1',kind:'window',x1:70,y1:16,x2:120,y2:24,source_confidence:.9,wall_id:null,fraction:null,reason:'Review host'}],
   input_manifest:{source_preview_sha256:'a'.repeat(64)},comparison:{agreed_candidates:0,yytsi_only_candidates:0,yolo_only_candidates:0,topology:{disconnected_components:1,dangling_endpoints:2}},
   geometry_review:{suggestions:[],explanation:'',auto_applied:false},detections:null,segmentation:{provider:'test'},yolo_error:null,mask_overlay_png_base64:'',saved:false});
  if(path.endsWith('/fusion-draft/merge')){state.mergedIds=route.request().postDataJSON().candidate_ids;return reply({saved:false,geometry,added:0,already_present:0,ignored:0,layout_version:1});}
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
