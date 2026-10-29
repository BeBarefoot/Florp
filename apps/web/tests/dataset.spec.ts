import {test,expect} from '@playwright/test';
test('mask annotation autosaves and a ready error preserves the draft',async({page})=>{
 let annotation:any=null;
 await page.route('http://localhost:8000/**',async route=>{
  const path=new URL(route.request().url()).pathname;
  const reply=(body:unknown,status=200)=>route.fulfill({status,contentType:'application/json',headers:{'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'Content-Type','Access-Control-Allow-Methods':'GET, PUT, OPTIONS'},body:JSON.stringify(body)});
  if(route.request().method()==='OPTIONS')return reply({});
  if(path==='/dataset/cases')return reply([{id:'plan',name:'sample.png',width_px:300,height_px:200,annotation}]);
  if(path==='/dataset/cases/plan'){
   const b=route.request().postDataJSON();
   if(b.complete)return reply({detail:'Two distinct reviewers required'},422);
   annotation={...b,revision:b.expected_revision+1,status:'draft'};return reply(annotation);
  }
  if(path.endsWith('/preview'))return route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="300" height="200"/>'});
  return reply([]);
 });
 await page.goto('/dataset');
 await page.getByRole('button',{name:'sample.png · unlabeled'}).click();
 await expect(page.getByRole('status')).toContainText('Automatic detection is unavailable');
 const canvas=page.getByLabel('Training mask editor');
 const box=await canvas.boundingBox();if(!box)throw Error('Missing canvas');
 for(const [x,y] of [[.1,.1],[.5,.1],[.5,.3],[.1,.3]])await page.mouse.click(box.x+x*box.width,box.y+y*box.height);
 await page.getByRole('button',{name:'Finish polygon',exact:true}).click();
 await expect.poll(()=>annotation?.objects.length).toBe(1);
 await expect(page.getByText('Server revision 1',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Whole plan reviewed · Mark ready'}).click();
 await expect(page.getByRole('status')).toContainText('Two distinct reviewers');
 expect(annotation.status).toBe('draft');
});

test('inspection is collapsed and never pushes the plan off screen',async({page})=>{
 const issues=Array.from({length:300},(_,i)=>({kind:'short_wall',object:i}));
 await page.route('http://localhost:8000/**',async route=>{
  const path=new URL(route.request().url()).pathname;
  const reply=(body:unknown)=>route.fulfill({contentType:'application/json',headers:{'Access-Control-Allow-Origin':'*'},body:JSON.stringify(body)});
  if(path.endsWith('/preview'))return route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="300" height="200"/>'});
  if(path==='/dataset/cases')return reply([{id:'plan',name:'plan.png',width_px:300,height_px:200,annotation:{revision:1,group_id:'g',split:'train',reviewer:'',independent_reviewer:'',complete:false,rights_confirmed:false,objects:[],status:'draft',reconstruction:{issues}}}]);
  return reply([]);
 });
 await page.goto('/dataset');await page.getByRole('button',{name:'plan.png · draft'}).click();
 await expect(page.getByLabel('Training mask editor')).toBeVisible();
 await expect(page.getByRole('button',{name:'Short walls · 1 object'}).first()).toBeHidden();
 await page.getByText('Advanced diagnostics (300)').click();
 await page.getByText('Short walls (300)').click();
 await expect(page.getByRole('button',{name:'Short walls · 1 object'})).toHaveCount(20);
 await page.getByRole('button',{name:'Next',exact:true}).click();
 await expect(page.getByText('2 / 15')).toBeVisible();
});

test('nearby warnings share a marker and all issue types remain selectable',async({page})=>{
 const objects=[{kind:'wall',polygon:[[10,10],[20,10],[20,20],[10,20]]},{kind:'wall',polygon:[[11,11],[21,11],[21,21],[11,21]]}];
 const issues=[{kind:'short_wall',object:0},{kind:'complex_wall_mask',object:1}];
 await page.route('http://localhost:8000/**',async route=>{
  const path=new URL(route.request().url()).pathname;
  if(path.endsWith('/preview'))return route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="300" height="200"/>'});
  const value=path==='/dataset/cases'?[{id:'plan',name:'plan.png',width_px:300,height_px:200,annotation:{revision:1,group_id:'g',split:'train',reviewer:'',independent_reviewer:'',complete:false,rights_confirmed:false,objects,status:'draft',reconstruction:{issues}}}]:[];
  return route.fulfill({contentType:'application/json',headers:{'Access-Control-Allow-Origin':'*'},body:JSON.stringify(value)});
 });
 await page.goto('/dataset');await page.getByRole('button',{name:'plan.png · draft'}).click();
 const marker=page.getByRole('button',{name:'Inspection marker, 2 regions'});await expect(marker).toHaveCount(0);
 await page.getByRole('button',{name:'Start review'}).click();
 await expect(page.getByText('Selected: wall')).toBeVisible();
 await expect(page.getByRole('button',{name:'False detection'})).toBeVisible();
});

test('snapshot readiness explains drafts and missing splits',async({page})=>{
 await page.route('http://localhost:8000/**',async route=>{
  const path=new URL(route.request().url()).pathname;
  const value=path==='/dataset/cases'?[{id:'plan',name:'draft.png',width_px:300,height_px:200,annotation:{revision:1,group_id:'g',split:'train',reviewer:'',independent_reviewer:'',complete:false,rights_confirmed:false,objects:[],status:'draft'}}]:[];
  return route.fulfill({contentType:'application/json',headers:{'Access-Control-Allow-Origin':'*'},body:JSON.stringify(value)});
 });
 await page.goto('/dataset');await page.getByText('4. Dataset Snapshots').click();
 await expect(page.getByText('0 of 1 plans ready')).toBeVisible();
 await expect(page.getByText(/Review a plan from the Annotation Queue/)).toBeVisible();
 await expect(page.getByText(/Train 0 · Validation 0 · Test 0/)).toBeVisible();
});

test('import opens the plan only after it is visible in the queue',async({page})=>{
 let imported=false;
 await page.route('http://localhost:8000/**',async route=>{
  const path=new URL(route.request().url()).pathname;
  const reply=(body:unknown)=>route.fulfill({contentType:'application/json',headers:{'Access-Control-Allow-Origin':'*','Access-Control-Allow-Methods':'GET, POST, OPTIONS'},body:JSON.stringify(body)});
  if(route.request().method()==='OPTIONS')return reply({});
  if(path==='/dataset/import'){imported=true;return reply({case_ids:['new-plan'],pages:1,status:'completed'})}
  if(path==='/dataset/cases')return reply(imported?[{id:'new-plan',name:'plan.png',width_px:300,height_px:200,annotation:null}]:[]);
  if(path.endsWith('/preview'))return route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="300" height="200"/>'});
  return reply([]);
 });
 await page.goto('/dataset');
 await page.locator('input[type=file]').first().setInputFiles({name:'plan.png',mimeType:'image/png',buffer:Buffer.from('fixture')});
 await expect(page.getByRole('button',{name:'plan.png · unlabeled'})).toBeVisible();
 await expect(page.getByRole('heading',{name:'plan.png'})).toBeVisible();
 await expect(page.getByRole('status')).toContainText('Automatic detection is unavailable');
});

test('calibration previews over a finding and saves the chosen distance',async({page})=>{
 let saved:any=null;
 const ann={revision:1,group_id:'g',split:'train',reviewer:'',independent_reviewer:'',complete:false,rights_confirmed:false,objects:[{kind:'wall',polygon:[[20,20],[250,20],[250,32],[20,32]]}],status:'draft',reconstruction:{geometry:{width_px:300,height_px:200,walls:[{id:'w',start:{x:20,y:26},end:{x:250,y:26}}],rooms:[],openings:[]},issues:[{kind:'complex_wall_mask',object:0}]}};
 await page.route('http://localhost:8000/**',async route=>{
  const path=new URL(route.request().url()).pathname;const reply=(body:unknown)=>route.fulfill({contentType:'application/json',headers:{'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'Content-Type','Access-Control-Allow-Methods':'GET, PUT, OPTIONS'},body:JSON.stringify(body)});
  if(route.request().method()==='OPTIONS')return reply({});
  if(path==='/dataset/cases')return reply([{id:'plan',name:'plan.png',width_px:300,height_px:200,annotation:saved||ann}]);
  if(path==='/dataset/cases/plan'){const b=route.request().postDataJSON();saved={...ann,...b,revision:b.expected_revision+1,status:'draft'};return reply(saved)}
  if(path.endsWith('/preview'))return route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="300" height="200"/>'});return reply([]);
 });
 await page.goto('/dataset');await page.getByRole('button',{name:'plan.png · draft'}).click();
 await page.getByRole('button',{name:'Calibrate known length'}).click();
 const svg=page.getByLabel('Training mask editor');const box=await svg.boundingBox();if(!box)throw Error('no canvas');
 // SVG letterboxing can introduce padding: use its actual SVG-to-screen transform.
 const xy=await svg.evaluate((el:SVGSVGElement)=>{const m=el.getScreenCTM()!;return [[20*m.a+m.e,26*m.d+m.f],[220*m.a+m.e,26*m.d+m.f]]});
 await page.mouse.click(xy[0][0],xy[0][1]);await page.mouse.move(xy[1][0],xy[1][1]);
 await expect(svg.locator('polyline')).toHaveAttribute('points',/ /);
 await page.mouse.click(xy[1][0],xy[1][1]);await page.getByLabel('Known distance in meters').fill('4');await page.getByRole('button',{name:'Confirm scale'}).click();
 await expect.poll(()=>saved?.px_per_meter).toBeCloseTo(50,0);
});

test('review decisions are saved, can be undone, and reclassify a finding',async({page})=>{
 let saved:any=null;
 const ann={revision:1,group_id:'g',split:'train',reviewer:'',independent_reviewer:'',complete:false,rights_confirmed:false,objects:[{kind:'wall',polygon:[[20,20],[250,20],[250,32],[20,32]]}],status:'draft',reconstruction:{geometry:{width_px:300,height_px:200,walls:[{id:'w',start:{x:20,y:26},end:{x:250,y:26}}],rooms:[],openings:[]},issues:[{kind:'complex_wall_mask',object:0}]}};
 await page.route('http://localhost:8000/**',async route=>{
  const path=new URL(route.request().url()).pathname;const reply=(body:unknown)=>route.fulfill({contentType:'application/json',headers:{'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'Content-Type','Access-Control-Allow-Methods':'GET, PUT, OPTIONS'},body:JSON.stringify(body)});
  if(route.request().method()==='OPTIONS')return reply({});
  if(path==='/dataset/cases')return reply([{id:'plan',name:'plan.png',width_px:300,height_px:200,annotation:saved||ann}]);
  if(path==='/dataset/cases/plan'){const b=route.request().postDataJSON();saved={...ann,...b,revision:b.expected_revision+1,status:'draft'};return reply(saved)}
  if(path.endsWith('/preview'))return route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="300" height="200"/>'});return reply([]);
 });
 await page.goto('/dataset');await page.getByRole('button',{name:'plan.png · draft'}).click();await page.getByRole('button',{name:'Start review'}).click();
 await page.getByRole('button',{name:'False detection'}).click();await expect.poll(()=>saved?.excluded_objects).toEqual([0]);
 await page.getByRole('button',{name:'Undo masks'}).click();await expect.poll(()=>saved?.excluded_objects||[]).toEqual([]);
 await page.getByRole('button',{name:'Start review'}).click();await page.getByRole('button',{name:'Window',exact:true}).click();await expect.poll(()=>saved?.objects[0].kind).toBe('window');
});

test('newly opened plan automatically shows reconstructed wall lines',async({page})=>{
 const annotation={revision:1,group_id:'g',split:'train',reviewer:'',independent_reviewer:'',complete:false,rights_confirmed:false,objects:[{kind:'wall',polygon:[[20,20],[250,20],[250,32],[20,32]]}],status:'draft',reconstruction:{geometry:{width_px:300,height_px:200,walls:[{id:'w',start:{x:20,y:26},end:{x:250,y:26}}],rooms:[],openings:[]},issues:[{kind:'complex_wall_mask',object:0}]}};
 await page.route('http://localhost:8000/**',async route=>{
  const path=new URL(route.request().url()).pathname;
  if(path.endsWith('/preview'))return route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="300" height="200"/>'});
  const data=path==='/dataset/cases'?[{id:'plan',name:'plan.png',width_px:300,height_px:200,annotation:null}]:path==='/dataset/cases/plan/seed'?{annotation,warning:'Review model proposals'}:[];
  return route.fulfill({contentType:'application/json',headers:{'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'Content-Type','Access-Control-Allow-Methods':'GET, POST, OPTIONS'},body:JSON.stringify(data)});
 });
 await page.goto('/dataset');await page.getByRole('button',{name:'plan.png · unlabeled'}).click();
 await expect(page.getByRole('status')).toContainText('Review model proposals');
 await expect(page.getByLabel('Training mask editor').locator('line[stroke="#147eb1"]')).toHaveCount(1);
 await expect(page.getByLabel('Training mask editor').locator('circle')).toHaveCount(0);
});

test('review controls wait for an in-flight save instead of dropping the next decision',async({page})=>{
 let release!:()=>void;const gate=new Promise<void>(r=>{release=r});let saving=false;
 const ann={revision:1,group_id:'g',split:'train',reviewer:'',independent_reviewer:'',complete:false,rights_confirmed:false,objects:[{kind:'wall',polygon:[[20,20],[100,20],[100,30],[20,30]]},{kind:'window',polygon:[[140,20],[160,20],[160,30],[140,30]]}],status:'draft',reconstruction:{geometry:{width_px:300,height_px:200,walls:[],rooms:[],openings:[]},issues:[{kind:'short_wall',object:0},{kind:'opening_host',object:1}]}};
 await page.route('http://localhost:8000/**',async route=>{
  const path=new URL(route.request().url()).pathname;const reply=(body:unknown)=>route.fulfill({contentType:'application/json',headers:{'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'Content-Type','Access-Control-Allow-Methods':'GET, PUT, OPTIONS'},body:JSON.stringify(body)});
  if(route.request().method()==='OPTIONS')return reply({});
  if(path==='/dataset/cases')return reply([{id:'plan',name:'plan.png',width_px:300,height_px:200,annotation:ann}]);
  if(path==='/dataset/cases/plan'){saving=true;await gate;const b=route.request().postDataJSON();return reply({...ann,...b,revision:2,status:'draft'})}
  if(path.endsWith('/preview'))return route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="300" height="200"/>'});return reply([]);
 });
 await page.goto('/dataset');await page.getByRole('button',{name:'plan.png · draft'}).click();await page.getByRole('button',{name:'Start review'}).click();
 await page.getByRole('button',{name:'False detection'}).click();await expect.poll(()=>saving).toBe(true);
 await expect(page.getByRole('button',{name:'Wall',exact:true})).toBeDisabled();
 release();await expect(page.getByRole('button',{name:'Wall',exact:true})).toBeEnabled();
});
