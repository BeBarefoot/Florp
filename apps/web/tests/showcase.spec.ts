import {expect,test,type Page} from "@playwright/test";
import {samplePlan,sampleScene} from "../lib/plan/showcaseSample";
import type {Scene} from "../lib/plan/scene";
import {savedPose} from "../lib/plan/camera";

async function openTools(page:Page){
  const button=page.getByRole("button",{name:/^(Open|Close) tour tools$/});
  await expect(button).toBeVisible({timeout:15_000});
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
  const frame = await page.locator("canvas").boundingBox();
  await page.getByRole("button",{name:"Finishes",exact:true}).click();
  const controls = page.locator(".finish-controls");
  expect(await page.locator("canvas").boundingBox()).toEqual(frame);
  expect(await controls.evaluate(e => e.scrollWidth > e.clientWidth && getComputedStyle(e).overflowY === "hidden")).toBe(true);
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
  const previous={...model,revision:1,rooms:model.rooms.map(room=>
    room.id==="bedroom"?{...room,id:"previous-room"}:room)};
  await page.setViewportSize({width:390,height:844});
  await page.route("**/blueprints/f/**",route=>{
    const endpoint=new URL(route.request().url()).pathname.split("/").pop();
    if(endpoint==="plan")return route.fulfill({json:{revision:2,model}});
    if(endpoint==="info")return route.fulfill({json:{id:"f",filename:"Owner floor",project_id:"p",width:1000,height:680}});
    if(endpoint==="history")return route.fulfill({json:[{revision:2,model},{revision:1,model:previous}]});
    if(endpoint==="renders")return route.fulfill({json:[]});
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
  await expect(recovery.getByRole("option",{name:"Living room"})).toHaveCount(0);
  await recovery.getByRole("combobox",{name:/Move finish/}).selectOption("bedroom");
  await expect(recovery).toHaveCount(0);
  await expect(page.getByRole("region",{name:"Review plan changes"}).getByText("Affected items reviewed. Save the scene to update it.")).toBeVisible();
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
  test.setTimeout(60_000);
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
  expect(before.horizontalFovDegrees).toBeCloseTo(120);
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
  await page.getByRole("button",{name:"Living room",exact:true}).click();
  const gestureStart=await camera();
  const box=(await page.locator("canvas").boundingBox())!;
  const x=Math.round(box.x+box.width/2),y=Math.round(box.y+box.height/2);
  await page.mouse.move(x,y);
  await page.mouse.wheel(85,0);
  const swiped=await camera();
  expect(swiped.forwardUnitXYZ).not.toEqual(gestureStart.forwardUnitXYZ);
  expect(swiped.horizontalFovDegrees).toBeCloseTo(gestureStart.horizontalFovDegrees);

  const cdp=await page.context().newCDPSession(page);
  await cdp.send("Emulation.setTouchEmulationEnabled",{enabled:true,maxTouchPoints:2});
  const touches=(dx:number,dy:number,angle:number)=>[-1,1].map((side,id)=>({
    id,x:x+dx+side*50*Math.cos(angle),y:y+dy+side*50*Math.sin(angle),
  }));
  await cdp.send("Input.dispatchTouchEvent",{type:"touchStart",touchPoints:touches(0,0,0)});
  await cdp.send("Input.dispatchTouchEvent",{type:"touchMove",touchPoints:touches(24,-20,.34)});
  await cdp.send("Input.dispatchTouchEvent",{type:"touchEnd",touchPoints:[]});
  const touched=await camera();
  expect(touched.eyeXYZ).not.toEqual(swiped.eyeXYZ);
  expect(touched.forwardUnitXYZ).not.toEqual(swiped.forwardUnitXYZ);
});

test("trackpad swipe orbits the dollhouse in both axes",async({page})=>{
  test.setTimeout(45_000);
  await page.setViewportSize({width:960,height:700});
  await page.goto("/phone/showcase/sample#overview");
  const canvas=page.locator("canvas");
  const initial=await canvas.screenshot();
  const bounds=(await canvas.boundingBox())!;
  await page.mouse.move(bounds.x+bounds.width/2,bounds.y+bounds.height/2);
  await page.mouse.wheel(80,-50);
  expect((await canvas.screenshot()).equals(initial)).toBe(false);
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
    const camera=new PerspectiveCamera(45,aspect,.005,2000);
    camera.position.copy(target).addScaledVector(new Vector3(.82,1.1,1.22).normalize(),19/Math.min(1,aspect));
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
  expect(saved.horizontalFov).toBeCloseTo(120);
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
    await page.goto("/phone/showcase/f#overview");
    await openTools(page);
    await page.getByRole("button",{name:"Furnish",exact:true}).click();
    const sheet=page.getByRole("region",{name:"Furnish",exact:true});
    await expect(sheet).toBeVisible();
    const canvas=page.locator("canvas");
    async function tapFloor(x:number,z:number){
      const box=(await canvas.boundingBox())!;
      const aspect=box.width/box.height;
      const target=new Vector3(5,.65,3.4);
      const camera=new PerspectiveCamera(45,aspect,.005,2000);
      camera.position.copy(target).addScaledVector(new Vector3(.82,1.1,1.22).normalize(),19/Math.min(1,aspect));
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
    await expect(toggle).toHaveAttribute("aria-expanded","false",{timeout:15_000});
    await expect(dock).toBeHidden();
    const frame={x:0,y:0,width:390,height:844};
    await expect.poll(()=>canvas.boundingBox(),{timeout:15_000}).toEqual(frame);
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
    const overview = page.getByRole("button",{name:"Overview",exact:true});
    await expect(overview).toBeVisible();
    expect((await overview.boundingBox())!.y).toBeLessThan(24);

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
    await page.getByRole("button",{name:"Furnish",exact:true}).click();
    const catalog = page.getByRole("group",{name:"Furniture catalog"});
    await expect(catalog).toBeVisible();
    expect(await canvas.boundingBox()).toEqual(frame);
    expect(await catalog.evaluate(e => e.scrollWidth > e.clientWidth && getComputedStyle(e).overflowY === "hidden")).toBe(true);
    await catalog.hover();
    await page.mouse.wheel(0,220);
    await expect.poll(()=>catalog.evaluate(e=>e.scrollLeft)).toBeGreaterThan(0);
    await overview.click();
    await expect(page.getByRole("heading",{name:"Dollhouse view"})).toBeVisible();
    await expect(catalog).toBeVisible();
  }finally{await context.close();}
});

test("Furnish offers a session preview when scale or scene review prevents saving",async({page})=>{
  test.setTimeout(75000);
  await page.setViewportSize({width:390,height:844});
  const {PerspectiveCamera,Vector3}=await import("three");
  const writes:string[]=[];
  let approximate=true;
  await page.route("**/blueprints/f/*",route=>{
    const endpoint=new URL(route.request().url()).pathname.split("/").pop();
    if(route.request().method()==="PUT")writes.push(endpoint!);
    const model={...samplePlan,id:"f",revision:2,
      scale:approximate?{metersPerPixel:null,reference:null}:samplePlan.scale};
    return route.fulfill({json:endpoint==="plan"?{revision:2,model}:
      endpoint==="scene"?{revision:1,planRevision:1,config:sampleScene}:endpoint==="renders"?[]:
      {id:"f",filename:"Owner floor",project_id:"p"}});
  });
  await page.goto("/phone/showcase/f#overview");
  await openTools(page);
  await page.getByRole("button",{name:"Furnish",exact:true}).click();
  const sheet=page.getByRole("region",{name:"Furnish",exact:true});
  const preview=sheet.getByText("Preview only",{exact:true});
  await expect(preview).toHaveAttribute("title","Approximate scale");
  const sofa=sheet.getByRole("button",{name:"Sofa 220 × 92 cm"});
  await sofa.click();
  const bounds=(await page.locator("canvas").boundingBox())!;
  await expect(sofa).toHaveAttribute("aria-pressed","true");
  await expect(sheet.getByRole("button",{name:/cancel/i})).toHaveCount(0);
  await page.mouse.click(bounds.x+16,bounds.y+16);
  await expect(sofa).toHaveAttribute("aria-pressed","false");
  await sofa.click();
  const aspect=bounds.width/bounds.height;
  const target=new Vector3(5,.65,3.4);
  const camera=new PerspectiveCamera(45,aspect,.005,2000);
  camera.position.copy(target).addScaledVector(new Vector3(.82,1.1,1.22).normalize(),19/Math.min(1,aspect));
  camera.lookAt(target);
  camera.updateMatrixWorld();
  const point=new Vector3(2.7,0,3).project(camera);
  await page.mouse.click(bounds.x+(point.x+1)*bounds.width/2,bounds.y+(1-point.y)*bounds.height/2);
  await sheet.getByRole("button",{name:"Keep preview"}).click();
  await expect(sheet.getByText("Preview kept for this session")).toBeVisible();
  await sheet.getByRole("button",{name:"Close Furnish"}).click();
  await page.getByRole("button",{name:"Furnish",exact:true}).click();
  const picker=sheet.getByLabel("Placed objects");
  await expect(picker.getByRole("option",{name:"Sofa 1"})).toHaveCount(1);
  expect((await picker.boundingBox())!.width).toBeLessThan(110);
  await picker.selectOption({label:"Sofa 1"});
  await expect(sheet.getByRole("button",{name:"Move",exact:true})).toBeVisible();
  await page.mouse.click(bounds.x+16,bounds.y+16);
  await expect(picker).toHaveValue("");
  expect(writes).toEqual([]);
  approximate=false;
  await page.reload();
  await openTools(page);
  await page.getByRole("button",{name:"Furnish",exact:true}).click();
  await expect(preview).toHaveAttribute("title","Scene needs review");
  await expect(sofa).toBeEnabled();
  await expect(sheet.getByRole("button",{name:"Save furniture"})).toHaveCount(0);
  await expect(sheet.getByRole("option",{name:"Sofa 1"})).toHaveCount(0);
});

test("room catalog saves a resized TV and places a planter on the detected yard",async({page})=>{
  test.setTimeout(75_000);
  await page.setViewportSize({width:390,height:844});
  const {PerspectiveCamera,Vector3}=await import("three");
  const model={
    ...samplePlan,id:"f",imageTransform:{...samplePlan.imageTransform,width:1400},
    gardens:[{kind:"garden",points:[[.73,.08],[.97,.08],[.97,.92],[.73,.92]]}],
  };
  let config:Scene={...sampleScene,objects:[]};
  let revision=1;
  await page.route("**/blueprints/f/*",async route=>{
    const endpoint=new URL(route.request().url()).pathname.split("/").pop();
    if(endpoint==="scene"&&route.request().method()==="PUT"){
      config=route.request().postDataJSON().config;
      revision++;
    }
    return route.fulfill({json:endpoint==="plan"?{revision:1,model}:
      endpoint==="scene"?{revision,planRevision:1,config}:endpoint==="renders"?[]:
      {id:"f",filename:"Owner floor",project_id:"p"}});
  });
  await page.goto("/phone/showcase/f#overview");
  await openTools(page);
  await page.getByRole("button",{name:"Furnish",exact:true}).click();
  const sheet=page.getByRole("region",{name:"Furnish",exact:true});
  async function tap(x:number,z:number,y=0){
    const box=(await page.locator("canvas").boundingBox())!;
    const aspect=box.width/box.height;
    const target=new Vector3(7,.65,3.4);
    const camera=new PerspectiveCamera(45,aspect,.005,2000);
    camera.position.copy(target).addScaledVector(new Vector3(.82,1.1,1.22).normalize(),14*1.90/Math.min(1,aspect));
    camera.lookAt(target);
    camera.updateMatrixWorld();
    const point=new Vector3(x,y,z).project(camera);
    await page.mouse.click(box.x+(point.x+1)*box.width/2,box.y+(1-point.y)*box.height/2);
  }
  await sheet.getByRole("button",{name:"Kitchen",exact:true}).click();
  await expect(sheet.getByRole("button",{name:/4-door fridge/})).toBeVisible();
  await expect(sheet.getByRole("button",{name:/Dining set · 8 seats/})).toBeVisible();
  await sheet.getByRole("button",{name:"Living room",exact:true}).click();
  await sheet.getByRole("button",{name:/TV 55″/}).click();
  await tap(3,3);
  const size=sheet.getByLabel("Screen diagonal (inches)");
  await expect(size).toHaveValue("55");
  await size.fill("77");
  await size.press("Enter");
  await expect(size).toHaveValue("77");
  await sheet.getByRole("button",{name:"Yard",exact:true}).click();
  await sheet.getByRole("button",{name:/Planter/}).click();
  await tap(3,3);
  await expect(sheet.getByText(/whole object fits in a yard or balcony/)).toBeVisible();
  await tap(12,3,-.01);
  await sheet.getByRole("button",{name:"Save furniture"}).click();
  await expect(sheet.getByText("Furniture saved")).toBeVisible();
  const [tv,plant]=config.objects;
  expect(tv.kind).toBe("tv");
  expect(Math.hypot(tv.width,tv.height)/.0254).toBeCloseTo(77);
  expect(tv.width/tv.height).toBeCloseTo(16/9);
  expect(plant.kind).toBe("planter");
  expect(plant.position.x).toBeCloseTo(1200,-1);
});

test("cursor zoom keeps an off-center floor target for catalog dragging in Overview",async({page})=>{
  test.setTimeout(75_000);
  await page.setViewportSize({width:1100,height:850});
  const {PerspectiveCamera,Vector3}=await import("three");
  let config={...sampleScene,objects:[] as Scene["objects"]};
  await page.route("**/blueprints/f/*",async route=>{
    const endpoint=new URL(route.request().url()).pathname.split("/").pop();
    if(endpoint==="scene"&&route.request().method()==="PUT")config=route.request().postDataJSON().config;
    return route.fulfill({json:endpoint==="plan"?{revision:1,model:{...samplePlan,id:"f"}}:
      endpoint==="scene"?{revision:1,planRevision:1,config}:endpoint==="renders"?[]:
      {id:"f",filename:"Owner floor",project_id:"p"}});
  });
  await page.goto("/phone/showcase/f#overview");
  await openTools(page);
  await page.getByRole("button",{name:"Furnish",exact:true}).click();
  const sheet=page.getByRole("region",{name:"Furnish",exact:true});
  const canvas=page.locator("canvas");
  const bounds=(await canvas.boundingBox())!;
  const aspect=bounds.width/bounds.height;
  const target=new Vector3(5,.65,3.4);
  const camera=new PerspectiveCamera(45,aspect,.005,2000);
  camera.position.copy(target).addScaledVector(new Vector3(.82,1.1,1.22).normalize(),19);
  camera.lookAt(target);
  camera.updateMatrixWorld();
  const projected=new Vector3(2,0,2.9).project(camera);
  const drop={x:(projected.x+1)*bounds.width/2,y:(1-projected.y)*bounds.height/2};
  const beforeZoom=await canvas.screenshot();
  await page.mouse.move(bounds.x+drop.x,bounds.y+drop.y);
  for(let i=0;i<6;i++)await page.mouse.wheel(0,-120);
  expect((await canvas.screenshot()).equals(beforeZoom)).toBe(false);
  await sheet.getByRole("button",{name:"Sofa 220 × 92 cm"}).dragTo(canvas,{targetPosition:drop});
  await sheet.getByRole("button",{name:"Save furniture"}).click();
  await expect(sheet.getByText("Furniture saved")).toBeVisible();
  expect(config.objects[0].position.x).toBeCloseTo(200,-1);
  expect(config.objects[0].position.y).toBeCloseTo(290,-1);
});

test("furniture can be placed and dragged directly in the current walkthrough",async({page})=>{
  test.setTimeout(75_000);
  await page.setViewportSize({width:1100,height:850});
  const {PerspectiveCamera,Vector3}=await import("three");
  const {savedPose}=await import("../lib/plan/camera");
  const start={...sampleScene.views[0],position:{x:130,y:320},yaw:0,pitch:-22};
  let config={...sampleScene,views:[start],objects:[] as Scene["objects"]};
  await page.route("**/blueprints/f/*",async route=>{
    const endpoint=new URL(route.request().url()).pathname.split("/").pop();
    if(endpoint==="scene"&&route.request().method()==="PUT")config=route.request().postDataJSON().config;
    return route.fulfill({json:endpoint==="plan"?{revision:1,model:{...samplePlan,id:"f"}}:
      endpoint==="scene"?{revision:1,planRevision:1,config}:endpoint==="renders"?[]:
      {id:"f",filename:"Owner floor",project_id:"p"}});
  });
  await page.goto("/phone/showcase/f#view="+start.id);
  await openTools(page);
  await page.getByRole("button",{name:"Furnish",exact:true}).click();
  const sheet=page.getByRole("region",{name:"Furnish",exact:true});
  const bounds=(await page.locator("canvas").boundingBox())!;
  const aspect=bounds.width/bounds.height;
  const pose=savedPose(start,.01,aspect);
  const camera=new PerspectiveCamera(pose.verticalFovDeg,aspect,.03,80);
  camera.position.set(...pose.position);
  camera.lookAt(camera.position.clone().add(new Vector3(...pose.direction)));
  camera.updateMatrixWorld();
  function point(x:number,y:number,z:number){
    const projected=new Vector3(x,y,z).project(camera);
    return [bounds.x+(projected.x+1)*bounds.width/2,bounds.y+(1-projected.y)*bounds.height/2] as const;
  }
  await sheet.getByRole("button",{name:"Table 140 × 80 cm"}).click();
  await page.mouse.click(...point(3.6,0,3.2));
  await expect(sheet.getByLabel("Width (cm)")).toHaveValue("140");
  const grab=point(3.6,.74,3.2);
  await page.mouse.move(...grab);
  await page.mouse.down();
  await page.mouse.move(grab[0]+110,grab[1],{steps:8});
  await page.mouse.up();
  await sheet.getByRole("button",{name:"Save furniture"}).click();
  await expect(sheet.getByText("Furniture saved")).toBeVisible();
  expect(config.objects).toHaveLength(1);
  expect(config.objects[0].position.x).toBeCloseTo(360,-1);
  expect(config.objects[0].position.y).toBeGreaterThan(350);
  await sheet.getByRole("button",{name:"Close Furnish"}).click();
  await expect(page.getByRole("heading",{name:start.name})).toBeVisible();
});

test("desktop studio keeps the full viewport canvas beneath the workspace navigation",async({page})=>{
  test.setTimeout(75_000);
  await page.setViewportSize({width:1280,height:760});
  await page.goto("/studio/sample#overview");
  const modes=page.getByRole("navigation",{name:"Workspace views"});
  await expect(modes.getByRole("button",{name:"Overview"})).toHaveAttribute("aria-pressed","true",{timeout:30_000});
  await expect.poll(() => page.locator("canvas").evaluate(canvas => Math.round(canvas.getBoundingClientRect().height)),
    {timeout:15_000}).toBe(760);
  await modes.getByRole("button",{name:"Walk"}).click();
  await expect(modes.getByRole("button",{name:"Walk"})).toHaveAttribute("aria-pressed","true");
  await page.getByRole("button",{name:"Open tour tools"}).click();
  await expect(page.getByRole("group",{name:"Tour actions"})).toBeVisible();
});

test("desktop keeps a moved draft pin and the live walk camera after refresh",async({page})=>{
  test.setTimeout(75_000);
  const {readFile}=await import("node:fs/promises");
  await page.setViewportSize({width:1100,height:820});
  const draft={...samplePlan,id:"draft",scale:{metersPerPixel:null,reference:null}};
  await page.route("**/blueprints/draft/*",route=>{
    const endpoint=new URL(route.request().url()).pathname.split("/").at(-1);
    return route.fulfill({json:endpoint==="plan"?{revision:1,model:draft}:endpoint==="scene"?
      {revision:0,planRevision:null,config:{views:[],objects:[],style:""}}:endpoint==="renders"?[]:
      {id:"draft",filename:"Ground floor",project_id:"project"}});
  });
  await page.goto("/studio/draft#overview");
  const first=page.getByRole("button",{name:"Visit Walkthrough",exact:true});
  await expect(first).toBeVisible({timeout:25_000});
  const pin=(await first.boundingBox())!;
  await page.mouse.move(pin.x+pin.width/2,pin.y+pin.height/2);
  await page.mouse.down();
  await page.mouse.move(pin.x+pin.width/2+66,pin.y+pin.height/2+20,{steps:5});
  await page.mouse.up();
  const moved=page.getByRole("button",{name:"Visit View 1",exact:true});
  await expect(moved).toBeVisible();
  const position=(await moved.boundingBox())!;
  await page.reload();
  await expect(moved).toBeVisible({timeout:20_000});
  await expect.poll(async()=>Math.round((await moved.boundingBox())?.x??0)).toBe(Math.round(position.x));
  await moved.click();
  async function camera(){
    await openTools(page);
    const download=page.waitForEvent("download");
    await page.getByRole("button",{name:"Download view prompt"}).click();
    const path=await (await download).path();
    return JSON.parse((await readFile(path!,"utf8")).trim().split("\n").at(-1)!).camera;
  }
  const before=await camera();
  await page.mouse.move(420,320);
  await page.mouse.down();
  await page.mouse.move(455,290,{steps:4});
  await page.mouse.up();
  const after=await camera();
  expect(after.forwardUnitXYZ).not.toEqual(before.forwardUnitXYZ);
  expect(after.eyeXYZ).not.toEqual(before.eyeXYZ);
  await page.reload();
  const restored=await camera();
  for(const field of ["eyeXYZ","forwardUnitXYZ"]){
    for(let i=0;i<3;i++)expect(restored[field][i]).toBeCloseTo(after[field][i],8);
  }

  await expect(page.getByRole("link",{name:"Import second floor"})).toHaveAttribute("href","/project/project#add-floor");
  await page.route("**/projects/project/blueprints",route=>route.fulfill({
    json:route.request().method()==="POST"?{id:"upper",filename:"Upper floor.png"}:[{id:"draft",filename:"Ground floor"}],
  }));
  await page.route("**/projects/project/floor-pair",route=>route.fulfill({json:null}));
  await page.route("**/projects",route=>route.fulfill({json:[{id:"project",title:"Courtyard house"}]}));
  await page.getByRole("link",{name:"Import second floor"}).click();
  const input=page.getByLabel("Floor plan file");
  await expect(input).toBeFocused({timeout:20_000});
  await input.setInputFiles({name:"Upper floor.png",mimeType:"image/png",buffer:Buffer.from("drawing")});
  await page.getByRole("button",{name:"Upload plan",exact:true}).click();
  await expect(page.getByRole("heading",{name:"Upper floor.png"})).toBeVisible();
  await expect(page.getByRole("button",{name:"Identify floors, garden and stairs"})).toBeEnabled();
});

test("desktop wall editing uses one compact row centered above the bottom edge",async({page})=>{
  test.setTimeout(60_000);
  await page.setViewportSize({width:1000,height:760});
  const id="desktop-wall";
  const view={...sampleScene.views[0],id:"wall",position:{x:315,y:350},yaw:-90,pitch:0};
  await page.route(`**/blueprints/${id}/*`,route=>{
    const endpoint=new URL(route.request().url()).pathname.split("/").at(-1);
    return route.fulfill({json:endpoint==="plan"?{revision:1,model:{...samplePlan,id}}:
      endpoint==="scene"?{revision:1,planRevision:1,config:{...sampleScene,views:[view],objects:[]}}:
      endpoint==="renders"?[]:{id,project_id:"home",filename:"Drawing"}});
  });
  await page.route("**/projects/home/blueprints",route=>route.fulfill({json:[{id}]}));
  await page.goto(`/studio/${id}#view=wall`);
  await expect(page.getByRole("button",{name:"Walk",exact:true})).toHaveAttribute("aria-pressed","true",{timeout:25_000});
  const canvas=page.locator("canvas");
  await canvas.screenshot();
  await canvas.click({position:{x:460,y:380}});
  const controls=page.getByRole("group",{name:"Wall",exact:true});
  await expect(controls).toBeVisible();
  const panel=(await controls.boundingBox())!;
  const material=(await controls.getByLabel("Material").boundingBox())!;
  const color=(await controls.getByLabel("Color").boundingBox())!;
  expect(panel.x+panel.width/2).toBeCloseTo(500,0);
  expect(760-panel.y-panel.height).toBeCloseTo(18,0);
  expect(panel.height).toBeLessThan(90);
  expect(color.x).toBeGreaterThan(material.x+material.width);
  expect(color.y).toBeCloseTo(material.y,0);
});

test("confirmed stair landings connect both floors and resume after refresh", async ({page})=>{
  test.setTimeout(110_000);
  const poses:Record<string,{x:number;y:number;yaw:number;revision:number}>={};
  const levels=["ground","upper"];
  await page.route("**/projects/stair-test/**",route=>{
    const last=new URL(route.request().url()).pathname.split("/").at(-1)!;
    if(route.request().method()==="PUT")poses[last]=route.request().postDataJSON();
    return route.fulfill({json:last==="floor-pair"?{first:"ground",second:"upper"}:poses});
  });
  await page.route("**/blueprints/**",route=>{
    const [, ,id,endpoint]=new URL(route.request().url()).pathname.split("/");
    const level=levels.indexOf(id)+1;
    const start={...sampleScene.views[0],id:"start",position:{x:300,y:350},yaw:level===1?-90:90};
    return route.fulfill({json:endpoint==="plan"?{revision:1,model:{...samplePlan,id}}:endpoint==="info"?
      {id,filename:id,project_id:"stair-test",floor:{level,otherId:levels[2-level],regions:[]}}:
      new URL(route.request().url()).pathname.endsWith("/renders")?[]:
      {revision:1,planRevision:1,config:{objects:[],views:[start],style:""}}});
  });
  for(const id of levels){
    await page.goto(`/studio/${id}#view=start`);
    await page.getByRole("button",{name:"Set stair landing"}).click({timeout:25_000});
    await page.getByRole("button",{name:"Use this landing"}).click();
    await expect.poll(()=>poses[id]?.x).toBe(300);
  }
  await page.getByRole("link",{name:"Go downstairs"}).click();
  await expect(page.getByRole("heading",{name:"Stair landing"})).toBeAttached({timeout:25_000});
  await page.reload();
  await expect(page.getByRole("heading",{name:"Stair landing"})).toBeAttached({timeout:25_000});
  await page.getByRole("link",{name:"Go upstairs"}).click();
  await expect(page.getByRole("heading",{name:"Stair landing"})).toBeAttached({timeout:25_000});
  await expect(page).toHaveURL(/\/studio\/upper$/);
});
