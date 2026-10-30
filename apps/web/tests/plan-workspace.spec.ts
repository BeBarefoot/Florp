import { test, expect, Page } from "@playwright/test";
import { moveEndpoint, geometry } from "../lib/planWorkspace";
const base = {
  width: 1000,
  height: 700,
  objects: [
    {
      id: "a",
      kind: "wall",
      start: { x: 100, y: 100 },
      end: { x: 900, y: 100 },
      thickness_px: 12,
      host_id: null,
      reviewed: false,
      uncertain: true,
      height_m: 2.8,
      sill_m: 0,
    },
  ],
  reference: null,
  warnings: [],
};
async function setup(page: Page, empty = false, conflict = false) {
  let doc: any = structuredClone(base),
    version = 0;
  if (empty) doc.objects = [];
  await page.route("**/blueprints/p/info", (r) =>
    r.fulfill({
      json: {
        id: "p",
        project_id: "house",
        filename: "My house",
        width: 1000,
        height: 700,
      },
    }),
  );
  await page.route("**/blueprints/p/workspace**", async (r) => {
    const request = r.request(),
      url = request.url();
    if (url.includes("/extract"))
      return r.fulfill({ json: { document: base } });
    if (url.includes("/history")) return r.fulfill({ json: [] });
    if (request.method() === "PUT") {
      if (conflict)
        return r.fulfill({
          status: 409,
          json: { detail: "A newer revision exists" },
        });
      const body = request.postDataJSON();
      doc = body.document;
      version++;
    }
    return r.fulfill({
      json: {
        version,
        document: doc,
        derived: {
          px_per_meter: doc.reference ? 100 : null,
          rooms: [],
          bounds_px: null,
          margin_px: null,
        },
      },
    });
  });
  await page.goto("/plan/p");
  await expect(page.getByText("My house", { exact: true })).toBeVisible();
}
async function at(page: Page, x: number, y: number) {
  const p = await page.locator(".pw-canvas svg").evaluate(
    (svg, [x, y]) => {
      const m = (svg as SVGSVGElement).getScreenCTM()!;
      const p = new DOMPoint(x, y).matrixTransform(m);
      return { x: p.x, y: p.y };
    },
    [x, y],
  );
  return p;
}
test("upload result appears before scale; measurement follows pointer and survives reload", async ({
  page,
}) => {
  await setup(page, true);
  await expect(page.getByText("1 walls · 0 openings")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "3D", exact: true }),
  ).toBeDisabled();
  await page
    .getByRole("button", { name: "Set measurement", exact: true })
    .click();
  const a = await at(page, 100, 100),
    b = await at(page, 900, 100);
  await page.mouse.click(a.x, a.y);
  await page.mouse.move(b.x, b.y);
  const line = page.getByTestId("measurement-line");
  await expect(line).toHaveAttribute("x2", /89[89]|900/);
  await page.mouse.click(b.x, b.y);
  await page.getByLabel("Known distance").fill("8");
  await page.getByRole("button", { name: "Use measurement" }).click();
  await expect(page.getByRole("status")).toHaveText("Saved");
  await expect(
    page.getByRole("button", { name: "3D", exact: true }),
  ).toBeEnabled();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export 3D", exact: true }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("florp-plan.glb");
  const fs = await import("node:fs/promises");
  expect(
    (await fs.readFile((await download.path())!)).subarray(0, 4).toString(),
  ).toBe("glTF");
  await page.reload();
  await expect(page.getByText("Reference measurement set")).toBeVisible();
  await page.screenshot({
    path: "/tmp/florp-plan-workspace.png",
    fullPage: true,
  });
});
test("selected wall has two handles; false detection and undo edit actual model", async ({
  page,
}) => {
  await setup(page);
  const p = await at(page, 500, 100);
  await page.mouse.click(p.x, p.y);
  await expect(page.locator(".pw-canvas circle")).toHaveCount(2);
  await page.getByRole("button", { name: "False detection" }).click();
  await expect(page.getByText("0 walls · 0 openings")).toBeVisible();
  await page.getByRole("button", { name: "Undo", exact: true }).click();
  await expect(page.locator(".pw-canvas circle")).toHaveCount(2);
  await expect(page.getByRole("status")).toHaveText("Saved");
});
test("conflict keeps local edits and exposes recovery instead of claiming saved", async ({
  page,
}) => {
  await setup(page, false, true);
  const p = await at(page, 500, 100);
  await page.mouse.click(p.x, p.y);
  await page.getByRole("button", { name: "False detection" }).click();
  await expect(page.locator(".pw-error")).toContainText("newer revision");
  await expect(page.getByRole("status")).toContainText("Save failed");
  await expect
    .poll(() => page.evaluate(() => !!localStorage.getItem("florp-plan-p")))
    .toBeTruthy();
  await expect(page.getByText("0 walls · 0 openings")).toBeVisible();
});

