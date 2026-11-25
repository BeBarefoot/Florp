import {defineConfig} from '@playwright/test';
const port = Number(process.env.FLORP_TEST_PORT || 3107);
const origin = `http://127.0.0.1:${port}`;
export default defineConfig({
 testDir:'./tests', testIgnore:'local-integration.spec.ts', timeout:30000, workers:1,
 use:{baseURL:origin,headless:true,launchOptions:process.env.FLORP_TEST_CHROMIUM?{executablePath:process.env.FLORP_TEST_CHROMIUM,args:["--enable-unsafe-swiftshader"]}:undefined},
 webServer:{command:`npm run dev -- --hostname 127.0.0.1 --port ${port}`,env:{NEXT_PUBLIC_FLORP_ADMIN:'1'},url:origin,reuseExistingServer:false,timeout:120000},
});
