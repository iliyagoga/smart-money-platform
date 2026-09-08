import { expect, test } from "@playwright/test";

test.skip(process.env.E2E_REAL_BACKTEST !== "1", "Requires the complete local Docker stack and OKX access");

test("admin loads real candles and sees a completed backtest report", async ({ page }) => {
  test.setTimeout(10 * 60_000);
  const browserErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") browserErrors.push(message.text());
  });
  page.on("pageerror", (error) => browserErrors.push(error.message));

  await page.goto("/");
  await page.getByRole("button", { name: /Войти через Keycloak/ }).click();
  await page.getByLabel(/Username or email|Имя пользователя/).fill("admin");
  await page.getByLabel(/Password|Пароль/).fill(process.env.E2E_PASSWORD ?? "CHANGE_ME");
  await page.getByRole("button", { name: /Sign In|Войти/ }).click();
  await page.goto("/backtest");

  await page.getByLabel("Бэктест: начало").fill("2025-08-08");
  await page.getByLabel("Бэктест: конец").fill("2025-08-14");
  await page.waitForTimeout(2_000);
  const loadButton = page.getByRole("button", { name: "Загрузить все свечи за период" });
  if (await page.getByText(/COMPLETED · сохранено/).count() === 0 && await loadButton.isEnabled()) await loadButton.click();
  await expect(page.getByText(/COMPLETED · сохранено/)).toBeVisible({ timeout: 180_000 });

  await page.getByRole("button", { name: "Запустить бэктест" }).click();
  await expect(page.getByText("Кривая капитала")).toBeVisible({ timeout: 180_000 });
  await expect(page.getByText("Журнал сделок")).toBeVisible();
  await expect(page.getByText(/Бэктест завершился с ошибкой/)).toHaveCount(0);
  expect(browserErrors).toEqual([]);
});
