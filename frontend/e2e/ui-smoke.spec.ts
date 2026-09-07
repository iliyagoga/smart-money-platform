import { expect, test } from "@playwright/test";

// Isolated UI checks: only the frontend server is required.
test("wide Elliott configuration workspace works on desktop and mobile", async ({ page, baseURL }, testInfo) => {
  let nonce = "";
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("http://localhost:8080/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/auth")) {
      nonce = url.searchParams.get("nonce") ?? "";
      const redirect = new URL(url.searchParams.get("redirect_uri")!);
      redirect.hash = new URLSearchParams({ code: "ui-test", state: url.searchParams.get("state")! }).toString();
      await route.fulfill({ status: 302, headers: { location: redirect.toString() } });
      return;
    }
    const encode = (data: object) => Buffer.from(JSON.stringify(data)).toString("base64url");
    const jwt = `${encode({ alg: "none" })}.${encode({ sub: "ui-test", nonce, preferred_username: "admin", realm_access: { roles: ["admin"] }, exp: Math.floor(Date.now() / 1000) + 3600, iat: Math.floor(Date.now() / 1000) })}.signature`;
    await route.fulfill({ json: { access_token: jwt, id_token: jwt, refresh_token: jwt, expires_in: 3600 }, headers: { "access-control-allow-origin": new URL(baseURL!).origin, "access-control-allow-credentials": "true" } });
  });
  await page.route("http://localhost:8050/**", async (route) => {
    if (route.request().method() === "PUT") {
      await route.fulfill({ status: 400, json: { detail: "Invalid template" } });
    } else {
      await route.fulfill({ json: { configurations: [] }, headers: { "access-control-allow-origin": new URL(baseURL!).origin, "access-control-allow-credentials": "true" } });
    }
  });
  await page.goto("/configurations");
  await expect(page.getByRole("heading", { name: "Конфигурации", exact: true })).toBeVisible();
  const main = await page.locator("main").boundingBox();
  expect(main!.width).toBeGreaterThan(page.viewportSize()!.width * 0.95);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize()!.width);
  await expect(page.getByRole("link", { name: "Сценарии", exact: true })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Обучение", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Переключить цветовую тему" }).click();
  await page.screenshot({ path: testInfo.outputPath("workspace.png"), fullPage: true });
  expect(errors).toEqual([]);
});
