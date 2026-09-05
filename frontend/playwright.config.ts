import { defineConfig, devices } from "@playwright/test";

/**
 * Boots its own stack (§9): mock LLM :8001, backend :3001 (test DB + Redis db 1),
 * Vite dev :5173 — specs run against :5173 which proxies /api to :3001.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  use: {
    baseURL: "http://localhost:5173",
    trace: "on-first-retry",
  },
  webServer: [
    {
      command: "cd .. && uv run python scripts/mock_llm_server.py",
      url: "http://localhost:8001/v1/models",
      reuseExistingServer: true,
      timeout: 30_000,
    },
    {
      command:
        "cd .. && DATABASE_URL=postgresql+asyncpg://llmchat:llmchat@localhost:5432/llmchat_test " +
        "REDIS_URL=redis://localhost:6379/1 " +
        "LLM_API_URL=http://localhost:8001/v1 " +
        "uv run uvicorn --app-dir backend app.main:app --host 127.0.0.1 --port 3001",
      url: "http://localhost:3001/health",
      reuseExistingServer: true,
      timeout: 30_000,
    },
    {
      command: "npm run dev -- --port 5173 --strictPort",
      url: "http://localhost:5173",
      reuseExistingServer: true,
      timeout: 60_000,
    },
  ],
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
