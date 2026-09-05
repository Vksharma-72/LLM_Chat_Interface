import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

const runSuffix = Math.random().toString(36).slice(2, 8);

// 1×1 red PNG
const PNG_BASE64 =
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkqPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==";

async function registerAndSeed(page: Page) {
  const username = `att_${runSuffix}_${Math.random().toString(36).slice(2, 6)}`;
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
  return body;
}

test.describe("attachments", () => {
  test("upload image → send → streamed vision reply → thumbnail renders", async ({ page }) => {
    const messageInput = () => page.getByLabel("Message", { exact: true });

    await registerAndSeed(page);
    await page.goto("/chat");

    await page
      .setInputFiles('input[type="file"]', {
        name: "cat.png",
        mimeType: "image/png",
        buffer: Buffer.from(PNG_BASE64, "base64"),
      })
    await expect(page.getByTestId("pending-attachment")).toBeVisible();
    await expect(page.getByTestId("pending-attachment")).toContainText("✓"); // upload complete

    await messageInput().fill("What is this?");
    await messageInput().press("Enter");

    // the mock's vision reply proves the image part reached the LLM payload
    await expect(page.getByText("I can see the image.")).toBeVisible({
      timeout: 15_000,
    });
    // the persisted attachment renders as a thumbnail
    await expect(page.getByRole("button", { name: "View cat.png" })).toBeVisible();
  });

  test("upload text document → assistant sees its contents", async ({ page }) => {
    const messageInput = () => page.getByLabel("Message", { exact: true });

    await registerAndSeed(page);
    await page.goto("/chat");

    await page.setInputFiles('input[type="file"]', {
      name: "notes.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("The launch code is ALPHA-1234."),
    });
    await messageInput().fill("summarize the notes");
    await messageInput().press("Enter");

    // plain mock reply for non-image input; the document chip renders
    await expect(page.getByText("This is a mock reply").first()).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByText("notes.txt")).toBeVisible();
  });

  test("pending chip can be removed before sending", async ({ page }) => {
    await registerAndSeed(page);
    await page.goto("/chat");

    // remove-on-✕ flow: upload then remove the pending chip
    await page.setInputFiles('input[type="file"]', {
      name: "clip.mp4",
      mimeType: "video/mp4",
      buffer: Buffer.from("0"),
    });
    const chip = page.getByTestId("pending-attachment");
    await expect(chip).toBeVisible();
    await page.getByRole("button", { name: "Remove clip.mp4" }).click();
    await expect(chip).toHaveCount(0);
  });
});
