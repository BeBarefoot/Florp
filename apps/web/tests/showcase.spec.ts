import {expect,test,type Page} from "@playwright/test";
import {samplePlan,sampleScene} from "../lib/plan/showcaseSample";
import type {Scene} from "../lib/plan/scene";
import {savedPose} from "../lib/plan/camera";

async function openTools(page:Page){
  const button=page.getByRole("button",{name:/^(Open|Close) tour tools$/});
  await expect(button).toBeVisible();
  if(await button.getAttribute("aria-expanded")==="false")await button.click();
}

test("phone finishes keep room overrides when the whole-floor preset changes",async({page})=>{
  test.setTimeout(60_000);
  await page.setViewportSize({width:390,height:844});
  let config:Scene=sampleScene;
  let revision=1;
  await page.route("**/blueprints/f/*",async route=>{
    const path=new URL(route.request().url()).pathname;
    if(path.endsWith("/plan"))return route.fulfill({json:{revision:1,model:{...samplePlan,id:"f"}}});
    if(path.endsWith("/info"))return route.fulfill({json:{id:"f",filename:"Owner floor",project_id:"p"}});
    if(path.endsWith("/renders"))return route.fulfill({json:[]});
    if(route.request().method()==="PUT"){
      const body=route.request().postDataJSON();
      expect(body.expectedRevision).toBe(revision);
      config=body.config;
      revision++;
    }
    return route.fulfill({json:{revision,planRevision:1,config}});
  });
  await page.goto("/phone/showcase/f");
  await openTools(page);
  await page.getByRole("button",{name:"Finishes",exact:true}).click();
  await page.getByLabel("Apply to").selectOption("bedroom");
  const material=page.getByRole("combobox",{name:"Material",exact:true});
  await material.selectOption("tile");
  await page.getByLabel("Tile width (cm)").fill("45");
  await page.getByRole("button",{name:"Save finishes"}).click();
  await expect(page.getByText("Finishes saved")).toBeVisible();
  expect(config.roomFloorMaterials?.bedroom).toMatchObject({kind:"tile",widthM:.45});
  await page.getByLabel("Apply to").selectOption("");
  await page.getByRole("button",{name:"Modern concrete"}).click();
  await page.getByRole("button",{name:"Save finishes"}).click();
  await expect(page.getByText("Finishes saved")).toBeVisible();
  expect(config.floorMaterial?.kind).toBe("concrete");
  await page.reload();
  await openTools(page);
  await page.getByRole("button",{name:"Finishes",exact:true}).click();
  await expect(material).toHaveValue("concrete");
  await page.getByLabel("Apply to").selectOption("bedroom");
  await expect(material).toHaveValue("tile");
  await expect(page.getByLabel("Tile width (cm)")).toHaveValue("45");
});

test("walkthrough keeps matching finishes after a plan edit and links to finish recovery",async({page})=>{
  test.setTimeout(75_000);
  const tile={kind:"tile",color:"#c8bca7",widthM:.45,lengthM:.6} as const;
  const wood={kind:"wood",color:"#bf946d",widthM:.18,lengthM:1.2} as const;
  let config:Scene={...sampleScene,roomFloorMaterials:{living:wood,"previous-room":tile}};
  let revision=1;
  let planRevision=1;
  const model={...samplePlan,id:"f",revision:2};
  await page.setViewportSize({width:390,height:844});
  await page.route("**/blueprints/f/*",route=>{
    const endpoint=new URL(route.request().url()).pathname.split("/").pop();
    if(endpoint==="plan")return route.fulfill({json:{revision:2,model}});
    if(endpoint==="info")return route.fulfill({json:{id:"f",filename:"Owner floor",project_id:"p",width:1000,height:680}});
    if(endpoint==="renders"||endpoint==="history")return route.fulfill({json:[]});
    if(endpoint==="review")return route.fulfill({json:{revision:2,status:"draft",blockers:[]}});
    if(endpoint==="render-settings")return route.fulfill({json:{width:1024,height:768,configured:false,model:"",provider:""}});
    if(route.request().method()==="PUT"){
      const body=route.request().postDataJSON();
      expect(body.expectedRevision).toBe(revision);
      expect(body.planRevision).toBe(2);
      config=body.config;
      planRevision=body.planRevision;
      revision++;
    }
    return route.fulfill({json:{revision,planRevision,config}});
  });
  await page.goto("/phone/showcase/f");
  await openTools(page);
  await expect(page.getByText("Some saved floor finishes need review. Open Finishes.")).toBeVisible({timeout:20_000});
  await page.getByRole("button",{name:"Finishes",exact:true}).click();
  await page.getByLabel("Apply to").selectOption("living");
  await expect(page.getByRole("button",{name:"Use whole-floor finish"})).toBeVisible();
  await page.getByRole("link",{name:"Review finishes from the previous layout"}).click();
  const recovery=page.getByRole("region",{name:"Floor finishes to review"});
  await expect(recovery).toBeVisible({timeout:20_000});
  await recovery.getByRole("combobox",{name:/Move finish/}).selectOption("bedroom");
  await expect(recovery).toHaveCount(0);
  await page.getByRole("button",{name:"Save scene",exact:true}).filter({visible:true}).first().click();
  await expect.poll(()=>config.roomFloorMaterials).toEqual({living:wood,bedroom:tile});
  await page.goto("/phone/showcase/f");
  await openTools(page);
  await page.getByRole("button",{name:"Finishes",exact:true}).click();
  await page.getByLabel("Apply to").selectOption("bedroom");
  await expect(page.getByLabel("Tile width (cm)")).toHaveValue("45");
});

