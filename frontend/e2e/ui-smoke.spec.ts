import { expect, test } from "@playwright/test";

// Isolated UI checks: only the frontend server is required.
test("configuration workspace and market execution chart work on desktop and mobile", async ({ page, baseURL }, testInfo) => {
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
  const symbol = "BTC-USDT-SWAP";
  const interval = 900_000;
  const last = Math.floor(Date.now() / interval) * interval;
  const candles = Array.from({ length: 24 }, (_, i) => ({ timestamp: last - (23-i)*interval,
    open: 100, high: 103, low: 98, close: 101, volume: 100 }));
  const marketResponses: Record<string, object> = {
    "/api/v1/backtest/assets": { assets: [{ symbol }] },
    "/api/v1/execution/trading-configs": { configs: [{ symbol, mode: "PRODUCTION", status: "ACTIVE", config: { activatedAt: last-5*interval } }] },
    "/api/v1/execution/positions": { positions: [{ id: "production", order_id: "filled", symbol, direction: "LONG",
      entry_price: 100, quantity: 1, status: "OPENED", opened_at: last+1000, execution_mode: "PRODUCTION",
      stop_loss_price: 95, take_profit_prices: [110] }] },
    "/api/v1/execution/orders": { orders: [{ id: "pending", symbol, side: "BUY", type: "LIMIT", price: 99,
      quantity: 1, status: "OPEN", created_at: last+2000, execution_mode: "PRODUCTION", take_profit_prices: [] }] },
    "/api/v1/execution/trades/history": { trades: [{ position_id: "closed", symbol, direction: "SHORT",
      entry_price: 102, exit_price: 100, quantity: 1, pnl: 2, reason: "TP", closed_at: last-interval,
      duration_seconds: 900, execution_mode: "PRODUCTION" }] },
    "/api/v1/data/market/candles": { symbol, timeframe: "M15", candles },
    "/api/v1/exchange/exchange/market-candles": { symbol, timeframe: "M15", candles },
    "/api/v1/exchange/exchange/history": { jobs: [{ id: "history", symbol,
      timeframes: ["M5","M15","M30","H1","H4","D1"], status: "RUNNING", progress: 20, ingested: 100, timeframe_status: {} }] },
    "/api/v1/elliott/elliott/history": { symbol, status: "COMPLETED", patterns: [], entries: [], trades: [] },
    "/api/v1/elliott/elliott/patterns": { symbol, patterns: [] },
    "/api/v1/elliott/elliott/entries": { symbol, entries: [] },
  };
  await page.route("http://localhost:8050/**", async (route) => {
    if (route.request().method() === "PUT") {
      await route.fulfill({ status: 400, json: { detail: "Invalid template" } });
    } else {
      await route.fulfill({ json: marketResponses[new URL(route.request().url()).pathname] ?? { configurations: [] }, headers: { "access-control-allow-origin": new URL(baseURL!).origin, "access-control-allow-credentials": "true" } });
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
  await page.evaluate(() => {
    const labels: string[] = [];
    Object.assign(window, { chartLabels: labels });
    const fillText = CanvasRenderingContext2D.prototype.fillText;
    CanvasRenderingContext2D.prototype.fillText = function (text, x, y, maxWidth) {
      if (/PRODUCTION|SL|TP1|История paper|мин/.test(text)) labels.push(text);
      if (maxWidth === undefined) fillText.call(this,text,x,y); else fillText.call(this,text,x,y,maxWidth);
    };
  });
  if (testInfo.project.name === "mobile-chromium") await page.getByRole("button", { name: "Открыть меню" }).click();
  await page.getByRole("link", { name: "Рынок", exact: true }).click();
  await expect(page.getByText("Исполнения: 2 · заявки: 1", { exact: true })).toBeVisible();
  const labels = () => page.evaluate(() => (window as unknown as { chartLabels: string[] }).chartLabels);
  await expect.poll(labels).toContain("PRODUCTION · LONG · вход 100");
  await expect.poll(labels).toContain("SL · -5.00%");
  await expect.poll(labels).toContain("TP1 · +10.00%");
  await expect.poll(labels).toContain("История paper | Live");
  await expect.poll(async () => (await labels()).some((text) => text.includes("PRODUCTION · выход 100"))).toBe(true);
  await page.getByRole("button", { name: "Линейка", exact: true }).click();
  const canvas = page.locator("canvas").last();
  await canvas.click({ position: { x: 60, y: 200 } });
  await canvas.click({ position: { x: 160, y: 250 } });
  await expect.poll(async () => (await labels()).some((text) => /%\) · \d+ мин/.test(text))).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("market.png"), fullPage: true });

  // Both live capital modes must reach the API, including on a mobile screen.
  marketResponses["/api/v1/execution/portfolios"] = { portfolios: [{
    id: "capital-modes", name: "Режимы капитала", description: "",
    assets: ["AVAX-USDT-SWAP", "ETH-USDT-SWAP"].map(symbol => ({
      symbol, configuration_id: "config", allocation_percent: 50, config: {},
    })),
  }] };
  const activations: object[] = [];
  await page.route("**/api/v1/execution/portfolios/capital-modes/live", async route => {
    activations.push(route.request().postDataJSON());
    await route.fulfill({ json: { activated_symbols: ["AVAX-USDT-SWAP", "ETH-USDT-SWAP"] },
      headers: { "access-control-allow-origin": new URL(baseURL!).origin } });
  });
  await page.goto("/portfolios");
  await page.getByLabel("Live-режим").click();
  await page.getByRole("option", { name: "OKX Production" }).click();
  await page.getByLabel("Live-капитал, USDT").fill("140");
  page.on("dialog", dialog => dialog.accept());
  await page.getByRole("button", { name: "Добавить в live" }).click();
  await expect.poll(() => activations).toEqual([
    { mode: "PRODUCTION", capital: 140, capital_mode: "ALLOCATED" },
  ]);
  await page.getByLabel("Режим капитала").click();
  await page.getByRole("option", { name: "Последовательно · общий капитал" }).click();
  await page.getByRole("button", { name: "Добавить в live" }).click();
  await expect.poll(() => activations).toEqual([
    { mode: "PRODUCTION", capital: 140, capital_mode: "ALLOCATED" },
    { mode: "PRODUCTION", capital: 140, capital_mode: "SEQUENTIAL" },
  ]);
  expect(errors).toEqual([]);
});

