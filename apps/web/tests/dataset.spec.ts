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
