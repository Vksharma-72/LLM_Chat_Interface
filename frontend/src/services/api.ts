import axios, { AxiosError } from "axios";
import type { AxiosRequestConfig, InternalAxiosRequestConfig } from "axios";
import { useAuthStore } from "../stores/authStore";
import type { RefreshResponse } from "../types/auth";

/** Axios instance for authenticated API calls (base /api, vite-proxied in dev). */
export const api = axios.create({ baseURL: "/api" });

interface RetriableRequestConfig extends InternalAxiosRequestConfig {
  _retry?: boolean;
}

/** A bare axios call (no interceptors) so refreshing cannot recurse into itself. */
export async function requestRefresh(refreshToken: string): Promise<RefreshResponse> {
  const response = await axios.post<RefreshResponse>("/api/auth/refresh", {
    refresh_token: refreshToken,
  });
  return response.data;
}

api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Single-flight: concurrent 401s share one refresh request.
let refreshInFlight: Promise<string | null> | null = null;

export function getErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data as { error?: { message?: string } } | undefined;
    if (data?.error?.message) {
      return data.error.message;
    }
    return error.message;
  }
  return error instanceof Error ? error.message : "Something went wrong";
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as RetriableRequestConfig | undefined;
    if (
      error.response?.status !== 401 ||
      !original ||
      original._retry ||
      original.url?.includes("/auth/refresh")
    ) {
      return Promise.reject(error);
    }
    original._retry = true;

    refreshInFlight ??= useAuthStore
      .getState()
      .refresh()
      .finally(() => {
        refreshInFlight = null;
      });
    const newToken = await refreshInFlight;

    if (!newToken) {
      useAuthStore.getState().clear();
      return Promise.reject(error);
    }
    const retryConfig: AxiosRequestConfig = {
      ...original,
      headers: { ...original.headers, Authorization: `Bearer ${newToken}` },
    };
    return api.request(retryConfig);
  }
);
