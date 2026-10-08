import { expect, test } from "@playwright/test";

test("a developer text turn shows the tutor reply", async ({ page }) => {
  await page.goto("http://127.0.0.1:8875/?dev=1");
  await page.getByRole("button", { name: "Sam" }).click();
  await page.getByLabel("dev text").fill("Tell me about sharks");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText("What should we try next?")).toBeVisible();
});

test("the right parent password opens Today", async ({ page }) => {
  await page.goto("http://127.0.0.1:8876/");
  await page.getByLabel("parent password").fill("parent-secret");
  await page.getByRole("button", { name: "Unlock" }).click();
  await expect(page.getByRole("heading", { name: "Today" })).toBeVisible();
  await page.getByRole("button", { name: "Library" }).click();
  await expect(page.getByRole("heading", { name: "Library" })).toBeVisible();
});

test("returning from the parent screen locks again", async ({ page }) => {
  await page.goto("http://127.0.0.1:8876/");
  await page.getByLabel("parent password").fill("parent-secret");
  await page.getByRole("button", { name: "Unlock" }).click();
  await page.getByRole("button", { name: "Session", exact: true }).click();
  await page.getByRole("button", { name: "Lock" }).click();
  await expect(page.getByLabel("parent password")).toBeVisible();
});

test("five bad parent passwords lock the console", async ({ page }) => {
  await page.goto("http://127.0.0.1:8876/");
  for (let attempt = 0; attempt < 4; attempt += 1) {
    await page.getByLabel("parent password").fill("nope");
    const response = page.waitForResponse((item) => item.url().includes("/api/login"));
    await page.getByRole("button", { name: "Unlock" }).click();
    expect((await response).status()).toBe(401);
    await expect(page.getByRole("alert")).toHaveText("invalid password");
  }
  await page.getByLabel("parent password").fill("nope");
  const fifth = page.waitForResponse((item) => item.url().includes("/api/login"));
  await page.getByRole("button", { name: "Unlock" }).click();
  expect((await fifth).status()).toBe(401);
  await expect(page.getByRole("alert")).toHaveText("locked");
  await page.getByLabel("parent password").fill("parent-secret");
  const blocked = page.waitForResponse((item) => item.url().includes("/api/login"));
  await page.getByRole("button", { name: "Unlock" }).click();
  expect((await blocked).status()).toBe(401);
  await expect(page.getByRole("alert")).toHaveText("locked");
});
