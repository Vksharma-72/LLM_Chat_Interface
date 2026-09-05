import { expect, test } from "@playwright/test";

const suffix = Math.random().toString(36).slice(2, 8);
const username = `e2e_${suffix}`;
const password = "password123";

test.describe("auth flow", () => {
  test("register → /chat → logout → login → wrong-password error", async ({ page }) => {
    await page.goto("/register");

    await page.getByLabel("Email").fill(`${username}@example.com`);
    await page.getByLabel("Username").fill(username);
    await page.getByLabel("Password").fill(password);
    await page.getByRole("button", { name: "Create account" }).click();

    // registered and logged in → redirected to the (placeholder) chat page
    await expect(page).toHaveURL(/\/chat$/);
    await expect(page.getByText(username)).toBeVisible();

    // logout → back to /login
    await page.getByRole("button", { name: "Log out" }).click();
    await expect(page).toHaveURL(/\/login$/);

    // wrong password shows the API error banner
    await page.getByLabel("Username or email").fill(username);
    await page.getByLabel("Password").fill("wrong-password");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("alert")).toContainText(/incorrect username/i);

    // correct credentials → /chat again
    await page.getByLabel("Password").fill(password);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page).toHaveURL(/\/chat$/);
  });

  test("unauthenticated users are redirected to /login", async ({ page }) => {
    await page.goto("/chat");
    await expect(page).toHaveURL(/\/login$/);
  });

  test("register validation: short password shows client error", async ({ page }) => {
    await page.goto("/register");
    await page.getByLabel("Email").fill(`${username}_x@example.com`);
    await page.getByLabel("Username").fill(`${username}_x`);
    await page.getByLabel("Password").fill("short");
    await page.getByRole("button", { name: "Create account" }).click();
    await expect(page.getByRole("alert")).toContainText(/at least 8 characters/i);
  });
});
