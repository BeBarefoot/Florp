import {test,expect} from '@playwright/test';
import {regionArea} from '../components/SiteOutline';
import {execFileSync} from 'node:child_process';
import {resolve} from 'node:path';
import {readFileSync,writeFileSync} from 'node:fs';

test('real local PNG/JPEG/PDF extraction, scene persistence and capture',async({page,request},testInfo)=>{
 const api=String(testInfo.config.metadata.api);
 const demo=JSON.parse(execFileSync('uv',['run','--locked','python','scripts/demo_project.py','--api',api],
   {cwd:resolve(__dirname,'../../api'),encoding:'utf8',timeout:90000}));
 expect(demo.blueprints).toHaveLength(3);
 for(const bp of demo.blueprints){
   expect(bp.walls).toBeGreaterThan(0);expect(bp.rooms).toBe(2);
   const review=await request.get(`${api}/blueprints/${bp.id}/plan/review`);
   expect((await review.json()).status).toBe('draft');
 }
 const bid=demo.blueprints[0].id;
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(`/plan/${bid}`);
 await expect(page.getByText('synthetic-plan.png',{exact:true})).toBeVisible();
 const enter=()=>page.locator('.fe-segment button').nth(2).click();
 await enter();
 const map=page.getByLabel('Camera and furniture placement plan');
 async function at(x:number,y:number){
   await map.scrollIntoViewIfNeeded();
   const p=await map.evaluate((el,xy)=>{
     const p=new DOMPoint(...xy).matrixTransform((el as unknown as SVGSVGElement).getScreenCTM()!);
     return {x:p.x,y:p.y};
   },[x,y] as [number,number]);
   await page.mouse.click(p.x,p.y);
 }
 await page.getByRole('button',{name:'Place camera',exact:true}).click();
 await at(250,200);await at(250,450);
 const walk=page.getByRole('group',{name:'Walkthrough'});
 await walk.focus();
 await walk.press('ArrowRight');
 await walk.press('w');
 await page.getByRole('button',{name:'Place object',exact:true}).click();await at(250,350);
 await page.getByLabel('Design prompt').fill('Warm oak bedroom');
 await page.getByRole('button',{name:'Save scene',exact:true}).click();
 await expect(page.getByText('Scene saved.',{exact:true})).toBeVisible();
 async function capture(){
   await page.getByRole('button',{name:'Capture view',exact:true}).click();
   const download=page.waitForEvent('download');
   await page.getByRole('button',{name:'Export render inputs',exact:true}).click();
   const path=await(await download).path();
   return JSON.parse(readFileSync(path!,'utf8'));
 }
 const captureStart=performance.now();
 const original=await capture();
 const captureAndExportMs=Math.round(performance.now()-captureStart);
 await page.getByLabel('Floor finish').selectOption('oak');
 await page.getByRole('button',{name:'Save scene',exact:true}).click();
 await expect(page.getByText('Scene saved.',{exact:true})).toBeVisible();
 const before=await capture();
 expect(before.preview).not.toEqual(original.preview);
 expect(before.depth).toEqual(original.depth);
 expect(before.mask).toEqual(original.mask);

 expect(before.view.yaw).toBe(95);
 expect(before.view.position.y).toBeGreaterThan(200);
 expect(before.planRevision).toBe(2);
 expect(before.architectureReview.status).toBe('draft');
 expect(before.planSnapshot.walls.length).toBeGreaterThan(0);
 expect(before.prompt).toContain('Warm oak bedroom');
 expect(before.depth).toMatch(/^data:image\/png;base64,/);
 await page.reload();await enter();
 await expect(page.getByLabel('Design prompt')).toHaveValue('Warm oak bedroom');
 await expect(page.getByLabel('Floor finish')).toHaveValue('oak');
 const after=await capture();
 expect(after.view).toEqual(before.view);
 expect(after.depth).toEqual(before.depth);
 expect(after.mask).toEqual(before.mask);
 await expect(page.getByRole('button',{name:'Generate preview',exact:true})).toBeDisabled();
 const saved=await(await request.get(`${api}/blueprints/${bid}/scene`)).json();
 expect(saved.config.objects).toHaveLength(1);
 expect(saved.config.views).toHaveLength(1);
 const objects=page.getByRole('region',{name:'Objects in this scene'});
 await objects.getByRole('button',{name:/Remove/}).click();
 await expect(objects.getByRole('button',{name:/Remove/})).toHaveCount(0);
 await page.getByRole('button',{name:'Undo scene edit',exact:true}).click();
 await expect(objects.getByRole('button',{name:/Remove/})).toHaveCount(1);
 expect(errors).toEqual([]);
 await page.screenshot({path:testInfo.outputPath('local-scene.png'),fullPage:true});
 writeFileSync(testInfo.outputPath('workspace.json'),JSON.stringify({workspace:testInfo.config.metadata.workspace,captureAndExportMs,...demo},null,2));
});

