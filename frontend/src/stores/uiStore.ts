import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

export interface ChatSettings {
  model: string;
  temperature: number;
  maxTokens: number;
  systemPrompt: string;
}

export type Theme = "light" | "dark";

interface UiState {
  sidebarOpen: boolean;
  settingsOpen: boolean;
  theme: Theme;
  settings: ChatSettings;
  toggleTheme: () => void;
  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;
  setSettingsOpen: (open: boolean) => void;
  updateSettings: (patch: Partial<ChatSettings>) => void;
}

export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      sidebarOpen: typeof window !== "undefined" ? window.innerWidth >= 768 : true,
      settingsOpen: false,
      theme: "light",
      settings: {
        model: "",
        temperature: 0.7,
        maxTokens: 1024,
        systemPrompt: "",
      },
      toggleTheme: () => set((state) => ({ theme: state.theme === "dark" ? "light" : "dark" })),
      toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
      setSidebarOpen: (open) => set({ sidebarOpen: open }),
      setSettingsOpen: (open) => set({ settingsOpen: open }),
      updateSettings: (patch) => set((state) => ({ settings: { ...state.settings, ...patch } })),
    }),
    {
      name: "ornithopter-ui",
      storage: createJSONStorage(() => localStorage),
    }
  )
);