test("sample tour works without a project and supports dollhouse stops and playback",async({page})=>{
  test.setTimeout(75000);
  await page.setViewportSize({width:390,height:844});
  await page.goto("/phone/showcase/sample");
  await openTools(page);
  await expect(page.getByRole("heading",{name:"Living room"})).toBeVisible({timeout:15000});
  await page.getByRole("button",{name:"Overview",exact:true}).click();
  await page.getByRole("button",{name:"Visit Bedroom"}).click();
  await expect(page.getByRole("heading",{name:"Bedroom"})).toBeVisible();
  await page.getByRole("button",{name:"Living room",exact:true}).click();
  await page.getByRole("button",{name:"Play tour"}).click();
  await expect(page.getByRole("heading",{name:"Dining corner"})).toBeVisible({timeout:15000});
  await page.getByRole("button",{name:"Pause"}).click();
  await expect(page.getByRole("button",{name:"Play tour"})).toBeVisible();
});

test("saved floor tour opens its linked camera and makes no project edits",async({page})=>{
  const writes:string[]=[];
  await page.route("**/blueprints/f/*",r=>{
    if(r.request().method()!=="GET")writes.push(r.request().url());
    const end=new URL(r.request().url()).pathname.split("/").pop();
    return r.fulfill({json:end==="plan"?{revision:1,model:{...samplePlan,id:"f"}}:
      end==="scene"?{revision:1,planRevision:1,config:sampleScene}:{id:"f",filename:"Owner floor",project_id:"p"}});
  });
  await page.route("**/blueprints/f/scene/renders",r=>r.fulfill({json:[
    {id:"current",viewId:"suite",status:"complete",planRevision:1,sceneRevision:1},
    {id:"old",viewId:"dining",status:"complete",planRevision:1,sceneRevision:0}]}));
  await page.goto("/phone/showcase/f#view=suite");
  await openTools(page);
  await expect(page.getByRole("heading",{name:"Bedroom"})).toBeVisible();
  await page.getByRole("button",{name:"Show saved design"}).click();
  await expect(page.getByAltText("Saved design render for Bedroom")).toHaveAttribute("src",/current\/result\.png$/);
  await page.getByRole("button",{name:"Previous stop"}).click();
  await expect(page.getByRole("button",{name:"Show saved design"})).toHaveCount(0);
  await expect(page.getByRole("heading",{name:"Dining corner"})).toBeVisible();
  expect(writes).toEqual([]);
});

