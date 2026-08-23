# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: auth-navigation.spec.ts >> user can add an asset and run an isolated backtest
- Location: e2e/auth-navigation.spec.ts:27:5

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: getByText('SOL-USDT-SWAP')
Expected: visible
Error: strict mode violation: getByText('SOL-USDT-SWAP') resolved to 2 elements:
    1) <span class="MuiChip-label mui-14vsv3w">SOL-USDT-SWAP</span> aka locator('div').filter({ hasText: /^SOL-USDT-SWAP$/ })
    2) <p class="MuiTypography-root MuiTypography-body2 mui-14w339s">Укажите биржевой символ, например SOL-USDT-SWAP и…</p> aka getByText('Укажите биржевой символ, например SOL-USDT-SWAP или ETH-USDT.')

Call log:
  - Expect "toBeVisible" with timeout 5000ms
  - waiting for getByText('SOL-USDT-SWAP')

```

# Page snapshot

```yaml
- generic [ref=f5e1]:
  - alert [ref=f5e2]
  - main [ref=f5e3]:
    - generic [ref=f5e5]:
      - link [ref=f5e6] [cursor=pointer]:
        - /url: /
        - generic [ref=f5e7]: SM
        - paragraph [ref=f5e9]: Smart Money
      - navigation [ref=f5e10]:
        - link [ref=f5e11] [cursor=pointer]:
          - /url: /
          - text: Обзор
        - link [ref=f5e12] [cursor=pointer]:
          - /url: /market
          - text: Рынок
        - link [ref=f5e13] [cursor=pointer]:
          - /url: /scenarios
          - text: Сценарии
        - link [ref=f5e14] [cursor=pointer]:
          - /url: /trades
          - text: Сделки
        - link [ref=f5e15] [cursor=pointer]:
          - /url: /learning
          - text: Обучение
        - link [ref=f5e16] [cursor=pointer]:
          - /url: /backtest
          - text: Бэктест
      - generic [ref=f5e17]:
        - generic [ref=f5e18]: Live
        - generic [ref=f5e21]: viewer
        - button [ref=f5e22] [cursor=pointer]:
          - generic [ref=f5e23]: ☾
        - button [ref=f5e24] [cursor=pointer]: Выйти
    - generic [ref=f5e26]:
      - paragraph [ref=f5e27]: SMART MONEY
      - heading [level=3] [ref=f5e28]: Бэктест
      - paragraph [ref=f5e29]: Проверка торговых стратегий на исторических данных без отправки ордеров.
    - generic [ref=f5e30]:
      - heading [level=6] [ref=f5e31]: Активы и исторические данные
      - generic [ref=f5e32]:
        - button [ref=f5e33] [cursor=pointer]:
          - generic [ref=f5e34]: BTC-USDT-SWAP
        - button [ref=f5e37] [cursor=pointer]:
          - generic [ref=f5e38]: ETH-USDT-SWAP
        - button [ref=f5e41] [cursor=pointer]:
          - generic [ref=f5e42]: SOL-USDT-SWAP
        - button [active] [ref=f5e45] [cursor=pointer]: + Добавить актив
      - generic [ref=f5e46]:
        - generic [ref=f5e47]:
          - generic [ref=f5e48]: Таймфрейм
          - generic [ref=f5e49]:
            - combobox [ref=f5e50] [cursor=pointer]: M15
            - textbox: M15
            - group:
              - generic: Таймфрейм
        - generic [ref=f5e51]:
          - generic [ref=f5e52]: Количество свечей
          - generic [ref=f5e53]:
            - spinbutton [ref=f5e54]: "1000"
            - group:
              - generic: Количество свечей
    - generic [ref=f5e55]:
      - generic [ref=f5e57]:
        - heading [level=6] [ref=f5e58]: Параметры стратегии
        - paragraph [ref=f5e59]: Пересечение двух скользящих средних.
        - generic [ref=f5e60]:
          - generic [ref=f5e61]:
            - generic [ref=f5e62]: Направление
            - generic [ref=f5e63]:
              - combobox [ref=f5e64] [cursor=pointer]: Long и Short
              - textbox: BOTH
              - group:
                - generic: Направление
          - generic [ref=f5e65]:
            - generic [ref=f5e66]:
              - generic [ref=f5e67]: Быстрая MA
              - generic [ref=f5e68]:
                - spinbutton [ref=f5e69]: "9"
                - group:
                  - generic: Быстрая MA
            - generic [ref=f5e70]:
              - generic [ref=f5e71]: Медленная MA
              - generic [ref=f5e72]:
                - spinbutton [ref=f5e73]: "21"
                - group:
                  - generic: Медленная MA
          - generic [ref=f5e74]:
            - generic [ref=f5e75]: Начальный капитал
            - generic [ref=f5e76]:
              - spinbutton [ref=f5e77]: "10000"
              - group:
                - generic: Начальный капитал
          - generic [ref=f5e78]:
            - generic [ref=f5e79]: Размер позиции, %
            - generic [ref=f5e80]:
              - spinbutton [ref=f5e81]: "25"
              - group:
                - generic: Размер позиции, %
          - generic [ref=f5e82]:
            - generic [ref=f5e83]:
              - generic [ref=f5e84]: Stop Loss, %
              - generic [ref=f5e85]:
                - spinbutton [ref=f5e86]: "2"
                - group:
                  - generic: Stop Loss, %
            - generic [ref=f5e87]:
              - generic [ref=f5e88]: Take Profit, %
              - generic [ref=f5e89]:
                - spinbutton [ref=f5e90]: "4"
                - group:
                  - generic: Take Profit, %
          - generic [ref=f5e91]:
            - generic [ref=f5e92]:
              - generic [ref=f5e93]: Комиссия, %
              - generic [ref=f5e94]:
                - spinbutton [ref=f5e95]: "0.05"
                - group:
                  - generic: Комиссия, %
            - generic [ref=f5e96]:
              - generic [ref=f5e97]: Проскальзывание, %
              - generic [ref=f5e98]:
                - spinbutton [ref=f5e99]: "0.02"
                - group:
                  - generic: Проскальзывание, %
          - button [ref=f5e100] [cursor=pointer]: Запустить бэктест
      - generic [ref=f5e102]:
        - heading [level=5] [ref=f5e103]: Настройте стратегию и запустите расчёт
        - paragraph [ref=f5e104]: Здесь появятся метрики, кривая капитала и журнал сделок.
  - dialog [ref=f5e107]:
    - heading "Добавить торговый актив" [level=2] [ref=f5e108]
    - generic [ref=f5e109]:
      - paragraph [ref=f5e110]: Укажите биржевой символ, например SOL-USDT-SWAP или ETH-USDT.
      - generic [ref=f5e111]:
        - generic: Символ актива
        - generic [ref=f5e112]:
          - textbox "Символ актива" [ref=f5e113]
          - group:
            - generic: Символ актива
        - paragraph [ref=f5e114]: "Формат: BASE-QUOTE-SWAP"
    - generic [ref=f5e115]:
      - button "Отмена" [ref=f5e116] [cursor=pointer]
      - button "Добавить" [disabled]
