import {expect,test} from "@playwright/test";
import {samplePlan} from "../lib/plan/showcaseSample";

for (const width of [390,1280]) {
  test(`phone library opens its own space and floor screens at ${width}px`,async({page})=>{
    await page.setViewportSize({width,height:844});
    const space={id:"s",title:"Garden apartment"};
    let uploaded=false;
    const floor={id:"f",filename:"ground.png",width:100,height:100,project_id:"s"};
    await page.route("**/projects",r=>r.fulfill({json:r.request().method()==="POST"?space:[]}));
    await page.route("**/projects/s/blueprints",r=>{
      if(r.request().method()==="POST"){uploaded=true;return r.fulfill({json:floor});}
      return r.fulfill({json:[]});
    });
    await page.route("**/blueprints/f/info",r=>r.fulfill({json:floor}));
    await page.route("**/blueprints/f/plan",r=>r.fulfill({json:{model:null,revision:0}}));
    await page.route("**/blueprints/f/plan/extract?expected_revision=0",r=>{
      expect(r.request().method()).toBe("POST");
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
    await expect(page.getByRole("heading",{name:"Walkthrough",exact:true})).toBeVisible({timeout:20000});
    await expect(page.getByText(/Approximate scale/)).toBeVisible();
    await page.getByRole("button",{name:"Overview"}).click();
    await expect(page.locator(".show-room-tag").filter({hasText:"Bedroom"})).toBeVisible();
    await expect(page.getByRole("link",{name:"Exit tour"})).toHaveCount(0);
  });
}
