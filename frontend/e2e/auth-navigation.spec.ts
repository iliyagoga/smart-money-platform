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
}

test("user can sign in, switch theme and open every section", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Переключить цветовую тему" }).click();
  await signIn(page);
  await expect(page.getByRole("heading", { name: new RegExp(`Добрый день, ${username}`) })).toBeVisible();

  for (const route of ["market", "trades", "configurations", "portfolios", "backtest", "replay"]) {
    await page.goto(`/${route}`);
    await expect(page).toHaveURL(new RegExp(`/${route}$`));
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.getByText("404", { exact: true })).toHaveCount(0);
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
  await page.getByRole("button", { name: "Запустить бэктест" }).click();
  await expect(page.getByText("Кривая капитала")).toBeVisible();
  await expect(page.getByText("Журнал сделок")).toBeVisible();
});

test("trader can simulate an Elliott signal", async ({ page }) => {
  await page.route("**/api/v1/execution/trades/assets", (route) => route.fulfill({
    json: { assets: [{ symbol: "BTC-USDT-SWAP" }] },
  }));
  await page.route("**/api/v1/decision/signals/simulate-elliott", async (route) => {
    expect(route.request().postDataJSON()).toEqual({ symbol: "BTC-USDT-SWAP", direction: "LONG" });
    await route.fulfill({ json: { approved: true } });
  });
  await signIn(page, "trader");
  await page.goto("/trades");
  await page.getByLabel("Актив", { exact: true }).click();
  await page.getByRole("option", { name: "BTC-USDT-SWAP" }).click();
  await page.getByRole("button", { name: "Имитировать сигнал" }).click();
  await expect(page.getByText("Elliott-сигнал принят и отправлен на исполнение")).toBeVisible();
});
