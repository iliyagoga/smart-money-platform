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

  for (const route of ["market", "scenarios", "trades", "learning", "backtest"]) {
    await page.goto(`/${route}`);
    await expect(page).toHaveURL(new RegExp(`/${route}$`));
  }
});

test("user can add an asset and run an isolated backtest", async ({ page }) => {
  const candles = Array.from({ length: 80 }, (_, index) => {
    const close = 100 + Math.sin(index / 5) * 10 + index * 0.1;
    return { timestamp: index * 60_000, open: close - 1, high: close + 2, low: close - 2, close, volume: 10 };
  });
  await page.route("**/api/v1/data/market/candles?**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ symbol: "SOL-USDT-SWAP", timeframe: "M15", candles }),
    });
  });
  await signIn(page);
  await page.goto("/backtest");
  await page.getByRole("button", { name: "Добавить актив" }).click();
  await page.getByLabel("Символ актива").fill("SOL/USDT_SWAP");
  await page.getByRole("button", { name: "Добавить", exact: true }).click();
  await expect(page.getByText("SOL-USDT-SWAP")).toBeVisible();
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
  await page.getByLabel("Тип").click();
  await page.getByRole("option", { name: "Limit" }).click();
  await page.getByLabel("Количество").fill("0.001");
  await page.getByLabel("Цена").fill("50000");
  await page.getByRole("button", { name: "BUY BTC-USDT-SWAP" }).click();
  await expect(page.getByText("Ордер успешно отправлен в paper-контур")).toBeVisible();
});
