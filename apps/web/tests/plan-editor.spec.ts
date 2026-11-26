import { test, expect, Page } from "@playwright/test";
import type { PlanModel } from "../lib/plan/model";
import { rooms, withDerived, metersPerPixel, wallEndReaches } from "../lib/plan/derive";
import { addWall, moveNode, setReference, decideOpening } from "../lib/plan/ops";
import { wallPieces } from "../lib/plan/mesh";
import { eyeLevelPose, savedPose, verticalFov } from "../lib/plan/camera";
import { promptFor, newItem, type Scene } from "../lib/plan/scene";
import {roomSurfaces} from "../lib/plan/stairs";
import {stairCutouts,treadLevels} from "../lib/plan/stairLevels";
import { furnitureParts } from "../lib/plan/furnitureModels";

function fixture(extra: Partial<PlanModel> = {}): PlanModel {
  const pts = [
    [100, 100],
    [500, 100],
    [900, 100],
    [900, 600],
    [500, 600],
    [100, 600],
  ];
  const edges = [
    [0, 1],
    [1, 2],
    [2, 3],
    [3, 4],
    [4, 5],
    [5, 0],
    [1, 4],
  ];
  const m: PlanModel = {
    schemaVersion: 2,
    id: "p",
    revision: 1,
    imageTransform: { width: 1000, height: 700, rotation: 0 },
    scale: { metersPerPixel: null, reference: null },
    nodes: pts.map(([x, y], i) => ({ id: "n" + i, x, y })),
    walls: edges.map(([a, b], i) => ({
      id: "w" + i,
      a: "n" + a,
      b: "n" + b,
      thicknessPx: 12,
      heightM: 2.8,
      material: "block",
      exterior: null,
      confidence: 1,
      source: "extracted",
    })),
    openings: [
      { id: "win", kind: "window", hostWallId: "w0", offsetPx: 100, widthPx: 120, span: null, heightM: 1.2, sillM: 0.9, swing: null, hinge: "start", confidence: 0.95, status: "confirmed" },
      { id: "maybe", kind: "door", hostWallId: "w3", offsetPx: 150, widthPx: 90, span: null, heightM: 2.1, sillM: 0, swing: null, hinge: "start", confidence: 0.55, status: "proposed" },
    ],
    rooms: [],
    findings: [
      { id: "opening_needs_approval:maybe", category: "opening_needs_approval", severity: "warn", targetIds: ["maybe"], anchor: { x: 745, y: 600 }, count: 1, message: "Confirm this door" },
      { id: "open_wall_end:n9", category: "open_wall_end", severity: "warn", targetIds: ["n2", "n3", "n4"], anchor: { x: 900, y: 100 }, count: 3, message: "3 wall ends not connected to another wall" },
      { id: "merged_duplicates:plan", category: "merged_duplicates", severity: "info", targetIds: [], anchor: { x: 500, y: 350 }, count: 41, message: "41 overlapping wall fragments merged" },
    ],
    dismissedFindings: [],
    notes: [],
    ...extra,
  };
  return withDerived(m);
}

async function setup(page: Page, opts: { empty?: boolean; model?: PlanModel; phone?:boolean } = {}) {
  let current: PlanModel | null = opts.empty ? null : opts.model || fixture();
  let revision = current ? 1 : 0;
  const puts: PlanModel[] = [];
  const extractions: { envelope?: { x: number; y: number }[] }[] = [];
  await page.route("**/blueprints/p/info", (r) =>
    r.fulfill({ json: { id: "p", project_id: "house", filename: "My house", width: 1000, height: 700 } }),
  );
  await page.route("**/blueprints/p/preview", (r) => r.fulfill({ status: 404, body: "" }));
  await page.route("**/blueprints/p/plan**", async (r) => {
    const req = r.request(),
      url = req.url();
    if (url.includes("/review")) return r.fulfill({json:{revision,status:"draft",blockers:[],elevations:null,reviewedAt:null}});
    if (url.includes("/extract")) {
      const body = req.postData() ? req.postDataJSON() : {};
      extractions.push(body);
      current = fixture({ envelope: body.envelope || opts.model?.envelope || null });
      revision++;
      return r.fulfill({ json: { revision, model: current } });
    }
    if (url.includes("/align-walls")) return r.fulfill({ json: req.postDataJSON().model });
    if (url.includes("/history")) return r.fulfill({ json: [] });
    if (req.method() === "PUT") {
      const body = req.postDataJSON();
      puts.push(body.model);
      revision++;
      current = { ...body.model, revision };
    }
    return r.fulfill({ json: { revision, model: current } });
  });
  await page.goto(opts.phone?"/phone/edit/p":"/plan/p");
  if(opts.phone)await expect(page.getByRole("heading",{name:"Edit floor"})).toBeVisible();
  else await expect(page.getByText("My house", { exact: true })).toBeVisible();
  return { puts, extractions };
}

async function screen(page: Page, x: number, y: number) {
  return page.locator(".fe-canvas svg").evaluate(
    (svg, [x, y]) => {
      const p = new DOMPoint(x, y).matrixTransform((svg as SVGSVGElement).getScreenCTM()!);
      return { x: p.x, y: p.y };
    },
    [x, y],
  );
}
async function clickAt(page: Page, x: number, y: number) {
  const p = await screen(page, x, y);
  await page.mouse.click(p.x, p.y);
}

test("phone editor adds and removes openings and walls with undo",async({page})=>{
  test.setTimeout(60_000);
  await page.setViewportSize({width:390,height:844});
  const {puts}=await setup(page,{phone:true});
  await page.getByRole("button",{name:"Window",exact:true}).click();
  await clickAt(page,630,100);
  await clickAt(page,750,100);
  await expect(page.locator(".fe-opening[data-kind=window]")).toHaveCount(2);
  await clickAt(page,690,100);
  await page.getByRole("button",{name:"Remove window"}).click();
  await expect(page.locator(".fe-opening[data-kind=window]")).toHaveCount(1);
  await page.getByRole("button",{name:"Door",exact:true}).click();
  await clickAt(page,500,260);
  await clickAt(page,500,370);
  await expect(page.locator(".fe-opening[data-kind=door]")).toHaveCount(2);
  await clickAt(page,500,320);
  await page.getByRole("button",{name:"Remove door"}).click();
  await page.getByRole("button",{name:"Wall",exact:true}).click();
  await clickAt(page,200,300);
  await clickAt(page,380,350);
  await expect(page.getByRole("button",{name:"Remove wall"})).toBeVisible();
  await page.getByRole("button",{name:"Remove wall"}).click();
  await page.getByRole("button",{name:"Undo",exact:true}).click();
  await page.getByRole("button",{name:"Done",exact:true}).click();
  await expect(page).toHaveURL(/\/phone\/showcase\/p/);
  expect(puts.at(-1)?.walls).toHaveLength(8);
  expect(puts.at(-1)?.openings).toHaveLength(2);
});

const rectangularTreads=[300,326,352,378,404].map(y=>[
  {x:290,y},{x:382,y},{x:382,y:y+26},{x:290,y:y+26},
]);

