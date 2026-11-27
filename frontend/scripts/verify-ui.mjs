/**
 * Проверка интерфейса в реальном браузере: обходит все маршруты, входит через
 * форму, считает выгоду и складывает скриншоты в docs/screens/.
 *
 * Запуск (при поднятых backend и vite):
 *   node scripts/verify-ui.mjs
 */

import { mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { chromium } from "playwright";

const BASE = process.env.UI_BASE ?? "http://127.0.0.1:5173";
const here = dirname(fileURLToPath(import.meta.url));
const OUT = join(here, "..", "..", "docs", "screens");

const consoleErrors = [];
const failedRequests = [];
const steps = [];

function note(label, detail = "") {
  steps.push(`${label}${detail ? ` — ${detail}` : ""}`);
  console.log(`  ${label}${detail ? ` — ${detail}` : ""}`);
}

async function shot(page, name) {
  await page.waitForTimeout(350);
  await page.screenshot({ path: join(OUT, `${name}.png`), fullPage: false });
}

await mkdir(OUT, { recursive: true });

const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  locale: "ru-RU",
  timezoneId: "Europe/Moscow",
});
const page = await context.newPage();

page.on("console", (message) => {
  if (message.type() === "error") consoleErrors.push(message.text());
});
page.on("requestfailed", (request) => {
  failedRequests.push(`${request.method()} ${request.url()} — ${request.failure()?.errorText ?? ""}`);
});
page.on("response", async (response) => {
  if (response.status() >= 400) {
    const body = await response.text().catch(() => "");
    console.log(`  HTTP ${response.status()} ${response.request().method()} ${response.url()} :: ${body.slice(0, 300)}`);
  }
});

try {
  console.log("== вход ==");
  await page.goto(`${BASE}/login`, { waitUntil: "networkidle" });
  await shot(page, "01-login");
  note("страница входа открыта");

  // Прямой переход на защищённый маршрут без токена — должен перебросить на /login.
  await page.goto(`${BASE}/trades`, { waitUntil: "networkidle" });
  await page.waitForURL("**/login", { timeout: 8_000 }).catch(() => undefined);
  const redirected = new URL(page.url()).pathname;
  note("PrivateRoute при прямом вводе /trades", `→ ${redirected}`);
  if (redirected !== "/login") throw new Error("PrivateRoute не сработал");

  await page.getByLabel("Логин").fill("demo");
  await page.getByLabel("Пароль").fill("demo12345");
  await page.getByRole("button", { name: "Войти" }).click();
  await page.waitForURL("**/trades", { timeout: 10_000 });
  await page.getByText("История сделок").first().waitFor();
  await shot(page, "02-trades");
  note("вход выполнен, журнал загружен");

  const statText = await page.locator("table tbody tr").count();
  note("строк в журнале", String(statText));

  console.log("== обзор рынка ==");
  await page.goto(`${BASE}/`, { waitUntil: "networkidle" });
  await page.getByText("Что выгодно прямо сейчас").waitFor();
  await shot(page, "03-dashboard");
  note("лента лотов отрисована");

  console.log("== каталог ==");
  await page.goto(`${BASE}/catalog`, { waitUntil: "networkidle" });
  await page.getByText("Предметы аукциона").waitFor();
  await shot(page, "04-catalog");
  note("каталог отрисован");

  console.log("== карточка предмета ==");
  await page.locator("a[href^='/catalog/']").first().click();
  await page.waitForURL(/\/catalog\/.+/, { timeout: 10_000 });
  await page.getByText("Активные лоты").waitFor();
  await shot(page, "05-item");
  const itemPath = new URL(page.url()).pathname;
  note("динамический маршрут", itemPath);

  console.log("== калькулятор ==");
  await page.getByRole("button", { name: "Посчитать выгоду" }).click();
  await page.waitForURL("**/calculator", { timeout: 10_000 });
  await page.getByLabel(/Цена покупки/).fill("18400");
  await page.getByLabel(/Цена продажи/).fill("27900");
  await page.getByLabel("Количество").fill("3");
  await page.getByText("Чистая выгода").waitFor({ timeout: 10_000 });
  const profitText = await page.locator("text=Чистая выгода").first().locator("..").innerText();
  await shot(page, "06-calculator");
  note("расчёт с сервера получен", profitText.replace(/\s+/g, " ").slice(0, 80));

  console.log("== сохранение сделки ==");
  await page.getByRole("button", { name: "Сохранить в журнал" }).click();
  await page.waitForURL(/\/trades\/\d+/, { timeout: 10_000 });
  await page.getByText("Расчёт").first().waitFor();
  await shot(page, "07-trade-detail");
  note("сделка сохранена", new URL(page.url()).pathname);

  console.log("== каталог: переход по прямой ссылке ==");
  await page.goto(`${BASE}${itemPath}`, { waitUntil: "networkidle" });
  note("карточка по прямому URL", itemPath);

  console.log("== 404 ==");
  await page.goto(`${BASE}/no-such-page`, { waitUntil: "networkidle" });
  await page.getByText("Такой страницы нет").waitFor();
  await shot(page, "08-404");
  note("страница 404 отрисована");

  console.log("== выход ==");
  await page.getByRole("button", { name: "Выйти" }).click();
  await page.waitForURL("**/login", { timeout: 10_000 });
  note("выход очищает сессию");

  await page.goto(`${BASE}/trades`, { waitUntil: "networkidle" });
  note("после выхода /trades", new URL(page.url()).pathname);
} catch (error) {
  console.error("ПРОВЕРКА УПАЛА:", error.message);
  await page.screenshot({ path: join(OUT, "failure.png") }).catch(() => undefined);
  process.exitCode = 1;
} finally {
  await browser.close();
}

console.log("\n=== итог ===");
if (consoleErrors.length) {
  console.log(`Ошибки в консоли (${consoleErrors.length}):`);
  for (const line of consoleErrors) console.log("  !", line);
} else {
  console.log("Ошибок в консоли браузера нет");
}

if (failedRequests.length) {
  console.log(`Упавшие запросы (${failedRequests.length}):`);
  for (const line of failedRequests) console.log("  !", line);
} else {
  console.log("Все сетевые запросы успешны");
}
