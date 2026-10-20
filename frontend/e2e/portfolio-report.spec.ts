import { expect, test } from "@playwright/test";
import { defaultBacktestSettings } from "../lib/backtest/defaultSettings";

test("portfolio run renders one report with contributions and asset trades", async ({ page }) => {
  await page.route("**/api/v1/execution/portfolios", route => route.fulfill({ json: { portfolios: [{
    id: "portfolio-test", name: "Тестовый портфель", description: "", updated_at: new Date().toISOString(),
    assets: ["AAA", "BBB"].map(symbol => ({ symbol, configuration_id: "config", allocation_percent: 50, config: defaultBacktestSettings })),
  }] } }));
  await page.route("**/api/v1/execution/configuration-library", route => route.fulfill({ json: { configurations: [] } }));
  await page.route("**/api/v1/execution/portfolios/portfolio-test/live", async route => {
    const body = route.request().postDataJSON();
    expect(body).toEqual({ mode: "PRODUCTION", capital: 140 });
    await route.fulfill({ json: { id: "portfolio-test", mode: "PRODUCTION", capital: 140, activated_symbols: ["AAA", "BBB"] } });
  });
  await page.route("**/api/v1/backtest/portfolio-backtests", async route => {
    const body = route.request().postDataJSON();
    expect(body.initial_capital).toBe(20000);
    expect(body.assets).toHaveLength(2);
    expect(body.assets.map((asset: { allocation_percent: number }) => asset.allocation_percent)).toEqual([50, 50]);
    await route.fulfill({ status: 202, json: { id: "portfolio-run" } });
  });
  const start = Date.UTC(2025, 0, 1), end = Date.UTC(2025, 1, 1);
  await page.route("**/api/v1/backtest/backtests/portfolio-run", route => route.fulfill({ json: {
    id: "portfolio-run", symbol: "Тестовый портфель", timeframe: "PORTFOLIO", status: "COMPLETED", progress: 100,
    created_at: new Date().toISOString(), result: {
      initial_capital: 20000, final_capital: 20200, net_profit: 200, total_return_percent: 1,
      max_drawdown_percent: 1, win_rate: 50, total_trades: 2, average_trade: 100, sharpe_ratio: 1, benchmark_return_percent: 2,
      equity: [{ timestamp: start, equity: 20000 }, { timestamp: end, equity: 20200 }],
      trades: ["AAA", "BBB"].map((symbol, index) => ({
        id: index + 1, symbol, leverage: 1, direction: "LONG", entry_time: start, exit_time: end,
        entry_price: 100, exit_price: 101, quantity: 1, pnl: index ? -100 : 300, pnl_percent: index ? -1 : 3, reason: "END_OF_DATA",
      })),
      portfolio: { name: "Тестовый портфель", cash: 0, assets: ["AAA", "BBB"].map((symbol, index) => ({
        symbol, run_id: `child-${index}`, allocation_percent: 50, initial_capital: 10000,
        final_capital: index ? 9900 : 10300, net_profit: index ? -100 : 300, total_return_percent: index ? -1 : 3,
        contribution_percent: index ? -0.5 : 1.5, total_trades: 1, win_rate: index ? 0 : 100, max_drawdown_percent: 1,
      })) },
    },
  } }));
  await page.goto("/");
  await page.getByRole("button", { name: /Войти через Keycloak/ }).click();
  await page.getByLabel(/Username or email|Имя пользователя/).fill(process.env.E2E_USERNAME ?? "viewer");
  await page.getByLabel(/Password|Пароль/).fill(process.env.E2E_PASSWORD ?? "CHANGE_ME");
  await page.getByRole("button", { name: /Sign In|Войти/ }).click();
  await expect(page.getByRole("button", { name: "Выйти" })).toBeVisible();
  await page.goto("/portfolios");
  await page.getByLabel("Капитал портфеля").fill("20000");
  await page.getByRole("button", { name: "Прогнать датасет" }).click();
  await expect(page.getByRole("heading", { name: "Портфель «Тестовый портфель» · вклад активов" })).toBeVisible();
  await expect(page.getByRole("img", { name: "Кривая капитала" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "1.50", exact: true })).toBeVisible();
  await expect(page.getByRole("cell", { name: "-0.50", exact: true })).toBeVisible();
  await expect(page.getByRole("cell", { name: "AAA", exact: true })).toHaveCount(2);
  await expect(page.getByRole("cell", { name: "BBB", exact: true })).toHaveCount(2);
  await page.getByLabel("Live-режим").click();
  await page.getByRole("option", { name: "OKX Production" }).click();
  await page.getByLabel("Live-капитал, USDT").fill("140");
  page.once("dialog", async dialog => {
    expect(dialog.message()).toContain("140 USDT");
    await dialog.accept();
  });
  await page.getByRole("button", { name: "Добавить в live" }).click();
  await expect(page.getByText("Портфель добавлен в live (PRODUCTION): AAA, BBB.")).toBeVisible();
});