test("shared endpoint edit preserves hosted opening fractions", async () => {
  const d: any = structuredClone(base);
  d.reference = { start: [100, 100], end: [900, 100], length_cm: 800 };
  d.objects.push({
    ...d.objects[0],
    id: "window",
    kind: "window",
    host_id: "a",
    start: { x: 300, y: 100 },
    end: { x: 500, y: 100 },
    height_m: 1.2,
    sill_m: 0.9,
  });
  const next = moveEndpoint(d, "a", "end", { x: 900, y: 300 });
  expect(next.objects[1].start.y).toBeCloseTo(150);
  expect(next.objects[1].end.y).toBeCloseTo(200);
  const g = geometry(next, []);
  expect(g.openings).toHaveLength(1);
  expect(g.openings[0].wall_id).toBe("a");
  expect(g.openings[0].width_m).toBeGreaterThan(2);
});

test("photo straightening collects four corners and creates a separate plan", async ({
  page,
}) => {
  await setup(page);
  let payload: any;
  await page.route("**/blueprints/p/workspace/straighten", async (route) => {
    payload = route.request().postDataJSON();
    await route.fulfill({
      json: { id: "rectified", reference_preserved: false },
    });
  });
  await page.route("**/blueprints/rectified/info", (r) =>
    r.fulfill({
      json: {
        id: "rectified",
        project_id: "house",
        filename: "Straightened plan",
        width: 1000,
        height: 700,
      },
    }),
  );
  await page.route("**/blueprints/rectified/workspace", (r) =>
    r.fulfill({
      json: {
        version: 1,
        document: base,
        derived: {
          px_per_meter: null,
          rooms: [],
          bounds_px: null,
          margin_px: null,
        },
      },
    }),
  );
  await page.getByText("Source notes", { exact: true }).click();
  await page
    .getByRole("button", { name: "Straighten photographed sheet", exact: true })
    .click();
  for (const [x, y] of [
    [50, 50],
    [950, 80],
    [900, 650],
    [60, 620],
  ]) {
    const p = await at(page, x, y);
    await page.mouse.click(p.x, p.y);
  }
  await expect(page.getByText("4 / 4 corners")).toBeVisible();
  await page.getByLabel("Custom page ratio").fill("1.5");
  await page.getByRole("button", { name: "Create straightened plan" }).click();
  await expect(page).toHaveURL("/plan/rectified");
  expect(payload.page_aspect_ratio).toBe(1.5);
  expect(payload.corners).toHaveLength(4);
});

test("mobile canvas and inspector remain bounded without covering footer", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await setup(page);
  const canvas = await page.locator(".pw-canvas").boundingBox();
  const inspector = await page.locator(".pw-inspector").boundingBox();
  const footer = await page.locator(".pw-footer").boundingBox();
  expect(canvas!.height).toBeGreaterThan(300);
  expect(inspector!.y).toBeGreaterThanOrEqual(canvas!.y + canvas!.height);
  expect(footer!.y).toBeGreaterThanOrEqual(inspector!.y + inspector!.height);
});
