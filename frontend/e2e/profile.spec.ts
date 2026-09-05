import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

const runSuffix = Math.random().toString(36).slice(2, 8);

async function registerAndSeed(page: Page) {
  const username = `pf_${runSuffix}_${Math.random().toString(36).slice(2, 6)}`;
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
  return { ...body, username };
}

/** Creates a conversation and exchanges one message via the API (mock LLM). */
async function seedConversation(page: Page, accessToken: string) {
  const created = await page.request.post("/api/conversations", {
    headers: { Authorization: `Bearer ${accessToken}` },
    data: { title: "Export me" },
  });
  const conversation = await created.json();
  await page.request.post("/api/chat/send", {
    headers: { Authorization: `Bearer ${accessToken}` },
    data: { conversation_id: conversation.id, content: "export test" },
  });
  return conversation.id as string;
}

test.describe("profile", () => {
  test("edit username → change password → re-login with new credentials", async ({ page }) => {
    const seeded = await registerAndSeed(page);
    await page.goto("/profile");

    // account info renders
    await expect(page.getByTestId("profile-email")).toHaveText(`${seeded.username}@example.com`);

    // usage chart renders (recharts svg)
    await expect(page.getByTestId("usage-chart").locator("svg")).toBeVisible();

    // edit username
    await page.getByLabel("Username", { exact: true }).fill(`${seeded.username}_renamed`);
    await page.getByRole("button", { name: "Save" }).click();
    await expect(page.getByText("Username updated")).toBeVisible();

    // change password
    await page.getByLabel("Current password").fill("password123");
    await page.getByLabel("New password").fill("newpassword1");
    await page.getByRole("button", { name: "Update password" }).click();
    await expect(page.getByText("Password updated")).toBeVisible();

    // logout → re-login: old password rejected, new one works
    await page.getByRole("button", { name: "Log out" }).click();
    await expect(page).toHaveURL(/\/login$/);

    await page.getByLabel("Username or email").fill(`${seeded.username}_renamed`);
    await page.getByLabel("Password").fill("password123");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("alert")).toContainText(/incorrect/i);

    await page.getByLabel("Password").fill("newpassword1");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page).toHaveURL(/\/chat$/);
  });

  test("export downloads .md and .json files", async ({ page }) => {
    const seeded = await registerAndSeed(page);
    const conversationId = await seedConversation(page, seeded.access_token);
    await page.goto("/chat");

    // open the conversation so the export action becomes available
    await page
      .getByTestId("conversation-item")
      .filter({ hasText: "Export me" })
      .first()
      .click();
    await expect(page.getByText("export test")).toBeVisible();

    await page.getByRole("button", { name: "Export conversation" }).click();
    void conversationId;

    await page.getByRole("menuitem", { name: "Markdown (.md)" }).click();
    const mdDownload = await page.waitForEvent("download");
    expect(mdDownload.suggestedFilename()).toMatch(/\.md$/);

    await page.getByRole("button", { name: "Export conversation" }).click();
    await page.getByRole("menuitem", { name: "JSON (.json)" }).click();
    const jsonDownload = await page.waitForEvent("download");
    expect(jsonDownload.suggestedFilename()).toMatch(/\.json$/);

    await expect(page.getByText("Conversation exported").first()).toBeVisible();
  });

  test("responsive 375px: sidebar collapses into a drawer", async ({ page }) => {
    await registerAndSeed(page);
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto("/chat");

    const sidebar = page.getByRole("navigation", { name: "Conversations" });
    const closedBox = await sidebar.boundingBox();
    expect(closedBox?.x ?? 0).toBeLessThan(0); // slid off-screen

    await page.getByRole("button", { name: "Toggle sidebar" }).click();
    await expect(page.getByLabel("Search conversations")).toBeVisible();
    // the slide-in is a CSS transition — poll until it settles at x=0
    await expect
      .poll(async () => (await sidebar.boundingBox())?.x ?? 999, { timeout: 3000 })
      .toBe(0);
  });
});
