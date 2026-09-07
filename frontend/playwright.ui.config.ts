import { defineConfig } from "@playwright/test";
import base from "./playwright.config";

export default defineConfig(base, {
  projects: base.projects?.map((project) => project.name === "desktop-chromium"
    ? { ...project, use: { ...project.use, viewport: { width: 1920, height: 1080 } } }
    : project),
  testMatch: "ui-smoke.spec.ts",
  webServer: {
    command: "npm run start -- --port 3100",
    url: "http://localhost:3100",
    reuseExistingServer: !process.env.CI,
  },
  use: { baseURL: "http://localhost:3100" },
});