test("downloaded showcase prompt follows the live position, heading and zoom",async({page})=>{
  const {readFile}=await import("node:fs/promises");
  await page.setViewportSize({width:390,height:844});
  await page.goto("/phone/showcase/sample");
  await openTools(page);
  async function camera(){
    const pending=page.waitForEvent("download");
    await page.getByRole("button",{name:"Download view prompt"}).click();
    const file=await (await pending).path();
    return JSON.parse((await readFile(file!,"utf8")).trim().split("\n").at(-1)!).camera;
  }
  const before=await camera();
  expect(before.horizontalFovDegrees).toBe(110);
  expect(before.eyeXYZ[0]).toBeGreaterThan(5.6);
  expect(before.eyeXYZ[2]).toBeGreaterThan(6);
  await page.mouse.move(160,230);
  await page.mouse.down();
  await page.mouse.move(190,200,{steps:4});
  await page.mouse.up();
  await page.mouse.wheel(0,-120);
  const after=await camera();
  expect(after.eyeXYZ).not.toEqual(before.eyeXYZ);
  expect(after.forwardUnitXYZ).not.toEqual(before.forwardUnitXYZ);
  expect(after.horizontalFovDegrees).toBeLessThan(before.horizontalFovDegrees);
  await page.keyboard.down("d");
  await page.waitForTimeout(700);
  await page.keyboard.up("d");
  const strafed=await camera();
  expect(strafed.eyeXYZ).not.toEqual(after.eyeXYZ);
  expect(strafed.forwardUnitXYZ).toEqual(after.forwardUnitXYZ);
  const pending=page.waitForEvent("download");
  await page.getByRole("button",{name:"Download view image"}).click();
  const png=await readFile((await (await pending).path())!);
  expect([png.readUInt32BE(16),png.readUInt32BE(20)]).toEqual(after.framePixels);
});

test("dollhouse lands on the floor and saves a new view from one tap",async({page})=>{
  test.setTimeout(75000);
  const {PerspectiveCamera,Vector3}=await import("three");
  let config=sampleScene;
  let revision=1;
  await page.setViewportSize({width:1100,height:850});
  await page.route("**/blueprints/f/*",async r=>{
    const endpoint=new URL(r.request().url()).pathname.split("/").pop();
    if(endpoint==="scene"&&r.request().method()==="PUT"){
      const body=r.request().postDataJSON();
      expect(body.expectedRevision).toBe(revision);
      expect(body.planRevision).toBe(1);
      config=body.config;
      revision++;
    }
    return r.fulfill({json:endpoint==="plan"?{revision:1,model:{...samplePlan,id:"f"}}:
      endpoint==="scene"?{revision,planRevision:1,config}:endpoint==="renders"||endpoint==="history"?[]:
      endpoint==="review"?{revision:1,status:"draft",blockers:[],elevations:null}:
      {id:"f",filename:"Owner floor",project_id:"p",width:1000,height:680}});
  });
  await page.goto("/plan/f");
  await page.getByRole("button",{name:"Phone walkthrough",exact:true}).click();
  await expect(page).toHaveURL(/\/phone\/showcase\/f\?from=editor$/);
  await openTools(page);
  await page.getByRole("button",{name:"Overview",exact:true}).click();
  const overview=page.getByRole("heading",{name:"Dollhouse view"});
  await expect(overview).toBeVisible();
  await expect(page.getByRole("link",{name:"Exit tour"})).toHaveCount(0);
  const canvas=page.locator("canvas");
  async function tapFloor(x:number,z:number){
    const box=(await canvas.boundingBox())!;
    const aspect=box.width/box.height;
    const target=new Vector3(5,.65,3.4);
    const camera=new PerspectiveCamera(42,aspect,.005,2000);
    camera.position.copy(target).addScaledVector(new Vector3(.82,1.1,1.22).normalize(),18.5/Math.min(1,aspect));
    camera.lookAt(target);
    camera.updateMatrixWorld();
    const point=new Vector3(x,0,z).project(camera);
    await page.mouse.click(box.x+(point.x+1)*box.width/2,box.y+(1-point.y)*box.height/2);
  }
  await tapFloor(2.3,3.6);
  await expect(page.getByRole("heading",{name:"Walkthrough"})).toBeVisible();
  await page.getByRole("button",{name:"Overview",exact:true}).click();
  await page.getByRole("button",{name:"Add view",exact:true}).click();
  await tapFloor(2.3,3.6);
  await expect(page.getByRole("heading",{name:"View 4"})).toBeVisible();
  const saved=config.views.at(-1)!;
  expect(saved.horizontalFov).toBe(110);
  expect(saved.yaw).toBe(-45);
  expect(saved.position.x).toBeGreaterThan(30);
  expect(saved.position.x).toBeLessThan(65);
  expect(680-saved.position.y).toBeCloseTo(saved.position.x);
  expect(config.objects).toEqual(sampleScene.objects);
  await page.goto("/phone/showcase/f#overview");
  await expect(page.getByRole("button",{name:"Visit View 4",exact:true})).toBeVisible({timeout:15000});
});

