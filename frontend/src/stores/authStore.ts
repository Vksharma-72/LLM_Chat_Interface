import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import { api, requestRefresh } from "../services/api";
import type { AuthResponse, User } from "../types/auth";

interface AuthState {
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
  login: (usernameOrEmail: string, password: string) => Promise<User>;
  register: (email: string, username: string, password: string) => Promise<User>;
  logout: () => Promise<void>;
  /** Rotate tokens; returns the new access token, or null on failure. */
  refresh: () => Promise<string | null>;
  fetchMe: () => Promise<User | null>;
  clear: () => void;
}

function applyAuth(set: (partial: Partial<AuthState>) => void, data: AuthResponse) {
  set({ user: data.user, accessToken: data.access_token, refreshToken: data.refresh_token });
  return data.user;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      accessToken: null,
      refreshToken: null,

      login: async (usernameOrEmail, password) => {
        const response = await api.post<AuthResponse>("/auth/login", {
          username_or_email: usernameOrEmail,
          password,
        });
        return applyAuth(set, response.data);
      },

      register: async (email, username, password) => {
        const response = await api.post<AuthResponse>("/auth/register", {
          email,
          username,
          password,
        });
        return applyAuth(set, response.data);
      },

      logout: async () => {
        const refreshToken = get().refreshToken;
        try {
          if (refreshToken) {
            await api.post("/auth/logout", { refresh_token: refreshToken });
          }
        } catch {
          // best-effort: clear locally even if the server rejects the token
        } finally {
          get().clear();
        }
      },

      refresh: async () => {
        const refreshToken = get().refreshToken;
        if (!refreshToken) {
          return null;
        }
        try {
          const data = await requestRefresh(refreshToken);
          set({ accessToken: data.access_token, refreshToken: data.refresh_token });
          return data.access_token;
        } catch {
          get().clear();
          return null;
        }
      },

      fetchMe: async () => {
        try {
          const response = await api.get<User>("/auth/me");
          set({ user: response.data });
          return response.data;
        } catch {
          return null;
        }
      },

      clear: () => set({ user: null, accessToken: null, refreshToken: null }),
    }),
    {
      name: "ornithopter-auth",
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        user: state.user,
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
      }),
    }
  )
);
