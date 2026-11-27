import {test, expect} from '@playwright/test';

test('upload explains the page contract and retains plans after a rejected file', async ({page}) => {
  await page.route('**/projects/demo/blueprints', async route => {
    if (route.request().method() === 'POST') {
      await route.fulfill({status:415, json:{detail:'Could not read plan. Use a valid PNG, JPEG, WebP or unlocked PDF.'}});
    } else {
      await route.fulfill({json:[{id:'saved', filename:'Saved plan', width:800, height:600}]});
    }
  });
  await page.goto('/project/demo');
  await expect(page.getByText('PDFs use the first page only', {exact:false})).toBeVisible();
  await expect(page.getByLabel('PDF page')).toHaveCount(0);
  await page.getByLabel('Floor plan file').setInputFiles({name:'broken.png', mimeType:'image/png', buffer:Buffer.from('broken')});
  await page.getByRole('button', {name:'Upload plan'}).click();
  await expect(page.getByRole('alert').filter({hasText:'Could not read plan'})).toContainText('Could not read plan');
  await expect(page.getByRole('heading', {name:'Saved plan'})).toBeVisible();
  await expect(page.getByRole('button', {name:'Upload plan'})).toBeEnabled();
});

test("desktop home retries the same upload and previews page one before extraction", async ({page}) => {
  await page.route("**/projects", route => route.fulfill({json: []}));
  await page.route("**/health", route => route.fulfill({json: {ok:true}}));
  await page.route("**/blueprints/floor/preview", route => route.fulfill({
    contentType: "image/svg+xml", body: '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"/>',
  }));
  const attempts: string[] = [];
  await page.route("**/home-uploads/*", route => {
    attempts.push(route.request().url());
    return attempts.length === 1
      ? route.fulfill({status: 503, json: {detail: "Try again"}})
      : route.fulfill({json: {id:"floor",project_id:"home",filename:"Ground.pdf",width:100,height:100}});
  });
  await page.route("**/blueprints/floor/info", route => route.fulfill({json:{id:"floor",filename:"Ground.pdf"}}));
  await page.route("**/blueprints/floor/plan**", route => route.fulfill({json:{revision:0,model:null}}));
  await page.goto("/");
  await page.locator("input[type=file]").setInputFiles({name:"Ground.pdf",mimeType:"application/pdf",buffer:Buffer.from("%PDF")});
  await page.getByRole("button", {name:"Retry upload"}).click();
  await expect(page.getByText("PDF · Page 1")).toBeVisible();
  await expect(page.getByRole("img",{name:"Drawing ready for extraction"})).toBeVisible();
  expect(attempts).toHaveLength(2);
  expect(attempts[0]).toBe(attempts[1]);
  await page.getByRole("button", {name:"Analyze plan"}).click();
  await expect(page).toHaveURL(/\/plan\/floor\?review=1$/);
});