test("phone inspector saves window calibration and a two-way stair",async({page})=>{
  test.setTimeout(60_000);
  await page.setViewportSize({width:390,height:844});
  const stair={id:"stair",layout:"l" as const,riseM:.17,treads:rectangularTreads};
  const model=setReference(fixture({stairs:[stair]}),{x:100,y:100},{x:500,y:100},4);
  const {puts}=await setup(page,{model,phone:true});
  await clickAt(page,260,100);
  await page.getByText("Window dimensions and frame",{exact:true}).click();
  const width=page.getByLabel("Window width (m)");
  await width.fill("1.4");
  await width.press("Enter");
  await page.getByLabel("Frame material").selectOption("wood");
  await page.getByLabel("Glass panes").selectOption("2");
  await clickAt(page,332,355);
  await page.getByText("Stair direction and rise",{exact:true}).click();
  await page.getByLabel("Stair direction").selectOption("both");
  const landing=page.getByLabel("Treads below the landing");
  await landing.fill("1");
  await landing.press("Enter");
  await page.getByRole("button",{name:"Done",exact:true}).click();
  await expect(page).toHaveURL(/\/phone\/showcase\/p/);
  expect(puts.at(-1)?.openings.find(o=>o.id==="win")).toMatchObject({
    offsetPx:90,widthPx:140,windowFrame:{material:"wood",color:"#a77852",panes:2},
  });
  expect(puts.at(-1)?.stairs?.[0]).toMatchObject({direction:"both",treadsBelow:1});
});

test("descending treads open the floor and two-way stairs have a level landing",()=>{
  const stair={id:"stair",layout:"l" as const,riseM:.17,treads:rectangularTreads};
  expect(treadLevels(stair)[0].elevation).toBeCloseTo(.17);
  expect(treadLevels({...stair,direction:"down"})[0].elevation).toBeCloseTo(-.17);
  const both={...stair,direction:"both" as const,treadsBelow:2};
  const model=fixture({stairs:[both]});
  expect(treadLevels(both).map(tread=>tread.elevation)).toEqual([-.34,-.17,0,.17,.34]);
  expect(stairCutouts(model)).toHaveLength(2);
  const [shape]=roomSurfaces(model.rooms.find(room=>room.polygon.some(point=>point.x<200))!.polygon,.01,stairCutouts(model));
  expect(shape.holes).toHaveLength(1);
});

test("GLB keeps floor and wall finishes, windows, stairs, metric furniture and outdoor surfaces",async({page})=>{
  test.setTimeout(75_000);
  const window={...fixture().openings[0],windowFrame:{material:"wood" as const,color:"#885522",widthM:.06,panes:2 as const}};
  const stair={id:"stairs",layout:"l" as const,riseM:.17,treads:rectangularTreads,direction:"down" as const};
  const gardens:PlanModel["gardens"]=[
    {kind:"garden",points:[[.02,.1],[.08,.1],[.08,.25],[.02,.25]]},
    {kind:"garden",surface:"paving",points:[[.02,.25],[.08,.25],[.08,.4],[.02,.4]]},
  ];
  const model=setReference(fixture({openings:[window],stairs:[stair],gardens}),{x:100,y:100},{x:500,y:100},4);
  const catalogItems=(["sofa","rug","console_standing","toilet","vanity","shower"] as const).map((kind,i)=>
    ({...newItem(kind,{x:230+i*85,y:410}),id:"asset-"+kind}));
  catalogItems[0]={...catalogItems[0],width:2.06,depth:.87,height:.93,rotation:15};
  let config:Scene={views:[],objects:[{id:"scene-planter",kind:"planter",position:{x:340,y:290},
    width:.55,depth:.55,height:.98,rotation:0},...catalogItems],style:"",wallFinishes:{},
    floorMaterial:{kind:"marble",color:"#e4dac6",widthM:.6,lengthM:.8},
    roomFloorMaterials:{[model.rooms[1].id]:{kind:"tile",color:"#c8bca7",widthM:.3,lengthM:.6}}};
  let revision=1;
  await setup(page,{model});
  await page.route("**/blueprints/p/scene**",route=>{
    const path=new URL(route.request().url()).pathname;
    if(path.endsWith("/render-settings"))return route.fulfill({json:{width:1024,height:768,configured:false,model:"",provider:""}});
    if(path.endsWith("/renders"))return route.fulfill({json:[]});
    if(route.request().method()==="PUT"){
      config=route.request().postDataJSON().config;
      revision++;
    }
    return route.fulfill({json:{revision,planRevision:revision?1:null,config}});
  });
  await page.getByRole("radio",{name:"3D",exact:true}).click();
  const tools=page.getByRole("group",{name:"Wall finishes"});
  await tools.getByRole("combobox",{name:"Wall",exact:true}).selectOption("w6");
  const side=tools.getByRole("combobox",{name:"Side",exact:true});
  const finish=tools.getByRole("combobox",{name:"Wall finish",exact:true});
  await finish.selectOption("paint");
  await side.selectOption("b");
  await finish.selectOption("tile");
  await page.getByRole("button",{name:"Save scene",exact:true}).filter({visible:true}).first().click();
  await expect.poll(()=>config.wallFinishes).toMatchObject({w6:{a:{kind:"paint"},b:{kind:"tile"}}});
  await page.getByRole("button",{name:"Export",exact:true}).click();
  const pending=page.waitForEvent("download");
  await page.getByRole("menuitem",{name:"3D model (.glb)"}).click();
  const {readFile}=await import("node:fs/promises");
  const bytes=await readFile((await (await pending).path())!);
  const gltf=JSON.parse(bytes.subarray(20,20+bytes.readUInt32LE(12)).toString());
  const grounds=gltf.nodes.filter((node:{extras?:{kind:string}})=>node.extras?.kind==="garden");
  expect(grounds.map((node:{extras:{surface:string}})=>node.extras.surface)).toEqual(["lawn","paving"]);
  expect(new Set(grounds.map((node:{mesh:number})=>gltf.meshes[node.mesh].primitives[0].material)).size).toBe(2);
  const wall=gltf.nodes.find((node:{name:string})=>node.name==="w6");
  const mesh=gltf.meshes[gltf.nodes[wall.children[0]].mesh];
  const [front,back]=mesh.primitives.slice(-2).map(({material}:{material:number})=>gltf.materials[material].pbrMetallicRoughness);
  expect(front.baseColorTexture).toBeUndefined();
  expect(back.baseColorTexture).toBeDefined();
  const floors=gltf.nodes.filter((node:{extras?:{kind:string}})=>node.extras?.kind==="room");
  for (const [i,scale] of [[1/(4*.8),1/(4*.6)],[1/(5*.6),1/(5*.3)]].entries()) {
    const floor=gltf.materials[gltf.meshes[floors[i].mesh].primitives[0].material];
    const textures=[floor.normalTexture,floor.pbrMetallicRoughness.baseColorTexture,floor.pbrMetallicRoughness.metallicRoughnessTexture];
    for (const texture of textures) expect(texture.extensions.KHR_texture_transform.scale).toEqual(scale);
  }
  const furniture=gltf.nodes.find((node:{extras?:{id:string}})=>node.extras?.id==="scene-planter");
  expect(furniture.extras).toMatchObject({kind:"furniture",product:"planter"});
  expect(furniture.matrix[12]).toBeCloseTo(3.4);
  expect(furniture.matrix[13]).toBe(0);
  expect(furniture.matrix[14]).toBeCloseTo(2.9);
  expect(furniture.children.length).toBeGreaterThan(3);
  const {GLTFLoader}=await import("three/addons/loaders/GLTFLoader.js");
  const {Box3,Texture,Vector3}=await import("three");
  const loader=new GLTFLoader().register(()=>({name:"Skip image decoding in Node",loadTexture:async()=>new Texture()}));
  const {scene}=await loader.parseAsync(Uint8Array.from(bytes).buffer,"");
  for (const item of catalogItems) {
    const object=scene.children.find(child=>child.userData.id===item.id)!;
    expect(object.children).toHaveLength(1);
    object.rotation.y=0;
    const bounds=new Box3().setFromObject(object,true);
    const size=bounds.getSize(new Vector3());
    expect(size.x).toBeCloseTo(item.width,4);
    expect(size.y).toBeCloseTo(item.height,4);
    expect(size.z).toBeCloseTo(item.depth,4);
    const center=bounds.getCenter(new Vector3());
    expect(center.x).toBeCloseTo(item.position.x*.01,4);
    expect(center.z).toBeCloseTo(item.position.y*.01,4);
    expect(bounds.min.y).toBeCloseTo(0,4);
  }
  const exportedWindow=gltf.nodes.find((node:{name:string})=>node.name==="Window win");
  expect(exportedWindow.extras.frame).toMatchObject({material:"wood",panes:2});
  expect(exportedWindow.children.filter((index:number)=>gltf.nodes[index].extras.glass)).toHaveLength(2);
  const exportedStair=gltf.nodes.find((node:{name:string})=>node.name==="stairs");
  expect(exportedStair.extras.direction).toBe("down");
  expect(gltf.nodes[exportedStair.children[0]].matrix[13]).toBeCloseTo(-.34);
});