test("saving from the starting camera preserves both numbered pins after reload", async ({page})=>{
  let config={...sampleScene,views:[] as typeof sampleScene.views};
  let revision=0;
  await page.route("**/blueprints/f/*",async r=>{
    const endpoint=new URL(r.request().url()).pathname.split("/").pop();
    if(endpoint==="scene"&&r.request().method()==="PUT"){
      config=r.request().postDataJSON().config;
      revision++;
    }
    return r.fulfill({json:endpoint==="plan"?{revision:1,model:{...samplePlan,id:"f"}}:
      endpoint==="scene"?{revision,planRevision:1,config}:{id:"f",filename:"Floor",project_id:"p"}});
  });
  await page.route("**/blueprints/f/scene/renders",r=>r.fulfill({json:[]}));
  await page.goto("/phone/showcase/f");
  await openTools(page);
  await expect(page.getByRole("button",{name:"Download view prompt"})).toBeVisible();
  await page.getByRole("button",{name:"Save this view"}).click();
  await expect(page.getByRole("heading",{name:"View 2"})).toBeVisible();
  expect(config.views.map(v=>v.name)).toEqual(["View 1","View 2"]);
  await page.goto("/phone/showcase/f#overview");
  await openTools(page);
  for(const number of [1,2]){
    await page.getByRole("button",{name:"Visit View "+number,exact:true}).click();
    await expect(page.getByRole("heading",{name:"View "+number})).toBeVisible();
    await page.getByRole("button",{name:"Overview",exact:true}).click();
  }
});

test("phone furnishing places metric objects, updates fit warnings and saves through reload",async({browser})=>{
  test.setTimeout(75000);
  const context=await browser.newContext({viewport:{width:390,height:844},hasTouch:true});
  try{
    const page=await context.newPage();
    const {PerspectiveCamera,Vector3}=await import("three");
    let config:Scene={...sampleScene,objects:[]};
    let revision=1;
    const model={...samplePlan,id:"f",openings:samplePlan.openings.map(o=>
      o.kind==="door"?{...o,swing:"right" as const}:o)};
    await page.route("**/blueprints/f/*",async route=>{
      const endpoint=new URL(route.request().url()).pathname.split("/").pop();
      if(endpoint==="scene"&&route.request().method()==="PUT"){
        const body=route.request().postDataJSON();
        expect(body.expectedRevision).toBe(revision);
        expect(body.planRevision).toBe(1);
        config=body.config;
        revision++;
      }
      return route.fulfill({json:endpoint==="plan"?{revision:1,model}:
        endpoint==="scene"?{revision,planRevision:1,config}:endpoint==="renders"?[]:
        {id:"f",filename:"Owner floor",project_id:"p"}});
    });
    await page.goto("/phone/showcase/f");
    await openTools(page);
    await page.getByRole("button",{name:"Furnish",exact:true}).click();
    const sheet=page.getByRole("region",{name:"Furnish",exact:true});
    await expect(sheet).toBeVisible();
    const canvas=page.locator("canvas");
    async function tapFloor(x:number,z:number){
      const box=(await canvas.boundingBox())!;
      const aspect=box.width/box.height;
      const target=new Vector3(5,.65,3.4);
      const camera=new PerspectiveCamera(42,aspect,.005,2000);
      camera.position.copy(target).addScaledVector(new Vector3(.82,1.1,1.22).normalize(),18.5/Math.min(1,aspect));
      camera.lookAt(target);
      camera.updateMatrixWorld();
      const point=new Vector3(x,0,z).project(camera);
      await page.touchscreen.tap(box.x+(point.x+1)*box.width/2,box.y+(1-point.y)*box.height/2);
    }
    await sheet.getByRole("button",{name:"Sofa 220 × 92 cm"}).click();
    await tapFloor(.3,2.2);
    await expect(sheet.getByText("Choose a position where the whole object fits inside one room.")).toBeVisible();
    await tapFloor(2.4,2.2);
    await expect(sheet.getByLabel("Width (cm)")).toHaveValue("220");
    await sheet.getByLabel("Width (cm)").fill("210");
    await sheet.getByRole("button",{name:"Rotate right 15 degrees"}).click();
    await sheet.getByRole("button",{name:"Move",exact:true}).click();
    await tapFloor(3.3,3.1);
    await expect(sheet.getByLabel("Width (cm)")).toHaveValue("210");
    await sheet.getByRole("button",{name:"Table 140 × 80 cm"}).click();
    await tapFloor(3.3,3.1);
    await expect(sheet.getByText("Overlaps another object.")).toBeVisible();
    await sheet.getByRole("button",{name:"Move",exact:true}).click();
    await tapFloor(7.2,4.35);
    await expect(sheet.getByLabel("Width (cm)")).toHaveValue("140");
    await expect(sheet.getByText("Blocks a door swing.")).toBeVisible();
    await expect(sheet.getByText(/Obstructs the 60 cm/)).toBeVisible();
    await sheet.getByRole("button",{name:"Save furniture"}).click();
    await expect(sheet.getByText("Furniture saved")).toBeVisible();
    expect(config.objects[0]).toMatchObject({kind:"sofa",width:2.1,depth:.92,rotation:15});
    expect(config.objects[0].position.x).toBeCloseTo(330,-1);
    expect(config.objects[0].position.y).toBeCloseTo(310,-1);
    expect(config.objects[1].kind).toBe("table");
    expect(config.views).toEqual(sampleScene.views);
    await page.reload();
    await openTools(page);
    await page.getByRole("button",{name:"Furnish",exact:true}).click();
    await sheet.getByLabel("Placed objects").selectOption(config.objects[0].id);
    await expect(sheet.getByLabel("Width (cm)")).toHaveValue("210");
  }finally{await context.close();}
});

