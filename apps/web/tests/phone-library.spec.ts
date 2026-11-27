import {expect,test} from "@playwright/test";
import {samplePlan} from "../lib/plan/showcaseSample";

for (const width of [390,1280]) {
  test(`phone library opens its own space and floor screens at ${width}px`,async({page})=>{
    await page.setViewportSize({width,height:844});
    const space={id:"s",title:"Garden apartment"};
    let uploaded=false;
    let releaseExtraction=()=>{};
    const analysisVisible=new Promise<void>(resolve=>{releaseExtraction=resolve;});
    const floor={id:"f",filename:"ground.png",width:100,height:100,project_id:"s"};
    await page.route("**/projects",r=>r.fulfill({json:r.request().method()==="POST"?space:[]}));
    await page.route("**/projects/s/blueprints",r=>{
      if(r.request().method()==="POST"){uploaded=true;return r.fulfill({json:floor});}
      return r.fulfill({json:[]});
    });
    await page.route("**/blueprints/f/info",r=>r.fulfill({json:floor}));
    await page.route("**/blueprints/f/plan",r=>r.fulfill({json:{model:null,revision:0}}));
    await page.route("**/blueprints/f/plan/extraction-progress/*",r=>
      r.fulfill({json:{percent:48,stage:"Finding openings"}}));
    await page.route("**/blueprints/f/plan/extract?expected_revision=0",async r=>{
      expect(r.request().method()).toBe("POST");
      expect(r.request().headers()["x-florp-progress-id"]).toBeTruthy();
      await analysisVisible;
      return r.fulfill({json:{model:{...samplePlan,id:"f",scale:{reference:null,metersPerPixel:null}},revision:1}});
    });
    await page.route("**/blueprints/f/scene",r=>r.fulfill({json:{revision:0,planRevision:null,config:{views:[],objects:[],style:""}}}));
    await page.route("**/blueprints/f/scene/renders",r=>r.fulfill({json:[]}));
    await page.goto("/phone");
    await expect(page.getByRole("heading",{name:"Your walkthroughs"})).toBeVisible();
    await expect(page.locator(".app aside")).toHaveCount(0);
    await page.getByRole("button",{name:"New space"}).click();
    await page.getByLabel("Space name").fill(space.title);
    await page.getByRole("button",{name:"Create space"}).click();
    await expect(page).toHaveURL(/\/phone\/spaces\/s$/);
    await expect(page.getByLabel("Upload plans")).toBeEnabled();
    await page.getByLabel("Upload plans").setInputFiles({name:"ground.png",mimeType:"image/png",buffer:Buffer.from("fixture")});
    await page.getByRole("link",{name:floor.filename}).click();
    expect(uploaded).toBe(true);
    await expect(page).toHaveURL(/\/phone\/showcase\/f$/,{timeout:20000});
    await expect(page.getByRole("progressbar",{name:"Plan analysis progress"})).toHaveAttribute("value","48");
    releaseExtraction();
    await expect(page.getByRole("heading",{name:"Walkthrough",exact:true})).toBeVisible({timeout:20000});
    await page.getByRole("button",{name:"Open tour tools"}).click();
    await expect(page.getByText(/Approximate scale/)).toBeVisible();
    await page.getByRole("button",{name:"Overview"}).click();
    await expect(page.locator(".show-room-tag").filter({hasText:"Bedroom"})).toBeVisible();
    await expect(page.getByRole("link",{name:"Exit tour"})).toHaveCount(0);
  });
}