test("a conflicting second distance is saved and shown without changing the plan scale",async({page})=>{
  test.setTimeout(60_000);
  const {puts}=await setup(page,{model:setReference(fixture(),{x:100,y:100},{x:500,y:100},4)});
  await page.getByRole("button",{name:"Check a second distance"}).click();
  await clickAt(page,100,100);
  await clickAt(page,100,600);
  await page.getByRole("spinbutton",{name:"Known distance"}).fill("6");
  await page.getByRole("button",{name:"Apply",exact:true}).click();
  await expect(page.getByRole("alert").filter({hasText:"Measurements disagree"})).toContainText("16.7% difference");
  await expect.poll(()=>puts.at(-1)?.scale.checkReference?.lengthMeters).toBe(6);
  expect(puts.at(-1)?.scale.metersPerPixel).toBe(.01);
  await page.reload();
  await expect(page.getByRole("alert").filter({hasText:"Measurements disagree"})).toContainText("16.7% difference");
});

test("upload: extraction runs automatically and shows editable walls and openings", async ({ page }) => {
  await setup(page, { empty: true });
  await expect(page.locator("[data-kind=wall]")).toHaveCount(7);
  await expect(page.locator("[data-kind=window][data-status=confirmed]")).toHaveCount(1);
  await expect(page.locator("[data-kind=door][data-status=proposed]")).toHaveCount(1);
  await expect(page.getByTestId("approval-queue")).toContainText("Needs your approval (1)");
  await expect(page.getByTestId("room-count")).toHaveText("2 rooms");
});

test("set measurement: two clicks + 2.9 m sets scale without moving geometry", async ({ page }) => {
  const { puts } = await setup(page);
  await page.getByRole("button", { name: "Set measurement" }).click();
  await clickAt(page, 100, 100);
  const mid = await screen(page, 300, 100);
  await page.mouse.move(mid.x, mid.y);
  await expect(page.getByTestId("rubber-band")).toHaveCount(1);
  await clickAt(page, 390, 100);
  await expect(page.getByTestId("measurement-line")).toHaveCount(1);
  await page.getByRole("dialog", { name: "Known distance" }).getByLabel("Known distance").fill("2.9");
  await page.getByRole("button", { name: "Apply" }).click();
  await expect.poll(() => puts.length, { timeout: 5000 }).toBeGreaterThan(0);
  const saved = puts[puts.length - 1];
  expect(saved.nodes).toEqual(fixture().nodes);
  expect(saved.walls).toEqual(fixture().walls);
  const ref = saved.scale.reference!;
  expect(ref.lengthMeters).toBe(2.9);
  expect(metersPerPixel(saved)).toBeCloseTo(2.9 / Math.hypot(ref.p2.x - ref.p1.x, ref.p2.y - ref.p1.y), 6);
  await expect(page.getByTestId("room-row-area").first()).toContainText("m²");
});

for (const phone of [false,true]) {
  test(`printed scale requires confirmation in the ${phone?"phone":"web"} editor`, async ({ page }) => {
    const reference = {p1:{x:100,y:70},p2:{x:900,y:70},lengthMeters:8};
    const checkReference = {p1:{x:950,y:100},p2:{x:950,y:600},lengthMeters:5};
    const model = fixture({scale:{metersPerPixel:null,reference:null,proposal:{reference,checkReference,evidenceCount:3}}});
    const {puts} = await setup(page,{model,phone});
    await expect(page.getByRole("button",{name:"Use these measurements"})).toHaveCount(0);
    await page.getByRole("button",{name:"Review detected scale"}).click();
    await expect(page.getByTestId("proposed-scale-span")).toHaveCount(2);
    expect(puts).toHaveLength(0);
    await page.getByRole("button",{name:"Use these measurements"}).click();
    await expect.poll(()=>puts.length).toBeGreaterThan(0);
    expect(puts.at(-1)?.scale).toMatchObject({metersPerPixel:.01,reference,checkReference});
    expect(puts.at(-1)?.nodes).toEqual(model.nodes);
  });
}

test("dragging a shared corner updates 3D meshes and room areas immediately", async ({ page }) => {
  const scaled = setReference(fixture(), { x: 100, y: 100 }, { x: 500, y: 100 }, 4);
  await setup(page, { model: scaled });
  await page.locator(".fe-segment button").nth(1).click();
  const before = await page.getByTestId("plan-3d").getAttribute("data-wall-lengths");
  const areaBefore = await page.getByTestId("room-row-area").first().textContent();
  await clickAt(page, 420, 100);
  await expect(page.getByTestId("node-handle")).toHaveCount(2);
  const from = await screen(page, 100, 100);
  const to = await screen(page, 60, 60);
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  await page.mouse.move(to.x, to.y, { steps: 5 });
  await page.mouse.up();
  await expect(page.getByTestId("plan-3d")).not.toHaveAttribute("data-wall-lengths", before!);
  await expect(page.getByTestId("room-row-area").first()).not.toHaveText(areaBefore!);
});

test("canvas has no text badges; findings are grouped in the inspector", async ({ page }) => {
  await setup(page);
  await expect(page.locator(".fe-canvas svg text")).toHaveCount(0);
  await expect(page.getByTestId("finding-indicator")).toHaveCount(0);
  const group = page.locator("details[data-category=open_wall_end] summary");
  await expect(group).toHaveText("Open wall ends (3)");
  await expect(page.locator("details[data-category=merged_duplicates] summary")).toHaveText("Merged duplicates (41)");
  await group.click();
  await page.getByRole("button", { name: "3 wall ends not connected to another wall" }).click();
  await expect(page.getByTestId("finding-indicator")).toHaveCount(1);
  await expect(page.getByTestId("selection")).toContainText("WALL");
});

test("uncertain door needs approval and blocks export until decided", async ({ page }) => {
  const scaled = setReference(fixture(), { x: 100, y: 100 }, { x: 500, y: 100 }, 4);
  const { puts } = await setup(page, { model: scaled });
  await page.getByRole("button", { name: "Export" }).click();
  await expect(page.getByRole("menu")).toContainText("Approve or reject 1 proposed opening first.");
  await page.getByRole("button", { name: "Export" }).click();
  await page.getByRole("button", { name: "Approve door" }).click();
  await expect(page.getByTestId("approval-queue")).toHaveCount(0);
  await expect.poll(() => puts.length, { timeout: 5000 }).toBeGreaterThan(0);
  expect(puts[puts.length - 1].openings.find((o) => o.id === "maybe")!.status).toBe("confirmed");
});

