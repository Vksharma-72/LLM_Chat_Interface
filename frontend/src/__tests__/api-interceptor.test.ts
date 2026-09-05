import axios, { AxiosError } from "axios";
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from "axios";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { api } from "../services/api";
import { useAuthStore } from "../stores/authStore";
import type { User } from "../types/auth";

const user: User = {
  id: "u-1",
  email: "user@example.com",
  username: "user",
  is_admin: false,
  created_at: "2026-09-06T00:00:00Z",
};

function authHeaderOf(config: InternalAxiosRequestConfig): string {
  const headers = config.headers as unknown as Record<string, string> | undefined;
  return headers?.["Authorization"] ?? headers?.["authorization"] ?? "";
}

/** Build an axios response; rejects when validateStatus fails, like real adapters. */
function respond(config: InternalAxiosRequestConfig, status: number, data: unknown): AxiosResponse {
  const response: AxiosResponse = {
    data,
    status,
    statusText: String(status),
    headers: {},
    config,
  };
  const validateStatus = config.validateStatus ?? ((s: number) => s >= 200 && s < 300);
  if (!validateStatus(status)) {
    throw new AxiosError(
      `Request failed with status code ${status}`,
      AxiosError.ERR_BAD_REQUEST,
      config,
      undefined,
      response
    );
  }
  return response;
}

/** Fake adapter: /auth/refresh mints new tokens; /protected demands Bearer new-access. */
function makeAdapter(options: {
  refreshCalls: { count: number };
  refreshDelayMs?: number;
  refreshStatus?: number;
  protectedCalls: { count: number };
}): AxiosAdapter {
  return async (config) => {
    const url = config.url ?? "";
    if (url.includes("/auth/refresh")) {
      options.refreshCalls.count += 1;
      if (options.refreshDelayMs) {
        await new Promise((resolve) => setTimeout(resolve, options.refreshDelayMs));
      }
      if ((options.refreshStatus ?? 200) !== 200) {
        return respond(
          config,
          options.refreshStatus ?? 401,
          { error: { code: "invalid_token", message: "Invalid refresh token" } }
        );
      }
      return respond(
        config,
        200,
        { access_token: "new-access", refresh_token: "new-refresh", token_type: "bearer" }
      );
    }
    if (url.includes("/protected")) {
      options.protectedCalls.count += 1;
      if (authHeaderOf(config) === "Bearer new-access") {
        return respond(config, 200, { ok: true });
      }
      return respond(
        config,
        401,
        { error: { code: "unauthorized", message: "Authentication required" } }
      );
    }
    return respond(config, 404, {});
  };
}

describe("api response interceptor: refresh-once-then-retry", () => {
  const refreshCalls = { count: 0 };
  const protectedCalls = { count: 0 };

  const installAdapter = (options: Parameters<typeof makeAdapter>[0]) => {
    const adapter = makeAdapter(options);
    api.defaults.adapter = adapter;
    axios.defaults.adapter = adapter; // used by requestRefresh's bare axios call
  };

  beforeEach(() => {
    refreshCalls.count = 0;
    protectedCalls.count = 0;
    useAuthStore.setState({
      user,
      accessToken: "expired-access",
      refreshToken: "refresh-1",
    });
  });

  afterEach(() => {
    useAuthStore.getState().clear();
  });

  it("retries a 401 once after a successful refresh", async () => {
    installAdapter({ refreshCalls, protectedCalls });

    const response = await api.get("/protected");

    expect(response.status).toBe(200);
    expect(protectedCalls.count).toBe(2); // first attempt 401, retried with new token
    expect(refreshCalls.count).toBe(1);
    expect(useAuthStore.getState().accessToken).toBe("new-access");
    expect(useAuthStore.getState().refreshToken).toBe("new-refresh");
  });

  it("shares a single refresh across concurrent 401s (single-flight)", async () => {
    installAdapter({ refreshCalls, protectedCalls, refreshDelayMs: 20 });

    const [first, second] = await Promise.all([api.get("/protected"), api.get("/protected")]);

    expect(first.status).toBe(200);
    expect(second.status).toBe(200);
    expect(refreshCalls.count).toBe(1);
    expect(protectedCalls.count).toBe(4); // 2 × (401 + retried 200)
  });

  it("clears the store and rejects when the refresh itself fails", async () => {
    installAdapter({ refreshCalls, protectedCalls, refreshStatus: 401 });

    await expect(api.get("/protected")).rejects.toThrow();

    expect(refreshCalls.count).toBe(1);
    expect(useAuthStore.getState().accessToken).toBeNull();
    expect(useAuthStore.getState().refreshToken).toBeNull();
    expect(useAuthStore.getState().user).toBeNull();
  });

  it("does not retry when the original request is not a 401", async () => {
    const adapter: AxiosAdapter = async (config) => respond(config, 500, {});
    api.defaults.adapter = adapter;
    axios.defaults.adapter = adapter;

    await expect(api.get("/protected")).rejects.toThrow();

    expect(useAuthStore.getState().accessToken).toBe("expired-access");
  });
});
