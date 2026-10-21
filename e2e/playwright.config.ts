import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  timeout: 30_000,
  workers: 1,
  use: {
    channel: "chrome",
    headless: true,
  },
  webServer: {
    command: "../.venv/bin/python ../scripts/e2e_serve.py",
    url: "http://127.0.0.1:8875/health",
    reuseExistingServer: false,
    timeout: 30_000,
  },
});