test("pure ops: corner move keeps hosted openings, T-split, metric mesh", async () => {
  const m = setReference(fixture(), { x: 100, y: 100 }, { x: 500, y: 100 }, 4);
  const moved = moveNode(m, "n0", { x: 60, y: 100 });
  const win = moved.openings.find((o) => o.id === "win")!;
  expect(win.hostWallId).toBe("w0");
  expect(win.widthPx).toBe(120);
  // Extending the host keeps the window at its original image position.
  const original = m.openings.find((o) => o.id === "win")!;
  expect(60 + win.offsetPx).toBeCloseTo(100 + original.offsetPx, 6);
  expect(win.span).toEqual([{ x: 200, y: 100 }, { x: 320, y: 100 }]);
  expect(moved.nodes.find((n) => n.id === "n1")).toEqual(m.nodes.find((n) => n.id === "n1"));
  // Split solid wall spans, clear of the window at x=200–320.
  const t = addWall(m, { x: 350, y: 100 }, { x: 350, y: 600 }, 12);
  expect(t.model.walls.length).toBe(m.walls.length + 3);
  expect(rooms(t.model).length).toBe(3);
  expect(m.rooms[0].areaPx2).toBeCloseTo((400 - 12) * (500 - 12), 3);
  const pieces = wallPieces(decideOpening(m, "maybe", "confirm")!);
  expect(pieces.find((p) => p.id === "w0")!.lengthM).toBeCloseTo(4, 6);
  const doorWall = pieces.find((p) => p.id === "w3")!;
  // Joint caps are additional slabs outside the host's original length.
  expect(doorWall.chunks.filter((c) => c.start >= 0 && c.end <= doorWall.lengthM)).toEqual([
    { start: 0, end: 1.5, low: 0, high: 2.8 },
    { start: 1.5, end: 2.4, low: 2.1, high: 2.8 },
    { start: 2.4, end: 4, low: 0, high: 2.8 },
  ]);
});

test("unequal wall corners share outer faces and the T run stays flush", () => {
  const m = setReference(fixture(), { x: 100, y: 100 }, { x: 500, y: 100 }, 4);
  m.walls.find((w) => w.id === "w0")!.thicknessPx = 24;
  m.walls.find((w) => w.id === "w5")!.thicknessPx = 8;
  const reaches = wallEndReaches(m);
  expect(reaches.get("w0")).toEqual([4, 0]);
  expect(reaches.get("w5")![1]).toBe(12);
  expect(reaches.get("w6")![0]).toBe(12);
  const pieces = wallPieces(m);
  const horizontal = pieces.find((w) => w.id === "w0")!;
  const vertical = pieces.find((w) => w.id === "w5")!;
  expect(Math.min(...horizontal.chunks.map((c) => c.start))).toBeCloseTo(-0.04);
  expect(Math.max(...vertical.chunks.map((c) => c.end))).toBeCloseTo(vertical.lengthM + 0.12);
  expect(horizontal.chunks.some((c) => c.start < 1.6 && c.end > 1.6 && c.low < 1.5 && c.high > 1.5)).toBe(false);
});

test("building outline toggles cleanly and re-extracts only after corner release", async ({ page }) => {
  const envelope = [{ x: 100, y: 100 }, { x: 900, y: 100 }, { x: 900, y: 600 }, { x: 100, y: 600 }];
  const { extractions } = await setup(page, { model: fixture({ envelope }) });
  const toggle = page.getByRole("checkbox", { name: "Building outline" });
  await expect(page.getByTestId("building-outline")).toHaveCount(0);
  await toggle.check();
  await expect(page.getByTestId("outline-handle")).toHaveCount(4);
  const from = await screen(page, 100, 100), to = await screen(page, 70, 80);
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  await page.mouse.move(to.x, to.y, { steps: 5 });
  expect(extractions).toHaveLength(0);
  await page.mouse.up();
  await expect.poll(() => extractions.length).toBe(1);
  expect(extractions[0].envelope![0].x).toBeCloseTo(70, 0);
  expect(extractions[0].envelope![0].y).toBeCloseTo(80, 0);
  expect(extractions[0].envelope!.slice(1)).toEqual(envelope.slice(1));
  await toggle.uncheck();
  await expect(page.getByTestId("building-outline")).toHaveCount(0);
  expect(extractions).toHaveLength(1);
});

test("door hinge flip persists independently of its span and swing", async ({ page }) => {
  const model = fixture();
  model.openings[1].swing = "left";
  const { puts } = await setup(page, { model });
  await clickAt(page, 705, 600);
  await expect(page.getByRole("button", { name: "Flip hinge" })).toBeVisible();
  await page.getByRole("button", { name: "Flip hinge" }).click();
  await expect.poll(() => puts.length).toBeGreaterThan(0);
  const saved = puts.at(-1)!.openings.find((o) => o.id === "maybe")!;
  expect(saved.hinge).toBe("end");
  expect(saved.swing).toBe("left");
  expect(saved.widthPx).toBe(90);
  expect(saved.offsetPx).toBe(150);
  expect(saved.hostWallId).toBe("w3");
});

test("outline re-extraction saves pending approval edits first", async ({ page }) => {
  const envelope = [{ x: 100, y: 100 }, { x: 900, y: 100 }, { x: 900, y: 600 }, { x: 100, y: 600 }];
  const { puts, extractions } = await setup(page, { model: fixture({ envelope }) });
  await page.getByRole("checkbox", { name: "Building outline" }).check();
  await page.getByRole("button", { name: "Approve door" }).click();
  const from = await screen(page, 100, 100), to = await screen(page, 75, 90);
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  await page.mouse.move(to.x, to.y);
  await page.mouse.up();
  await expect.poll(() => extractions.length).toBe(1);
  expect(puts.length).toBeGreaterThan(0);
  expect(puts[0].openings.find((o) => o.id === "maybe")!.status).toBe("confirmed");
});