test("portfolio live activation sends the chosen capital mode and validates allocations", async ({ page, baseURL }) => {
  let nonce="";
  await page.route("http://localhost:8080/**",async route => {
    const url=new URL(route.request().url());
    if (url.pathname.endsWith("/auth")) {
      nonce=url.searchParams.get("nonce") ?? "";
      const redirect=new URL(url.searchParams.get("redirect_uri")!);
      redirect.hash=new URLSearchParams({code:"ui-test",state:url.searchParams.get("state")!}).toString();
      await route.fulfill({status:302,headers:{location:redirect.toString()}});return;
    }
    const encode=(data:object)=>Buffer.from(JSON.stringify(data)).toString("base64url");
    const jwt=`${encode({alg:"none"})}.${encode({sub:"ui-test",nonce,realm_access:{roles:["admin"]},exp:Math.floor(Date.now()/1000)+3600,iat:Math.floor(Date.now()/1000)})}.signature`;
    await route.fulfill({json:{access_token:jwt,id_token:jwt,refresh_token:jwt,expires_in:3600},
      headers:{"access-control-allow-origin":new URL(baseURL!).origin,"access-control-allow-credentials":"true"}});
  });
  const activations:Array<{mode:string;capital:number;capital_mode:string}>=[];
  let allocation=50;
  await page.route("http://localhost:8050/**",async route => {
    const path=new URL(route.request().url()).pathname;
    let response:object={configurations:[]};
    if (path==="/api/v1/execution/portfolios") response={portfolios:[{
      id:"portfolio-test",name:"Портфель",description:"",updated_at:new Date().toISOString(),
      assets:["AVAX-USDT-SWAP","ETH-USDT-SWAP"].map(symbol=>({symbol,configuration_id:"config",allocation_percent:allocation,config:{}})),
    }]};
    if (path==="/api/v1/execution/portfolios/portfolio-test/live") {
      activations.push(route.request().postDataJSON());response={activated_symbols:["AVAX-USDT-SWAP","ETH-USDT-SWAP"]};
    }
    await route.fulfill({json:response,headers:{"access-control-allow-origin":new URL(baseURL!).origin,"access-control-allow-credentials":"true"}});
  });
  await page.goto("/portfolios");
  await page.getByLabel("Live-капитал, USDT").fill("1000");
  await page.getByRole("button",{name:"Добавить в live"}).click();
  await expect.poll(()=>activations).toEqual([{mode:"PAPER",capital:1000,capital_mode:"ALLOCATED"}]);
  await page.getByLabel("Режим капитала").click();
  await page.getByRole("option",{name:"Последовательно · общий капитал"}).click();
  await page.getByRole("button",{name:"Добавить в live"}).click();
  await expect.poll(()=>activations.length).toBe(2);
  expect(activations[1]).toEqual({mode:"PAPER",capital:1000,capital_mode:"SEQUENTIAL"});
  allocation=100;
  await page.reload();
  await page.getByLabel("Live-капитал, USDT").fill("1000");
  await expect(page.getByRole("button",{name:"Добавить в live"})).toBeDisabled();
  await page.getByLabel("Режим капитала").click();
  await page.getByRole("option",{name:"Последовательно · общий капитал"}).click();
  await expect(page.getByRole("button",{name:"Добавить в live"})).toBeEnabled();
});
