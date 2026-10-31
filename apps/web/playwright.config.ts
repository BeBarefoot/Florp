import {defineConfig} from '@playwright/test';
const port = Number(process.env.FLORP_TEST_PORT || 3107);
const origin = `http://127.0.0.1:${port}`;
export default defineConfig({
 testDir:'./tests', timeout:30000, workers:1,
 use:{baseURL:origin,headless:true},
 webServer:{command:`npm run dev -- --hostname 127.0.0.1 --port ${port}`,env:{NEXT_PUBLIC_FLORP_ADMIN:'1'},url:origin,reuseExistingServer:false,timeout:120000},
});
