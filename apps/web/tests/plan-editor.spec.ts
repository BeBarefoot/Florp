import { test, expect, Page } from "@playwright/test";
import type { PlanModel } from "../lib/plan/model";
import { rooms, withDerived, metersPerPixel } from "../lib/plan/derive";
import { addWall, moveNode, setReference, decideOpening } from "../lib/plan/ops";
import { wallPieces } from "../lib/plan/mesh";

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
  await page.route("**/blueprints/p/info", (r) =>
    r.fulfill({ json: { id: "p", project_id: "house", filename: "My house", width: 1000, height: 700 } }),
  );
  await page.route("**/blueprints/p/preview", (r) => r.fulfill({ status: 404, body: "" }));
  await page.route("**/blueprints/p/plan**", async (r) => {
    const req = r.request(),
      url = req.url();
    if (url.includes("/extract")) {
      current = fixture();
      revision++;
      return r.fulfill({ json: { revision, model: current } });
    }
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
  return { puts };
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
