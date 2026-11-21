import {expect,test} from "@playwright/test";
import {samplePlan,sampleScene} from "../lib/plan/showcaseSample";

test("sample tour works without a project and supports dollhouse stops and playback",async({page})=>{
  test.setTimeout(75000);
  await page.setViewportSize({width:390,height:844});
  await page.goto("/phone/showcase/sample");
  await expect(page.getByRole("heading",{name:"Living room"})).toBeVisible();
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
  await expect(page.getByRole("heading",{name:"Bedroom"})).toBeVisible();
  await page.getByRole("button",{name:"Show saved design"}).click();
  await expect(page.getByAltText("Saved design render for Bedroom")).toHaveAttribute("src",/current\/result\.png$/);
  await page.getByRole("button",{name:"Previous stop"}).click();
  await expect(page.getByRole("button",{name:"Show saved design"})).toHaveCount(0);
  await expect(page.getByRole("heading",{name:"Dining corner"})).toBeVisible();
  expect(writes).toEqual([]);
});