test("saved interior framing and depth match after reopening at a different width", async ({ page }) => {
  const scaled = setReference(fixture(), { x: 100, y: 100 }, { x: 500, y: 100 }, 4);
  let scene = { revision: 0, planRevision: 1, config: { views: [], objects: [], style: "" } };
  await page.route("**/blueprints/p/scene", r => {
    if (r.request().method() === "PUT") scene = {revision: 1, planRevision: 1, config: r.request().postDataJSON().config};
    return r.fulfill({json:scene});
  });
  await page.route("**/blueprints/p/scene/renders", r=>r.fulfill({json:[]}));
  await page.route("**/blueprints/p/scene/render-settings", r=>r.fulfill({json:{width:1024,height:768,configured:false,model:"test",provider:"fal"}}));
  const { puts } = await setup(page, { model: scaled });
  const enter = () => page.locator(".fe-segment button").nth(2).click();
  await enter();
  const map = page.getByLabel("Camera and furniture placement plan");
  async function at(x:number,y:number) {
    await map.scrollIntoViewIfNeeded();
    const p=await map.evaluate((el,coords)=>{
      const p=new DOMPoint(...coords).matrixTransform((el as unknown as SVGSVGElement).getScreenCTM()!);
      return {x:p.x,y:p.y};
    },[x,y] as [number,number]);
    await page.mouse.click(p.x,p.y);
  }
  await page.getByRole("button", {name:"Place camera"}).click();
  await at(400,180);
  await at(300,470);
  await expect(page.getByRole("button",{name:"Back to orbit"})).toBeVisible();
  await page.getByRole("button",{name:"Place object"}).click();
  await at(300,390);
  await page.getByLabel("Furniture",{exact:true}).selectOption("toilet");
  await page.getByRole("button",{name:"Place object"}).click();
  await at(700,350);
  await page.getByRole("button",{name:"Save scene"}).click();
  await expect(page.getByText("Scene saved.",{exact:true})).toBeVisible();
  async function depth() {
    await page.getByRole("button",{name:"Capture view"}).click();
    const download = page.waitForEvent("download");
    await page.getByRole("button",{name:"Export render inputs"}).click();
    const file = await (await download).path();
    const {readFile} = await import("node:fs/promises");
    return JSON.parse(await readFile(file,"utf8"));
  }
  const before=await depth();
  expect(before.prompt).toContain("Visible bed: 1.80 × 2.00 m mattress");
  expect(before.prompt).not.toContain("Visible toilet:");
  await page.setViewportSize({width:950,height:850});
  await page.reload();
  await enter();
  await expect(page.getByRole("button",{name:"Back to orbit"})).toBeVisible();
  const after=await depth();
  expect(after.sceneSnapshot.objects.length).toBe(2);
  const bed=after.visibleRegions[1000];
  expect(bed.pixels).toBeGreaterThan(0);
  expect(bed.depthMm[0]).toBeGreaterThan(0);
  expect(bed.boundsXY[2]).toBeLessThan(after.frame.width);
  expect(JSON.parse(after.prompt.split("\n").at(-1)).objects[0].visibleInFrame).toEqual(bed);
  expect(after.view).toEqual(before.view);
  expect(after.depth).toEqual(before.depth);
  expect(after.mask).toEqual(before.mask);
  expect(puts).toHaveLength(0);
  // Exercise the in-app design flow using mocked Comfy Cloud job responses.
  await page.route("**/blueprints/p/scene/render-settings", r=>r.fulfill({json:{width:1024,height:768,configured:true,model:"comfy:flux-depth-lora",provider:"comfy"}}));
  let submitted: Record<string, any> | null = null;
  const job = {id:"comfy-test",viewId:after.view.id,name:"Warm bedroom",prompt:"",model:"comfy:flux-depth-lora",sceneRevision:1,planRevision:1,status:"queued",error:null};
  await page.route("**/blueprints/p/renders", r=>{
    submitted=r.request().postDataJSON();
    return r.fulfill({json:{...job,prompt:submitted!.prompt}});
  });
  await page.route("**/blueprints/p/scene/renders/comfy-test", r=>r.fulfill({json:{...job,status:"complete"}}));
  await page.route("**/blueprints/p/scene/renders/comfy-test/*.png", r=>r.fulfill({contentType:"image/png",body:Buffer.from(after.preview.split(",")[1],"base64")}));
  await page.reload();
  await enter();
  const design="Create a warm brown bedroom with black bathroom tiles and a gold toilet";
  await page.getByLabel("Design prompt",{exact:true}).fill(design);
  // Generation captures automatically; a separate Capture click is unnecessary.
  const consent=page.getByRole("checkbox",{name:/Comfy Cloud/});
  await expect(page.getByRole("button",{name:"Generate preview"})).toBeDisabled();
  await consent.check();
  await page.getByRole("button",{name:"Generate preview"}).click();
  await expect(page.getByAltText("Generated design visualisation")).toBeVisible();
  expect(submitted).toMatchObject({viewId:after.view.id,confirmed:true,depth:after.depth.split(",")[1]});
  const geometry=JSON.parse(submitted!.prompt.split("\n").at(-1)!);
  const scale=metersPerPixel(after.planSnapshot)!;
  expect(geometry.camera.eyeXYZ).toEqual([after.view.position.x*scale,after.view.eyeHeight,after.view.position.y*scale]);
  expect(geometry.camera.framePixels).toEqual([after.frame.width,after.frame.height]);
  expect(geometry.camera.forwardUnitXYZ).toEqual(savedPose(after.view,scale,after.frame.width/after.frame.height).direction);
  expect(geometry.rooms[0].perimeterXZ.length).toBeGreaterThanOrEqual(3);
  expect(geometry.openings.find((o:{id:string})=>o.id==="win")).toMatchObject({height:1.2,sill:.9});
  expect(submitted!.prompt).toContain(design);
  expect(submitted!.prompt).toContain("Visible bed:");
  expect(submitted!.prompt).toContain("Do not bring an out-of-view room");
  expect(puts).toHaveLength(0);
});

test("saved camera converts horizontal FOV, pitch and pixel origin",()=>{
  const pose=savedPose({position:{x:200,y:300},yaw:90,pitch:-10,horizontalFov:90,eyeHeight:1.6},.01,4/3);
  expect(pose.position).toEqual([2,1.6,3]);
  expect(pose.direction[1]).toBeCloseTo(-.173648);
  expect(Math.hypot(...pose.direction)).toBeCloseTo(1);
  expect(verticalFov(90,4/3)).toBeCloseTo(73.7398);
});

test("bed mesh keeps the specified mattress and prompt separates style from geometry",()=>{
  const position={x:200,y:250};
  const view={id:"v",name:"Bedroom",position,yaw:0,pitch:-10,horizontalFov:90,eyeHeight:1.6};
  const parts=furnitureParts({id:"b",kind:"bed",position,rotation:0,width:1.9,depth:2.12,height:.9,
    mattressWidth:1.8,mattressDepth:2});
  const mattress=parts.filter(part=>part.finish==="linen").reduce((longest,part)=>
    part.size[2]>longest.size[2]?part:longest);
  expect(mattress.size[0]).toBeCloseTo(1.8);
  expect(mattress.size[2]).toBeCloseTo(2);
  expect(promptFor(view,["Space type: bedroom."],"Oak")).toBe([
    "Scene facts: Photorealistic interior from the supplied camera view.",
    "Eye height 1.60 m; horizontal field of view 90 degrees.",
    "Space type: bedroom.",
    "Preserve the camera, walls, existing openings, visible object positions and proportions. Do not add architectural openings or reveal objects behind walls.",
    "Apply each requested finish only to the named visible room or object. Do not bring an out-of-view room or fixture into the image to satisfy the design request.",
    "Style: Oak",
  ].join("\n"));
});

test("eye-level camera keeps metric position and a normalized level direction", () => {
  expect(eyeLevelPose([2, 3], [5, 7], 1.65)).toEqual({
    position: [2, 1.65, 3],
    direction: [0.6, 0, 0.8],
    verticalFovDeg: 55,
  });
  expect(eyeLevelPose([2, 3], [2, 3], 1.65)).toBeNull();
  expect(eyeLevelPose([2, 3], [5, 7], 4)).toBeNull();
});

