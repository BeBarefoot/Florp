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