test("the tour opens full screen, scrolls its dock, and walks through an open doorway",async({browser})=>{
  test.setTimeout(75000);
  const context=await browser.newContext({viewport:{width:390,height:844},hasTouch:true});
  try{
    const page=await context.newPage();
    const {readFile}=await import("node:fs/promises");
    const {PerspectiveCamera,Vector3}=await import("three");
    const start={id:"approach",name:"Approach",position:{x:500,y:450},yaw:0,pitch:-19,horizontalFov:90,eyeHeight:1.6};
    const config={...sampleScene,views:[start],objects:[]};
    await page.route("**/blueprints/f/*",route=>{
      const endpoint=new URL(route.request().url()).pathname.split("/").pop();
      return route.fulfill({json:endpoint==="plan"?{revision:1,model:{...samplePlan,id:"f"}}:
        endpoint==="scene"?{revision:1,planRevision:1,config}:endpoint==="renders"?[]:
        {id:"f",filename:"Owner floor",project_id:"p"}});
    });
    await page.goto("/phone/showcase/f#view=approach");
    const canvas=page.locator("canvas");
    const toggle=page.getByRole("button",{name:"Open tour tools"});
    const dock=page.getByRole("group",{name:"Tour actions"});
    await expect(toggle).toHaveAttribute("aria-expanded","false");
    await expect(dock).toBeHidden();
    const frame=(await canvas.boundingBox())!;
    expect(frame).toMatchObject({x:0,y:0,width:390,height:844});
    const button=(await toggle.boundingBox())!;
    expect(button.x).toBeLessThan(24);
    expect(button.y+button.height).toBeGreaterThan(810);
    await openTools(page);
    expect(await dock.evaluate(e=>e.scrollWidth>e.clientWidth)).toBe(true);
    const rail=(await dock.boundingBox())!;
    await page.mouse.move(rail.x+rail.width/2,rail.y+rail.height/2);
    await page.mouse.wheel(250,0);
    await expect.poll(()=>dock.evaluate(e=>e.scrollLeft)).toBeGreaterThan(0);
    await page.getByRole("button",{name:"Close tour tools"}).click();
    await expect(dock).toBeHidden();
    expect(await canvas.boundingBox()).toEqual(frame);

    const pose=savedPose(start,.01,frame.width/frame.height);
    const camera=new PerspectiveCamera(pose.verticalFovDeg,frame.width/frame.height,.03,80);
    camera.position.set(...pose.position);
    camera.lookAt(camera.position.clone().add(new Vector3(...pose.direction)));
    camera.updateMatrixWorld();
    const point=new Vector3(7.4,0,4.5).project(camera);
    await page.touchscreen.tap((point.x+1)*frame.width/2,(1-point.y)*frame.height/2);
    await openTools(page);
    async function eyeX(){
      const pending=page.waitForEvent("download");
      await page.getByRole("button",{name:"Download view prompt"}).click();
      const file=await (await pending).path();
      return JSON.parse((await readFile(file!,"utf8")).trim().split("\n").at(-1)!).camera.eyeXYZ[0] as number;
    }
    await expect.poll(eyeX,{timeout:9000,intervals:[500,1000]}).toBeGreaterThan(7.2);
  }finally{await context.close();}
});
