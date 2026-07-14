import {defineConfig,devices} from "@playwright/test";

export default defineConfig({
  testDir:"./e2e",
  timeout:60_000,
  expect:{timeout:10_000},
  outputDir:"test-results",
  fullyParallel:false,
  forbidOnly:Boolean(process.env.CI),
  retries:process.env.CI?1:0,
  workers:1,
  reporter:[["line"],["html",{outputFolder:"playwright-report",open:"never"}]],
  use:{
    baseURL:process.env.PLAYWRIGHT_BASE_URL??"http://127.0.0.1:3000",
    headless:true,
    screenshot:"only-on-failure",
    video:"retain-on-failure",
    trace:"retain-on-failure",
  },
  projects:[{name:"chromium",use:{...devices["Desktop Chrome"]}}],
});