test("fixture scan requires an individual insert or dismiss before saving", async ({ page }) => {
  const scaled = setReference(fixture(), { x: 100, y: 100 }, { x: 500, y: 100 }, 4);
  let scene = { revision: 0, planRevision: 1,
    config: { views: [], objects: [] as { id: string }[], style: "", dismissedFixtureIds: [] as string[] } };
  await page.route("**/blueprints/p/scene", r => {
    if (r.request().method() === "PUT") scene = { revision: 1, planRevision: 1, config: r.request().postDataJSON().config };
    return r.fulfill({ json: scene });
  });
  await page.route("**/blueprints/p/scene/renders", r => r.fulfill({ json: [] }));
  await page.route("**/blueprints/p/scene/render-settings", r => r.fulfill({ json: { width: 1024, height: 768 } }));
  await page.route("**/blueprints/p/scene/fixture-suggestions?*", r => r.fulfill({ json: { planRevision: 1, suggestions: [
    { id: "fixture-bed", kind: "bed", position: { x: 280, y: 310 }, rotation: 90, width: 1.62, depth: 2, height: .9 },
    { id: "fixture-toilet", kind: "toilet", position: { x: 650, y: 310 }, rotation: 180, width: .45, depth: .63, height: .8 },
  ] } }));
  await setup(page, { model: scaled });
  await page.locator(".fe-segment button").nth(2).click();
  const scan = page.getByRole("button", { name: "Find fixtures on plan" });
  await scan.click();
  const outlines = page.getByTestId("fixture-outline");
  await expect(outlines).toHaveCount(2);
  expect(scene.config.objects).toHaveLength(0);
  await page.getByRole("button", { name: "Insert bed" }).click();
  await expect(outlines).toHaveCount(1);
  await page.getByRole("button", { name: "Dismiss suggestion" }).click();
  await expect(outlines).toHaveCount(0);
  await page.getByRole("button", { name: "Save scene" }).click();
  await expect(page.getByText("Scene saved.", { exact: true })).toBeVisible();
  expect(scene.config.objects.map(o => o.id)).toEqual(["fixture-bed"]);
  expect(scene.config.dismissedFixtureIds).toEqual(["fixture-toilet"]);
  const objects=page.getByRole("region",{name:"Objects in this scene"});
  await expect(objects.getByRole("button",{name:"1. Bed"})).toBeVisible();
  await objects.getByRole("button",{name:"Remove bed 1"}).click();
  await expect(objects.getByText("No objects yet.",{exact:false})).toBeVisible();
  await page.getByRole("button",{name:"Undo scene"}).click();
  await expect(objects.getByRole("button",{name:"1. Bed"})).toBeVisible();
  await scan.click();
  await expect(page.getByText("Review the outlined suggestions. Nothing has been inserted.")).toBeVisible();
  await expect(outlines).toHaveCount(0);
});

test('failed Comfy render explains credit recovery and preserves the saved camera', async ({page}) => {
  const scaled = setReference(fixture(), {x:100,y:100}, {x:500,y:100}, 4);
  await setup(page, {model:scaled});
  const view = {id:'saved-view',name:'Bedroom',position:{x:300,y:250},yaw:0,pitch:0,horizontalFov:90,eyeHeight:1.6};
  await page.route('**/blueprints/p/scene', r=>r.fulfill({json:{revision:1,planRevision:1,config:{views:[view],objects:[],style:'Warm oak'}}}));
  await page.route('**/blueprints/p/scene/render-settings', r=>r.fulfill({json:{width:1024,height:768,configured:true,model:'comfy:flux-depth-lora',provider:'comfy'}}));
  await page.route('**/blueprints/p/scene/renders', r=>r.fulfill({json:[{id:'failed',viewId:view.id,name:'Bedroom',prompt:'Warm oak',model:'comfy:flux-depth-lora',sceneRevision:1,planRevision:1,status:'failed',error:'Comfy Cloud is out of credits. Add credits to the account associated with COMFY_API_KEY.'}]}));
  await page.locator('.fe-segment button').nth(2).click();
  await expect(page.getByRole('link',{name:'Open Comfy account and credits'})).toHaveAttribute('href','https://cloud.comfy.org');
  await expect(page.getByText('After fixing the account or configuration issue', {exact:false})).toBeVisible();
  await expect(page.getByLabel('Design prompt')).toHaveValue('Warm oak');
  await expect(page.getByRole('button',{name:'Capture view',exact:true})).toBeEnabled();
  await expect(page.getByRole('button',{name:'Generate preview',exact:true})).toBeDisabled();
});

test("render review recovers an existing job and compares its saved mask",async({page})=>{
  test.setTimeout(75_000);
  const model=setReference(fixture(),{x:100,y:100},{x:500,y:100},4);
  await setup(page,{model});
  const view={id:"saved-view",name:"Bedroom",position:{x:300,y:250},yaw:0,pitch:0,horizontalFov:90,eyeHeight:1.6};
  const job={id:"render",viewId:view.id,name:"Design",prompt:"Oak",model:"local-comfy:sdxl-depth",
    sceneRevision:1,planRevision:1,status:"failed",error:"Receipt not received"};
  let recoveries=0;
  const image=Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jPioAAAAASUVORK5CYII=","base64");
  await page.route("**/blueprints/p/scene**",route=>{
    const endpoint=new URL(route.request().url()).pathname.split("/").pop();
    if(endpoint==="render-settings")return route.fulfill({json:{width:1024,height:768,configured:false,provider:"local-comfy",model:"local-comfy:sdxl-depth"}});
    if(endpoint==="renders")return route.fulfill({json:[job]});
    if(endpoint==="recover"){
      expect(route.request().method()).toBe("POST");
      recoveries++;
      return route.fulfill({json:{...job,status:"complete",error:null}});
    }
    if(endpoint?.endsWith(".png"))return route.fulfill({contentType:"image/png",body:image});
    return route.fulfill({json:{revision:1,planRevision:1,config:{views:[view],objects:[],style:"Oak"}}});
  });
  await page.route("**/blueprints/p/renders",()=>{throw Error("Recovery attempted to submit a render");});
  await page.getByRole("radio",{name:"3D",exact:true}).click();
  await page.getByRole("button",{name:"Check for existing render"}).click();
  const review=page.getByRole("group",{name:"Render comparison"});
  await review.getByRole("button",{name:"Overlay",exact:true}).click();
  await review.getByRole("combobox",{name:"Reference layer"}).selectOption("mask.png");
  await expect(review.getByAltText("Captured object and wall mask")).toHaveAttribute("src",/\/mask\.png$/);
  await review.getByRole("slider",{name:/Design opacity/}).press("End");
  await expect(review.getByAltText("Generated design visualisation")).toHaveCSS("opacity","1");
  expect(recoveries).toBe(1);
});