```

# Test source

```ts
  1  | import { expect, test } from "@playwright/test";
  2  | import type { Page } from "@playwright/test";
  3  | 
  4  | const username = process.env.E2E_USERNAME ?? "viewer";
  5  | const password = process.env.E2E_PASSWORD ?? "CHANGE_ME";
  6  | 
  7  | async function signIn(page: Page, user = username) {
  8  |   await page.goto("/");
  9  |   await page.getByRole("button", { name: /Войти через Keycloak/ }).click();
  10 |   await page.getByLabel(/Username or email|Имя пользователя/).fill(user);
  11 |   await page.getByLabel(/Password|Пароль/).fill(password);
  12 |   await page.getByRole("button", { name: /Sign In|Войти/ }).click();
  13 | }
  14 | 
  15 | test("user can sign in, switch theme and open every section", async ({ page }) => {
  16 |   await page.goto("/");
  17 |   await page.getByRole("button", { name: "Переключить цветовую тему" }).click();
  18 |   await signIn(page);
  19 |   await expect(page.getByRole("heading", { name: new RegExp(`Добрый день, ${username}`) })).toBeVisible();
  20 | 
  21 |   for (const route of ["market", "scenarios", "trades", "learning", "backtest"]) {
  22 |     await page.goto(`/${route}`);
  23 |     await expect(page).toHaveURL(new RegExp(`/${route}$`));
  24 |   }
  25 | });
  26 | 
  27 | test("user can add an asset and run an isolated backtest", async ({ page }) => {
  28 |   const candles = Array.from({ length: 80 }, (_, index) => {
  29 |     const close = 100 + Math.sin(index / 5) * 10 + index * 0.1;
  30 |     return { timestamp: index * 60_000, open: close - 1, high: close + 2, low: close - 2, close, volume: 10 };
  31 |   });
  32 |   await page.route("**/api/v1/data/market/candles?**", async (route) => {
  33 |     await route.fulfill({
  34 |       status: 200,
  35 |       contentType: "application/json",
  36 |       body: JSON.stringify({ symbol: "SOL-USDT-SWAP", timeframe: "M15", candles }),
  37 |     });
  38 |   });
  39 |   await signIn(page);
  40 |   await page.goto("/backtest");
  41 |   await page.getByRole("button", { name: "Добавить актив" }).click();
  42 |   await page.getByLabel("Символ актива").fill("SOL/USDT_SWAP");
  43 |   await page.getByRole("button", { name: "Добавить", exact: true }).click();
> 44 |   await expect(page.getByText("SOL-USDT-SWAP")).toBeVisible();
     |                                                 ^ Error: expect(locator).toBeVisible() failed
  45 |   await page.getByRole("button", { name: "Запустить бэктест" }).click();
  46 |   await expect(page.getByText("Кривая капитала")).toBeVisible();
  47 |   await expect(page.getByText("Журнал сделок")).toBeVisible();
  48 | });
  49 | 
  50 | test("trader can submit a validated paper order", async ({ page }) => {
  51 |   await page.route("**/api/v1/execution/orders", async (route) => {
  52 |     const body = route.request().postDataJSON() as { side: string; type: string; quantity: number };
  53 |     expect(body).toMatchObject({ side: "BUY", type: "LIMIT", quantity: 0.001 });
  54 |     await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ order_id: "e2e", status: "PENDING" }) });
  55 |   });
  56 |   await signIn(page, "trader");
  57 |   await page.goto("/trades");
  58 |   await page.getByLabel("Тип").click();
  59 |   await page.getByRole("option", { name: "Limit" }).click();
  60 |   await page.getByLabel("Количество").fill("0.001");
  61 |   await page.getByLabel("Цена").fill("50000");
  62 |   await page.getByRole("button", { name: "BUY BTC-USDT-SWAP" }).click();
  63 |   await expect(page.getByText("Ордер успешно отправлен в paper-контур")).toBeVisible();
  64 | });
  65 | 
```