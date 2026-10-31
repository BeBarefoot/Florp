import {defineConfig} from '@playwright/test';
export default defineConfig({
 testDir:'./tests', timeout:30000, workers:1,
 use:{baseURL:'http://127.0.0.1:3000',headless:true},
 webServer:{command:'npm run dev -- --hostname 127.0.0.1 --port 3000',env:{NEXT_PUBLIC_FLORP_ADMIN:'1'},url:'http://127.0.0.1:3000',reuseExistingServer:!process.env.CI,timeout:120000},
});