test('architecture review requires explicit checks and becomes draft after calibration changes', async ({page}) => {
  const {puts}=await setup(page,{model:setReference(fixture({openings:[]}),{x:100,y:100},{x:500,y:100},4)});
  let reviewed=false;
  await page.route('**/blueprints/p/plan/review*',r=>{
    const revision=Number(new URL(r.request().url()).searchParams.get('revision')||1);
    if(r.request().method()==='POST'){
      expect(r.request().postDataJSON()).toMatchObject({revision:1,topology:true,openings:true,scale:true,elevations:'assumed'});
      reviewed=true;
    }
    return r.fulfill({json:{revision,status:reviewed&&revision===1?'reviewed':'draft',blockers:[],elevations:reviewed?'assumed':null,reviewedAt:null}});
  });
  await page.getByText('Architecture review: draft',{exact:true}).click();
  const record=page.getByRole('button',{name:'Record architecture review'});
  await expect(record).toBeDisabled();
  await page.getByLabel('I checked wall connections, room boundaries and intentional open ends.').check();
  await page.getByLabel('I checked all doors and windows against the source.').check();
  await page.getByLabel('I confirmed the reference distance against a known measurement.').check();
  await record.click();
  await expect(page.getByText('Architecture review: reviewed',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Set measurement'}).click();
  await clickAt(page,100,100);await clickAt(page,390,100);
  await page.getByRole('dialog',{name:'Known distance'}).getByLabel('Known distance').fill('2.9');
  await page.getByRole('button',{name:'Apply',exact:true}).click();
  await expect.poll(()=>puts.length).toBeGreaterThan(0);
  await expect(page.getByText('Architecture review: draft',{exact:true})).toBeVisible();
});

test('local generation consent avoids cloud billing and shows local recovery instructions',async({page})=>{
 await setup(page,{model:setReference(fixture(),{x:100,y:100},{x:500,y:100},4)});
 const view={id:'local',name:'Local bedroom',position:{x:300,y:250},yaw:0,pitch:0,horizontalFov:90,eyeHeight:1.6};
 await page.route('**/blueprints/p/scene',r=>r.fulfill({json:{revision:1,planRevision:1,config:{views:[view],objects:[{id:'wardrobe-1',kind:'wardrobe',position:{x:430,y:250},width:.5,height:1.8,depth:.4,rotation:0}],style:'Warm oak'}}}));
 await page.route('**/blueprints/p/scene/render-settings',r=>r.fulfill({json:{width:1024,height:768,configured:true,model:'local-comfy:sdxl-depth',provider:'local-comfy'}}));
 await page.route('**/blueprints/p/scene/renders',r=>r.fulfill({json:[]}));
 let count=0;
 await page.route('**/blueprints/p/renders',r=>{
   expect(r.request().postDataJSON()).toMatchObject({confirmed:true,targetObjectId:'wardrobe-1'});count++;
   return r.fulfill({json:{id:'local-job',viewId:'local',name:'Local bedroom',prompt:'Warm oak',model:'local-comfy:sdxl-depth',sceneRevision:1,planRevision:1,status:'failed',error:'Local ComfyUI unavailable'}});
 });
 await page.locator('.fe-segment button').nth(2).click();
 const consent=page.getByLabel('Generate on this computer using local ComfyUI — no cloud API charge');
 await page.getByLabel("Render area").selectOption("wardrobe-1");
 await expect(consent).toBeVisible();await consent.check();
 await page.getByRole('button',{name:'Generate preview',exact:true}).click();
 await expect(page.getByText('Local ComfyUI unavailable', {exact:false})).toBeVisible();
 await expect(page.getByText('See the local ComfyUI setup guide', {exact:false})).toBeVisible();
 expect(count).toBe(1);
 await expect(page.getByRole('link',{name:'Open Comfy account and credits'})).toHaveCount(0);
});

test('walkthrough responds to mouse and touch and returns to the saved framing', async ({page})=>{
 test.setTimeout(60000);
 await setup(page,{model:setReference(fixture(),{x:100,y:100},{x:500,y:100},4)});
 const view={id:'walk',name:'Interior',position:{x:300,y:250},yaw:0,pitch:0,horizontalFov:90,eyeHeight:1.6};
 const bed={id:'bed',kind:'bed',position:{x:425,y:295},rotation:0,width:1.2,depth:.7,height:.55};
 await page.route('**/blueprints/p/scene',r=>r.fulfill({json:{revision:1,planRevision:1,config:{views:[view],objects:[bed],style:''}}}));
 await page.route('**/blueprints/p/scene/renders',r=>r.fulfill({json:[]}));
 await page.route('**/blueprints/p/scene/render-settings',r=>r.fulfill({json:{width:1024,height:768,configured:false,model:'',provider:'fal'}}));
 await page.locator('.fe-segment button').nth(2).click();
 const canvas=page.locator('.scene-frame canvas');
 const walk=page.getByRole('button',{name:'Walkthrough',exact:true});
 await walk.click();
 const saved=await canvas.screenshot();
 const box=(await canvas.boundingBox())!;
 const x=Math.round(box.x+box.width/2), y=Math.round(box.y+box.height/2);
 await page.mouse.move(x,y);
 await page.mouse.down();
 await page.mouse.move(x+40,y-25,{steps:4});
 await page.mouse.up();
 const dragged=await canvas.screenshot();
 expect(dragged.equals(saved)).toBe(false);
 await page.mouse.wheel(0,-170);
 expect((await canvas.screenshot()).equals(dragged)).toBe(false);
 await page.getByRole('button',{name:'Preview view'}).click();
 expect((await canvas.screenshot()).equals(saved)).toBe(true);
 await expect(page.getByRole('button',{name:'Save scene'})).toBeDisabled();

 await page.setViewportSize({width:390,height:844});
 const cdp=await page.context().newCDPSession(page);
 await cdp.send('Emulation.setTouchEmulationEnabled',{enabled:true,maxTouchPoints:2});
 await walk.click();
 const mobileStart=await canvas.screenshot();
 const mobile=(await canvas.boundingBox())!;
 const cx=Math.round(mobile.x+mobile.width/2), cy=Math.round(mobile.y+mobile.height/2);
 await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:cx,y:cy,id:1}]});
 await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:cx,y:cy-50,id:1}]});
 await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
 const mobileDragged=await canvas.screenshot();
 expect(mobileDragged.equals(mobileStart)).toBe(false);
 await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:cx-55,y:cy,id:1},{x:cx+55,y:cy,id:2}]});
 await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:cx-32,y:cy,id:1},{x:cx+32,y:cy,id:2}]});
 await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
 expect((await canvas.screenshot()).equals(mobileDragged)).toBe(false);
});

test('walker crosses a confirmed interior door and stops at a closed one',async({page})=>{
  const door={id:'passage',kind:'door' as const,hostWallId:'w6',offsetPx:150,widthPx:100,
    span:null,heightM:2.1,sillM:0,swing:null,hinge:'start' as const,confidence:1,status:'confirmed' as const};
  const model=setReference(fixture({openings:[door]}),{x:100,y:100},{x:500,y:100},4);
  await setup(page,{model});
  const view={id:'walker',name:'Walker',position:{x:450,y:300},yaw:0,pitch:0,horizontalFov:90,eyeHeight:1.6};
  let savedX=view.position.x;
  await page.route('**/blueprints/p/scene',r=>{
    const config=r.request().method()==='PUT'?r.request().postDataJSON().config:{views:[view],objects:[],style:''};
    savedX=config.views[0].position.x;
    return r.fulfill({json:{revision:1,planRevision:model.revision,config}});
  });
  await page.locator('.fe-segment button').nth(2).click();
  const walk=page.getByRole('group',{name:'Walkthrough'});
  await walk.focus();
  for(let i=0;i<10;i++)await walk.press('w');
  await page.getByRole('button',{name:'Save scene',exact:true}).click();
  await expect.poll(()=>savedX).toBeCloseTo(550);
  await page.getByText('Door positions',{exact:true}).click();
  await page.getByLabel('Door 1 closed').check();
  await walk.focus();
  for(let i=0;i<10;i++)await walk.press('s');
  await page.getByRole('button',{name:'Save scene',exact:true}).click();
  await expect.poll(()=>savedX).toBeCloseTo(540);
});

test('phone walkthrough captures its current pose for design and saves it',async({page})=>{
  const model=setReference(fixture(),{x:100,y:100},{x:500,y:100},4);
  await setup(page,{model});
  const view={id:'phone',name:'Phone view',position:{x:300,y:250},yaw:0,pitch:0,horizontalFov:90,eyeHeight:1.6};
  let savedYaw=0;
  await page.route('**/blueprints/p/scene',route=>{
    const config=route.request().method()==='PUT'?route.request().postDataJSON().config:{views:[view],objects:[],style:''};
    savedYaw=config.views[0].yaw;
    return route.fulfill({json:{revision:1,planRevision:model.revision,config}});
  });
  await page.route('**/blueprints/p/scene/render-settings',r=>r.fulfill({json:{width:1024,height:768,configured:false,model:'',provider:'fal'}}));
  await page.route('**/blueprints/p/scene/renders',r=>r.fulfill({json:[]}));
  await page.setViewportSize({width:390,height:844});
  await page.goto('/phone/p');
  await page.getByRole('button',{name:'Floor map',exact:true}).click();
  await expect(page.getByLabel('Camera and furniture placement plan')).toBeVisible();
  await page.getByRole('button',{name:'3D overview'}).click();
  await expect(page.locator('[data-mode=orbit] canvas')).toBeVisible();
  await expect(page.getByLabel('Camera and furniture placement plan')).toBeHidden();
  await page.getByRole('button',{name:'Walk',exact:true}).click();
  const canvas=page.locator('[data-mode=walk] canvas');
  await canvas.scrollIntoViewIfNeeded();
  const box=(await canvas.boundingBox())!;
  const x=box.x+box.width/2,y=box.y+box.height/2;
  await page.mouse.move(x,y);await page.mouse.down();await page.mouse.move(x+35,y,{steps:3});await page.mouse.up();
  await page.getByRole('button',{name:'Design this view'}).click();
  await expect(page.getByAltText('Captured walkthrough view')).toBeVisible();
  await page.getByRole('button',{name:'Save scene',exact:true}).click();
  await expect.poll(()=>savedYaw).toBeGreaterThan(1);
});

