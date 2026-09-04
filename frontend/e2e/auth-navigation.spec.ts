import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

const username = process.env.E2E_USERNAME ?? "viewer";
const password = process.env.E2E_PASSWORD ?? "CHANGE_ME";

async function signIn(page: Page, user = username) {
  await page.goto("/");
  await page.getByRole("button", { name: /Войти через Keycloak/ }).click();
  await page.getByLabel(/Username or email|Имя пользователя/).fill(user);
  await page.getByLabel(/Password|Пароль/).fill(password);
  await page.getByRole("button", { name: /Sign In|Войти/ }).click();
  await page.waitForURL((url) => url.origin === "http://localhost:3000" && !url.hash.includes("code="));
  await expect(page.getByRole("button", { name: "Выйти" })).toBeVisible();
  await expect.poll(() => page.evaluate(() => location.hash)).toBe("");
}

test("user can sign in, switch theme and open every section", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Переключить цветовую тему" }).click();
  await signIn(page);
  await expect(page.getByRole("heading", { name: new RegExp(`Добрый день, ${username}`) })).toBeVisible();

  for (const route of ["market", "scenarios", "trades", "learning", "backtest"]) {
    await page.goto(`/${route}`);
    await expect(page).toHaveURL(new RegExp(`/${route}$`));
  }
});

test("user can add an asset and run an isolated backtest", async ({ page }, testInfo) => {
  const asset = `E2E${testInfo.workerIndex}${testInfo.retry}${Date.now() % 100000}-USDT-SWAP`;
  await page.route("**/api/v1/backtest/backtests", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify({ id: "e2e-backtest" }) });
    } else {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ runs: [] }) });
    }
  });
  await page.route("**/api/v1/backtest/backtests/e2e-backtest", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "e2e-backtest",
        symbol: "SOL-USDT-SWAP",
        timeframe: "M15",
        status: "COMPLETED",
        progress: 100,
        created_at: new Date().toISOString(),
        result: {
          initial_capital: 10000,
          final_capital: 10500,
          net_profit: 500,
          total_return_percent: 5,
          max_drawdown_percent: 1,
          win_rate: 60,
          profit_factor: 1.8,
          total_trades: 1,
          average_trade: 500,
          sharpe_ratio: 1.2,
          benchmark_return_percent: 3,
          trades: [],
          equity: [{ timestamp: 0, equity: 10000 }, { timestamp: 60000, equity: 10500 }],
        },
      }),
    });
  });
  await signIn(page, "admin");
  await page.goto("/backtest");
  await page.getByRole("button", { name: "Добавить актив" }).click();
  await page.getByLabel("Символ актива").fill(asset);
  await page.getByRole("button", { name: "Добавить", exact: true }).click();
  await expect(page.getByText(asset, { exact: true })).toBeVisible();
  await page.getByRole("tab", { name: /Настройка и запуск/ }).click();
  await page.getByRole("button", { name: "Запустить бэктест" }).click();
  await expect(page.getByText("Кривая капитала")).toBeVisible();
  await expect(page.getByText("Журнал сделок")).toBeVisible();
});

test("trader can submit a validated paper order", async ({ page }) => {
  await page.route("**/api/v1/execution/orders", async (route) => {
    const body = route.request().postDataJSON() as { side: string; type: string; quantity: number };
    expect(body).toMatchObject({ side: "BUY", type: "LIMIT", quantity: 0.001 });
    await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ order_id: "e2e", status: "PENDING" }) });
  });
  await signIn(page, "trader");
  await page.goto("/trades");
  await expect(page).toHaveURL(/\/trades$/);
  const orderType = page.getByRole("combobox", { name: "Тип" });
  await orderType.press("ArrowDown");
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Enter");
  await expect(orderType).toContainText("Limit");
  await page.getByLabel("Количество").fill("0.001");
  await page.getByLabel("Цена").fill("50000");
  await page.getByRole("button", { name: "BUY BTC-USDT-SWAP" }).click();
  await expect(page.getByText("Ордер успешно отправлен в paper-контур")).toBeVisible();
});