test("detected beds appear in the uncalibrated 3D tour without saving the scene", async ({page})=>{
  await page.setViewportSize({width:900,height:760});
  const plan={...samplePlan,id:"detected",revision:1,scale:{reference:null,metersPerPixel:null},
    roomSymbols:[{kind:"bed",position:{x:310,y:240},widthPx:100,depthPx:125,rotation:90}]};
  let writes=0;
  await page.route("**/blueprints/detected/plan",r=>r.fulfill({json:{model:plan,revision:1}}));
  await page.route("**/blueprints/detected/info",r=>r.fulfill({json:{id:"detected",filename:"Apartment.png",project_id:"s"}}));
  await page.route("**/blueprints/detected/scene",r=>{
    if(r.request().method()==="PUT")writes++;
    return r.fulfill({json:{revision:0,planRevision:null,config:{views:[],objects:[],style:""}}});
  });
  await page.route("**/blueprints/detected/scene/renders",r=>r.fulfill({json:[]}));
  await page.goto("/phone/showcase/detected#overview");
  await page.getByRole("button",{name:"Open tour tools"}).click();
  const preview=page.getByRole("button",{name:"Detected preview"});
  await expect(preview).toHaveAttribute("aria-pressed","true");
  const canvas=page.locator("canvas");
  await expect(canvas).toBeVisible();
  const furnished=(await canvas.screenshot()).toString("base64");
  await preview.click();
  await expect(preview).toHaveAttribute("aria-pressed","false");
  await expect.poll(async ()=>(await canvas.screenshot()).toString("base64")!==furnished).toBe(true);
  expect(writes).toBe(0);
});

test("a whole-home style is saved with the current scene revision", async ({page})=>{
  await page.setViewportSize({width:900,height:760});
  const id="styled-tour";
  const plan={...samplePlan,id,revision:1};
  let current={revision:1,planRevision:1,config:{views:[],objects:[],style:"",designPreset:null as string|null}};
  await page.route(`**/blueprints/${id}/plan`,r=>r.fulfill({json:{model:plan,revision:1}}));
  await page.route(`**/blueprints/${id}/info`,r=>r.fulfill({json:{id,filename:"Apartment.png",project_id:"s"}}));
  await page.route(`**/blueprints/${id}/scene/renders`,r=>r.fulfill({json:[]}));
  await page.route(`**/blueprints/${id}/scene`,r=>{
    if(r.request().method()==="PUT"){
      const body=r.request().postDataJSON();
      expect(body.expectedRevision).toBe(current.revision);
      expect(body.planRevision).toBe(plan.revision);
      current={revision:current.revision+1,planRevision:plan.revision,config:body.config};
    }
    return r.fulfill({json:current});
  });
  await page.goto(`/phone/showcase/${id}#overview`);
  await page.getByRole("button",{name:"Open tour tools"}).click();
  await page.getByRole("button",{name:"Styles",exact:true}).click();
  const styles=page.getByRole("region",{name:"Whole-home style"});
  await styles.getByRole("button",{name:"Boutique hotel"}).click();
  await expect(styles.getByRole("button",{name:"Boutique hotel"})).toHaveAttribute("aria-pressed","true");
  await styles.getByRole("button",{name:"Apply style"}).click();
  await expect(styles).toHaveCount(0);
  expect(current.config.designPreset).toBe("hotel");
});

test("hovering over furniture in the walkthrough opens quick editing", async ({page})=>{
  await page.setViewportSize({width:900,height:760});
  const id="edit-tour";
  const plan={...samplePlan,id,revision:1};
  const sofa={id:"sofa",kind:"sofa",position:{x:300,y:340},width:2.2,depth:.92,height:.9,rotation:0};
  const view={id:"facing-sofa",name:"Living room",position:{x:300,y:570},yaw:-90,pitch:-24,
    horizontalFov:85,eyeHeight:1.6};
  let current={revision:1,planRevision:1,config:{views:[view],objects:[sofa],style:""}};
  await page.route(`**/blueprints/${id}/plan`,r=>r.fulfill({json:{model:plan,revision:1}}));
  await page.route(`**/blueprints/${id}/info`,r=>r.fulfill({json:{id,filename:"Apartment.png",project_id:"s"}}));
  await page.route(`**/blueprints/${id}/scene/renders`,r=>r.fulfill({json:[]}));
  await page.route(`**/blueprints/${id}/scene`,r=>{
    if(r.request().method()==="PUT")
      current={...current,revision:current.revision+1,config:r.request().postDataJSON().config};
    return r.fulfill({json:current});
  });
  await page.goto(`/phone/showcase/${id}#overview`);
  await page.getByRole("button",{name:"Visit Living room"}).click();
  await expect(page.getByRole("button",{name:"Overview",exact:true})).toBeVisible();
  const canvas=page.locator("canvas");
  await canvas.screenshot();
  const tools=page.getByRole("group",{name:"Sofa",exact:true});
  await expect.poll(async ()=>{
    await canvas.hover({position:{x:450,y:380}});
    return tools.isVisible();
  }).toBe(true);
  const panel=await tools.boundingBox();
  expect(panel).toBeTruthy();
  expect(Math.abs(panel!.x-450)).toBeLessThan(40);
  expect(Math.abs(panel!.y-380)).toBeLessThan(40);
  await tools.getByLabel("Width (cm)").fill("230");
  await tools.getByRole("button",{name:"Rotate",exact:true}).click();
  await page.getByRole("button",{name:"Save furniture"}).click();
  await expect.poll(()=>current.config.objects[0].rotation).toBe(90);
  expect(current.config.objects[0].width).toBe(2.3);
});

