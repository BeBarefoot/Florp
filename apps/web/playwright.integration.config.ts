import {defineConfig} from '@playwright/test';
import {mkdtempSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
const workspace=mkdtempSync(join(tmpdir(),'florp-integration-'));
const api='http://127.0.0.1:8008';
const web='http://127.0.0.1:3108';
export default defineConfig({
 testDir:'./tests',testMatch:'local-integration.spec.ts',timeout:120000,workers:1,
 metadata:{workspace,api},
 use:{baseURL:web,headless:true},
 webServer:[
  {command:'uv run --locked uvicorn app.main:app --host 127.0.0.1 --port 8008',cwd:resolve(__dirname,'../api'),
   env:{DATABASE_URL:`sqlite:///${workspace}/florp.db`,STORAGE_PATH:join(workspace,'storage'),CORS_ORIGINS:web,
        COMFY_API_KEY:'',IMAGE_API_KEY:'',LLM_API_KEY:'',IMAGE_PROVIDER:'fal'},
   url:api+'/health',reuseExistingServer:false,timeout:120000},
  {command:'npm run build && npm run start -- --hostname 127.0.0.1 --port 3108',env:{NEXT_PUBLIC_API_URL:api},
   url:web,reuseExistingServer:false,timeout:120000},
 ],
});
