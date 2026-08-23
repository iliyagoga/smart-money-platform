import { expect, test } from "@playwright/test";

const username = process.env.E2E_USERNAME ?? "viewer";
const password = process.env.E2E_PASSWORD ?? "CHANGE_ME";

test("user can sign in, switch theme and open every section", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Переключить цветовую тему" }).click();
  await page.getByRole("button", { name: /Войти через Keycloak/ }).click();

  await page.getByLabel(/Username or email|Имя пользователя/).fill(username);
  await page.getByLabel(/Password|Пароль/).fill(password);
  await page.getByRole("button", { name: /Sign In|Войти/ }).click();
  await expect(page.getByRole("heading", { name: new RegExp(`Добрый день, ${username}`) })).toBeVisible();

  for (const route of ["market", "scenarios", "trades", "learning"]) {
    await page.goto(`/${route}`);
    await expect(page).toHaveURL(new RegExp(`/${route}$`));
  }
});
