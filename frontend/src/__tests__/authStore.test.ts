import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, requestRefresh } from "../services/api";
import { useAuthStore } from "../stores/authStore";
import type { AuthResponse, User } from "../types/auth";

vi.mock("../services/api", () => ({
  api: { post: vi.fn(), get: vi.fn() },
  requestRefresh: vi.fn(),
}));

const mockedApi = vi.mocked(api, true);
const mockedRequestRefresh = vi.mocked(requestRefresh);

const user: User = {
  id: "u-1",
  email: "user@example.com",
  username: "user",
  is_admin: true,
  created_at: "2026-09-06T00:00:00Z",
};

function authResponse(): AuthResponse {
  return {
    access_token: "access-1",
    refresh_token: "refresh-1",
    token_type: "bearer",
    user,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  useAuthStore.getState().clear();
});

describe("authStore", () => {
  it("login stores user and tokens", async () => {
    mockedApi.post.mockResolvedValueOnce({ data: authResponse() });

    const result = await useAuthStore.getState().login("user", "password123");

    expect(result).toEqual(user);
    expect(mockedApi.post).toHaveBeenCalledWith("/auth/login", {
      username_or_email: "user",
      password: "password123",
    });
    const state = useAuthStore.getState();
    expect(state.user).toEqual(user);
    expect(state.accessToken).toBe("access-1");
    expect(state.refreshToken).toBe("refresh-1");
  });

  it("register stores user and tokens", async () => {
    mockedApi.post.mockResolvedValueOnce({ data: authResponse() });

    await useAuthStore.getState().register("user@example.com", "user", "password123");

    expect(mockedApi.post).toHaveBeenCalledWith("/auth/register", {
      email: "user@example.com",
      username: "user",
      password: "password123",
    });
    expect(useAuthStore.getState().accessToken).toBe("access-1");
  });

  it("logout revokes the refresh token and clears state", async () => {
    mockedApi.post.mockResolvedValueOnce({ data: undefined });
    useAuthStore.setState({ user, accessToken: "access-1", refreshToken: "refresh-1" });

    await useAuthStore.getState().logout();

    expect(mockedApi.post).toHaveBeenCalledWith("/auth/logout", { refresh_token: "refresh-1" });
    expect(useAuthStore.getState().user).toBeNull();
    expect(useAuthStore.getState().accessToken).toBeNull();
  });

  it("logout clears state even when the server call fails", async () => {
    mockedApi.post.mockRejectedValueOnce(new Error("network down"));
    useAuthStore.setState({ user, accessToken: "access-1", refreshToken: "refresh-1" });

    await useAuthStore.getState().logout();

    expect(useAuthStore.getState().accessToken).toBeNull();
  });

  it("refresh rotates tokens and returns the new access token", async () => {
    useAuthStore.setState({ user, accessToken: "expired", refreshToken: "refresh-1" });
    mockedRequestRefresh.mockResolvedValueOnce({
      access_token: "new-access",
      refresh_token: "new-refresh",
      token_type: "bearer",
    });

    const token = await useAuthStore.getState().refresh();

    expect(token).toBe("new-access");
    expect(useAuthStore.getState().accessToken).toBe("new-access");
    expect(useAuthStore.getState().refreshToken).toBe("new-refresh");
  });

  it("refresh clears the store and returns null on failure", async () => {
    useAuthStore.setState({ user, accessToken: "expired", refreshToken: "refresh-1" });
    mockedRequestRefresh.mockRejectedValueOnce(new Error("invalid token"));

    const token = await useAuthStore.getState().refresh();

    expect(token).toBeNull();
    expect(useAuthStore.getState().accessToken).toBeNull();
    expect(useAuthStore.getState().refreshToken).toBeNull();
    expect(useAuthStore.getState().user).toBeNull();
  });

  it("refresh returns null when there is no refresh token", async () => {
    expect(await useAuthStore.getState().refresh()).toBeNull();
    expect(mockedRequestRefresh).not.toHaveBeenCalled();
  });

  it("fetchMe updates the stored user", async () => {
    mockedApi.get.mockResolvedValueOnce({ data: user });

    const result = await useAuthStore.getState().fetchMe();

    expect(result).toEqual(user);
    expect(useAuthStore.getState().user).toEqual(user);
  });
});
