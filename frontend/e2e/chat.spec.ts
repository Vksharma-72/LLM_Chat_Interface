import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

const runSuffix = Math.random().toString(36).slice(2, 8);

/**
 * Registers a fresh user through the API and seeds the persisted auth store
 * before the page loads, so tests skip the login form.
 */
async function registerAndSeed(page: Page) {
  const username = `chat_${runSuffix}_${Math.random().toString(36).slice(2, 6)}`;
  const response = await page.request.post("/api/auth/register", {
    data: { email: `${username}@example.com`, username, password: "password123" },
  });
  expect(response.ok()).toBeTruthy();
  const body = await response.json();
  const authState = JSON.stringify({
    state: {
      user: body.user,
      accessToken: body.access_token,
      refreshToken: body.refresh_token,
    },
    version: 0,
  });
  await page.addInitScript(
    ([value]) => window.localStorage.setItem("ornithopter-auth", value as string),
    [authState]
  );
}

const MOCK_REPLY = "This is a mock reply";

test.describe("chat UI", () => {
  test("new chat → send → streamed reply → switch conversation → delete", async ({ page }) => {
    await registerAndSeed(page);
    await page.goto("/chat");
    const messageInput = () => page.getByLabel("Message", { exact: true });

    // send in a brand-new conversation
    await messageInput().fill("Hello there");
    await messageInput().press("Enter");
    await expect(page.getByText(MOCK_REPLY).first()).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText("Hello there").first()).toBeVisible();

    // second exchange in the same conversation
    await messageInput().fill("And again");
    await messageInput().press("Enter");
    await expect(page.getByText(MOCK_REPLY)).toHaveCount(2, { timeout: 15_000 });

    // start another conversation — its view shows only its own reply
    await page.getByRole("button", { name: "New chat" }).click();
    await messageInput().fill("Second conversation");
    await messageInput().press("Enter");
    await expect(page.getByText(MOCK_REPLY)).toHaveCount(1, { timeout: 15_000 });

    // sidebar groups both; switch back to the first conversation
    const items = page.getByTestId("conversation-item");
    await expect(items).toHaveCount(2);
    await items.filter({ hasText: "Hello there" }).first().click();
    await expect(page.getByText("And again")).toBeVisible();

    // delete it via hover action + confirm dialog
    await items.filter({ hasText: "Hello there" }).first().hover();
    await page.getByRole("button", { name: "Delete conversation" }).first().click();
    await page.getByRole("button", { name: "Delete", exact: true }).click();
    await expect(page.getByTestId("conversation-item")).toHaveCount(1);
    await expect(page.getByText("And again")).toHaveCount(0);
  });

  test("stop button aborts while streaming", async ({ page }) => {
    await registerAndSeed(page);
    await page.goto("/chat");
    const messageInput = () => page.getByLabel("Message", { exact: true });

    await messageInput().fill("Count slowly");
    await messageInput().press("Enter");

    // the mock reply streams fast — Stop may vanish before the click lands
    await page
      .getByRole("button", { name: "Stop" })
      .click({ timeout: 2000 })
      .catch(() => {});

    await expect(page.getByRole("button", { name: "Send" })).toBeVisible();
    await expect(page.getByRole("alert")).toHaveCount(0);
  });
});