test("an open plan can get a floor and a camera through the guided setup",async({page})=>{
  test.setTimeout(60000);
  const model=fixture();
  model.walls=model.walls.filter(w=>w.id!=="w0"&&w.id!=="w1");
  const {puts}=await setup(page,{model:setReference(model,{x:100,y:100},{x:500,y:100},4)});
  let savedView=false;
  await page.route("**/blueprints/p/scene",r=>{
    if(r.request().method()==="PUT"){
      const {planRevision,config}=r.request().postDataJSON();
      savedView=planRevision===2&&config.views.length===1;
      return r.fulfill({json:{revision:1,planRevision,config}});
    }
    return r.fulfill({json:{revision:0,planRevision:null,config:{views:[],objects:[],style:""}}});
  });
  await page.route("**/blueprints/p/scene/renders",r=>r.fulfill({json:[]}));
  await page.route("**/blueprints/p/scene/render-settings",r=>r.fulfill({json:{width:1024,height:768,configured:false,model:"",provider:"fal"}}));
  await page.goto("/plan/p?setup=floor");
  await page.getByRole("button",{name:"Mark walkable floor"}).click();
  const map=page.locator("svg.scene-map");
  async function tap(x:number,y:number){
    const p=await map.evaluate((svg,[x,y])=>{
      const point=new DOMPoint(x,y).matrixTransform((svg as SVGSVGElement).getScreenCTM()!);
      return {x:point.x,y:point.y};
    },[x,y]);
    await page.mouse.click(p.x,p.y);
  }
  await tap(180,170);
  await tap(420,500);
  await expect(page.getByText("Click the camera position inside a room.")).toBeVisible();
  await tap(300,250);
  await expect(page.getByText("Click the direction to face.")).toBeVisible();
  await tap(350,250);
  await expect(page.getByRole("button",{name:"Walkthrough",exact:true})).toBeEnabled();
  await page.getByRole("button",{name:"Save scene",exact:true}).click();
  await expect.poll(()=>savedView).toBe(true);
  expect(puts.at(-1)?.roomZones).toHaveLength(1);
});

test("diagonal wall and door retain their free angle when edited", async () => {
  const {patchOpening,addOpening} = await import("../lib/plan/ops");
  const drawn = addWall(fixture(), {x:200,y:250}, {x:380,y:430}, 9);
  const placed = addOpening(drawn.model,"door",{x:230,y:280},{x:280,y:330})!;
  expect(placed.model.openings.at(-1)?.hostWallId).toBe(drawn.wallId);
  const moved = moveNode(placed.model,drawn.model.walls.at(-1)!.b,{x:400,y:450});
  const resized = patchOpening(moved,placed.openingId,{widthPx:100});
  const [a,b] = resized.openings.at(-1)!.span!;
  expect(b.x-a.x).toBeCloseTo(100/Math.sqrt(2));
  expect(b.y-a.y).toBeCloseTo(b.x-a.x);
});

test("a suggested fourth wall can be previewed, added and undone", async ({page})=>{
  const model=fixture({nodes:[
    {id:"a",x:200,y:150},{id:"b",x:200,y:480},
    {id:"c",x:700,y:480},{id:"d",x:700,y:150}
  ],walls:fixture().walls.slice(0,3).map((w,i)=>({...w,a:"abc"[i],b:"bcd"[i]})),
  openings:[],findings:[]});
  const [a,,,d]=model.nodes;
  model.findings=[{id:"suggested_closure:a:d",category:"suggested_closure",targetIds:["a","d"],
    severity:"warn",anchor:{x:450,y:150},count:1,message:"Possible missing wall along a faint band",
    closure:{start:a,end:d,thicknessPx:18}}];
  await setup(page,{model});
  await page.getByText("Suggested wall closures (1)").click();
  await page.getByRole("button",{name:"Possible missing wall along a faint band"}).click();
  await page.getByRole("button",{name:"Add closing wall"}).click();
  await expect(page.locator('polygon[data-kind="room"]')).toHaveCount(1);
  await page.getByRole("button",{name:"Undo",exact:true}).click();
  await expect(page.locator('polygon[data-kind="room"]')).toHaveCount(0);
});

test("opens a corrected bundle and switches to 3D without aligning its walls", async ({page}) => {
  const original = setReference(fixture(), {x:100,y:100}, {x:500,y:100}, 4);
  const restored = {...original, walls:original.walls.map((w,i) => i===0 ? {...w,thicknessPx:26} : w)};
  const {puts} = await setup(page,{model:original});
  await page.route("**/blueprints/p/plan/restore-bundle", route => {
    expect(route.request().headers()["content-type"]).toContain("multipart/form-data");
    return route.fulfill({json:restored});
  });
  await page.route("**/blueprints/p/plan/align-walls**", () => {
    throw Error("Displaying the corrected model should not request wall alignment");
  });
  await page.route("**/blueprints/p/scene**", route => route.fulfill({json:{
    revision:0,planRevision:null,config:{views:[],objects:[],style:""}
  }}));
  await page.route("**/blueprints/p/scene/renders", route => route.fulfill({json:[]}));
  await page.route("**/blueprints/p/scene/render-settings", route => route.fulfill({json:{
    width:1024,height:768,configured:false,model:"",provider:"fal"
  }}));
  await page.getByText("History & source notes",{exact:true}).click();
  await page.getByLabel("Restore corrected plan (.zip)").setInputFiles({
    name:"florp-plan.zip",mimeType:"application/zip",buffer:Buffer.from("fixture")
  });
  await expect.poll(() => puts.at(-1)?.walls[0].thicknessPx).toBe(26);
  await page.getByRole("radio",{name:"3D",exact:true}).click();
  await expect(page.locator(".scene-frame canvas")).toBeVisible();
  expect(puts.at(-1)?.walls[0].thicknessPx).toBe(26);
});


test("the uncalibrated drawing shows detected appliance footprints", async ({page}) => {
  await setup(page, {model: {...fixture(), roomSymbols: [
    {kind:"fridge", position:{x:270,y:210}, widthPx:38, depthPx:32, rotation:90},
    {kind:"cabinets", position:{x:320,y:160}, widthPx:180, depthPx:30, rotation:0},
  ]}});
  const drawing = page.getByLabel("Plan drawing");
  const fridge = drawing.getByRole("img", {name:"Fridge"});
  await expect(fridge.locator("rect").first()).toBeVisible();
  await expect(fridge).toHaveAttribute("transform", "translate(270 210) rotate(90)");
  await expect(drawing.getByRole("img", {name:"Cabinets"}).locator("rect").first()).toBeVisible();
  await expect(drawing.getByText("Fridge", {exact:true})).toHaveCount(0);
});