test('two floor photos can be reviewed, swapped and reopened',async({page,request},testInfo)=>{
 const api=String(testInfo.config.metadata.api);
 const project=await (await request.post(api+'/projects',{data:{title:'Floor pair'}})).json();
 const png=execFileSync('uv',['run','--locked','python','-c',
   "from scripts.demo_project import fixtures; import sys; sys.stdout.buffer.write(next(fixtures())[2])"],
   {cwd:resolve(__dirname,'../../api')});
 await page.goto('/project/'+project.id);
 await page.getByLabel('Floor plan file').setInputFiles(['second-floor.png','ground-floor.png'].map(name=>({name,mimeType:'image/png',buffer:png})));
 await page.getByRole('button',{name:'Upload plan',exact:true}).click();
 await page.getByRole('button',{name:'Identify floors, garden and stairs'}).click();
 const first=page.getByLabel('First floor (garden level)');
 await expect(first.locator('option:checked')).toHaveText('ground-floor.png');
 await first.selectOption({label:'second-floor.png'});
 const floor=page.getByRole('region',{name:'First floor drawing',exact:true});
 await floor.getByRole('button',{name:'Outline garden'}).click();
 const map=floor.getByLabel('First floor region map');
 for(const position of [{x:10,y:10},{x:60,y:10},{x:60,y:60}])await map.click({position});
 await floor.getByRole('button',{name:'Finish outline'}).click();
 const overlay=page.getByLabel('Floor alignment overlay');
 await overlay.scrollIntoViewIfNeeded();
 const bounds=(await overlay.boundingBox())!;
 const initialTransform=await overlay.locator('[data-floor-layer="upper"]').getAttribute('transform');
 await page.mouse.move(bounds.x+bounds.width/2,bounds.y+bounds.height/2);
 await page.mouse.down();
 await page.mouse.move(bounds.x+bounds.width/2+40,bounds.y+bounds.height/2+20,{steps:4});
 await page.mouse.up();
 await expect(overlay.locator('[data-floor-layer="upper"]')).not.toHaveAttribute('transform',initialTransform!);
 const rotation=page.getByRole('slider',{name:/Rotation/});
 await rotation.press('ArrowRight');
 const upperLayer=overlay.locator('[data-floor-layer="upper"]');
 const transform=await upperLayer.getAttribute('transform');
 expect(transform).toContain('rotate(0.5)');
 await page.getByRole('button',{name:'Save floor pair'}).click();
 await expect(page.getByRole('status')).toHaveText('Floor pair saved.');
 await page.reload();
 await expect(first.locator('option:checked')).toHaveText('second-floor.png');
 await expect(upperLayer).toHaveAttribute('transform',transform!);
 await expect(floor.getByRole('button',{name:'Remove garden 1'})).toBeVisible();
 await floor.getByRole('link',{name:'Open first floor editor'}).click();
 await expect(page).toHaveURL(/\/plan\/[^/]+$/);
 await expect(page.getByTitle('second-floor.png',{exact:true})).toHaveText('second-floor.png',{timeout:25_000});
 await expect(page.getByRole('heading',{name:'First floor',exact:true})).toBeVisible();
 await expect(page.locator('[data-site-region="garden"]')).toBeVisible();
 await page.getByLabel('Garden and stair outlines').uncheck();
 await expect(page.locator('[data-site-region="garden"]')).toHaveCount(0);
 const secondTab=page.waitForEvent('popup');
 await page.getByRole('link',{name:'Open second floor in a new tab'}).click();
 const upperEditor=await secondTab;
 await expect(upperEditor.getByRole('heading',{name:'Second floor',exact:true})).toBeVisible({timeout:25_000});
 await upperEditor.getByRole('button',{name:'Overview',exact:true}).click();
 const scope=upperEditor.getByRole('group',{name:'Overview scope'});
 await expect(scope.getByRole('button',{name:'Whole house'})).toHaveAttribute('aria-pressed','true',{timeout:20_000});
 await expect(upperEditor.getByRole('heading',{name:'Whole house overview'})).toBeAttached();
 await scope.getByRole('button',{name:'This floor'}).click();
 await expect(upperEditor.getByRole('heading',{name:'Dollhouse view'})).toBeAttached();
 await scope.getByRole('button',{name:'Whole house'}).click();
 await expect(upperEditor.getByRole('heading',{name:'Whole house overview'})).toBeAttached();
});

test('garden area subtracts enclosed patios using calibrated source dimensions',()=>{
 const region={kind:'garden' as const,points:[[0,0],[.5,0],[.5,.5],[0,.5]] as [number,number][],
   holes:[[[.1,.1],[.2,.1],[.2,.2],[.1,.2]] as [number,number][]]};
 expect(regionArea(region,800,600,.01)).toBeCloseTo(11.52);
});
