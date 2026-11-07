import { test, expect, Page } from "@playwright/test";
import type { PlanModel } from "../lib/plan/model";
import { rooms, withDerived, metersPerPixel, wallEndReaches } from "../lib/plan/derive";
import { addWall, moveNode, setReference, decideOpening } from "../lib/plan/ops";
import { wallPieces } from "../lib/plan/mesh";
import { eyeLevelPose, savedPose, verticalFov } from "../lib/plan/camera";
import { blocks, promptFor } from "../lib/plan/scene";

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

async function setup(page: Page, opts: { empty?: boolean; model?: PlanModel } = {}) {
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
  await page.goto("/plan/p");
  await expect(page.getByText("My house", { exact: true })).toBeVisible();
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
  expect(win.offsetPx + win.widthPx / 2).toBeCloseTo(((100 + 60) / 400) * 440, 6);
  expect(moved.nodes.find((n) => n.id === "n1")).toEqual(m.nodes.find((n) => n.id === "n1"));
  const t = addWall(m, { x: 300, y: 100 }, { x: 300, y: 600 }, 12);
  expect(t.model.walls.length).toBe(m.walls.length + 3);
  expect(rooms(t.model).length).toBe(3);
  expect(m.rooms[0].areaPx2).toBeCloseTo((400 - 12) * (500 - 12), 3);
  const pieces = wallPieces(decideOpening(m, "maybe", "confirm")!);
  expect(pieces.find((p) => p.id === "w0")!.lengthM).toBeCloseTo(4, 6);
  expect(pieces.find((p) => p.id === "w3")!.chunks.length).toBe(3);
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
  expect(before.prompt).not.toContain("toilet");
  await page.setViewportSize({width:950,height:850});
  await page.reload();
  await enter();
  await expect(page.getByRole("button",{name:"Back to orbit"})).toBeVisible();
  const after=await depth();
  expect(after.view).toEqual(before.view);
  expect(after.depth).toEqual(before.depth);
  expect(after.mask).toEqual(before.mask);
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
  const parts=blocks({id:"b",kind:"bed",position,rotation:0,width:1.9,depth:2.12,height:.9,
    mattressWidth:1.8,mattressDepth:2});
  expect(parts[2].size[0]).toBeCloseTo(1.8);
  expect(parts[2].size[2]).toBeCloseTo(2);
  expect(promptFor(view,["Space type: bedroom."],"Oak")).toBe([
    "Scene facts: Photorealistic interior from the supplied depth view.",
    "Eye height 1.60 m; horizontal field of view 90 degrees.",
    "Space type: bedroom.",
    "Preserve the camera, walls, existing openings, visible object positions and proportions. Do not add architectural openings or reveal objects behind walls.",
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
  await scan.click();
  await expect(page.getByText("Review the outlined suggestions. Nothing has been inserted.")).toBeVisible();
  await expect(outlines).toHaveCount(0);
});