test.describe("touch walkthrough",()=>{
  test.use({hasTouch:true});

  test("walkthrough wall and window menus apply finishes and Add view works through furniture", async ({page})=>{
    await page.setViewportSize({width:390,height:760});
    const id="wall-and-view-tour";
    const plan={...samplePlan,id,revision:1};
    const walk={id:"north-wall",name:"Living room",position:{x:320,y:350},yaw:-90,pitch:0,horizontalFov:85,eyeHeight:1.6};
    let current:import("../lib/plan/scene").Saved={revision:1,planRevision:1,config:{
      views:[walk],objects:[{id:"rug",kind:"rug",position:{x:440,y:290},width:3.5,depth:3,height:.02,rotation:0}],
      style:"",wallFinishes:{"0":{b:{kind:"paint",color:"#aabbcc"}}}
    }};
    await page.route(`**/blueprints/${id}/plan`,r=>r.fulfill({json:{model:plan,revision:1}}));
    await page.route(`**/blueprints/${id}/info`,r=>r.fulfill({json:{id,filename:"Apartment.png",project_id:"s"}}));
    await page.route(`**/blueprints/${id}/scene/renders`,r=>r.fulfill({json:[]}));
    await page.route(`**/blueprints/${id}/scene`,r=>{
      if(r.request().method()==="PUT"){
        const body=r.request().postDataJSON();
        expect(body.expectedRevision).toBe(current.revision);
        current={...current,revision:current.revision+1,config:body.config};
      }
      return r.fulfill({json:current});
    });
    await page.goto(`/phone/showcase/${id}#overview`);
    await page.getByRole("button",{name:"Visit Living room"}).click();
    const canvas=page.locator("canvas");
    await canvas.screenshot();
    await canvas.tap({position:{x:165,y:380}});
    const wall=page.getByRole("group",{name:"Wall",exact:true});
    await wall.getByLabel("Material").selectOption("tile");
    await wall.getByLabel("Color").fill("#aacbaa");
    await wall.getByRole("button",{name:"Apply finish"}).click();
    await expect.poll(()=>current.config.wallFinishes?.["0"]).toEqual({
      a:{kind:"tile",color:"#aacbaa"},b:{kind:"paint",color:"#aabbcc"},
    });
    await canvas.tap({position:{x:221,y:380}});
    const window=page.getByRole("group",{name:"Window",exact:true});
    await window.getByLabel("Frame material").selectOption("wood");
    await window.getByRole("button",{name:"Apply finish"}).click();
    await expect.poll(()=>current.config.windowFinishes?.["opening-0"]?.material).toBe("wood");
    await page.getByRole("button",{name:"Overview",exact:true}).click();
    await page.getByRole("button",{name:"Open tour tools"}).click();
    await page.getByRole("button",{name:"Add view",exact:true}).click();
    await canvas.tap({position:{x:195,y:380}});
    await expect.poll(()=>current.config.views.length).toBe(2);
    expect(current.config.views[0]).toEqual(walk);
    await expect(page.getByRole("heading",{name:"View 2",exact:true})).toBeVisible();
  });
});
