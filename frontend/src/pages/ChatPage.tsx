import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import ChatInput from "../components/ChatInput";
import ConfirmDialog from "../components/ConfirmDialog";
import MessageList from "../components/MessageList";
import SettingsDrawer from "../components/SettingsDrawer";
import Sidebar from "../components/Sidebar";
import ThemeToggle from "../components/ThemeToggle";
import { useToast } from "../components/Toast";
import { useChat } from "../hooks/useChat";
import { friendlyError } from "../lib/friendlyError";
import { api, getErrorMessage } from "../services/api";
import { useAuthStore } from "../stores/authStore";
import { useUiStore } from "../stores/uiStore";

export default function ChatPage() {
  const navigate = useNavigate();
  const user = useAuthStore((state) => state.user);
  const logout = useAuthStore((state) => state.logout);

  const chat = useChat();
  const sidebarOpen = useUiStore((state) => state.sidebarOpen);
  const toggleSidebar = useUiStore((state) => state.toggleSidebar);
  const setSidebarOpen = useUiStore((state) => state.setSidebarOpen);
  const settingsOpen = useUiStore((state) => state.settingsOpen);
  const setSettingsOpen = useUiStore((state) => state.setSettingsOpen);
  const { push } = useToast();

  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [confirmClear, setConfirmClear] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);

  const currentTitle =
    chat.conversations.find((conversation) => conversation.id === chat.currentId)?.title ??
    "New chat";

  // Shortcuts: Ctrl/Cmd+K → search, Ctrl/Cmd+Shift+O → new chat (§8).
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      const mod = event.ctrlKey || event.metaKey;
      if (!mod) {
        return;
      }
      if (event.key.toLowerCase() === "k") {
        event.preventDefault();
        setSidebarOpen(true);
        requestAnimationFrame(() => {
          document.getElementById("conversation-search")?.focus();
        });
      } else if (event.shiftKey && event.key.toLowerCase() === "o") {
        event.preventDefault();
        chat.newConversation();
        push("Started a new chat", "info");
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [chat, setSidebarOpen, push]);

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  const handleDeleteConfirm = async () => {
    if (confirmDelete) {
      await chat.deleteConversation(confirmDelete);
      push("Conversation deleted");
    }
    setConfirmDelete(null);
  };

  const handleClearConfirm = async () => {
    await chat.clearCurrent();
    setConfirmClear(false);
    push("Conversation cleared");
  };

  const handleExport = async (format: "md" | "json") => {
    setExportOpen(false);
    if (!chat.currentId) {
      return;
    }
    try {
      const response = await api.get(`/conversations/${chat.currentId}/export`, {
        params: { format },
        responseType: "blob",
      });
      const disposition = (response.headers["content-disposition"] as string | undefined) ?? "";
      const match = /filename="([^"]+)"/.exec(disposition);
      const filename = match?.[1] ?? `conversation.${format}`;
      const url = URL.createObjectURL(response.data as Blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      push("Conversation exported");
    } catch (err) {
      push(getErrorMessage(err), "error");
    }
  };

  return (
    <div className="flex h-screen overflow-hidden bg-gray-50 text-gray-900 dark:bg-gray-950 dark:text-gray-100">
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-10 bg-black/40 md:hidden"
          onClick={toggleSidebar}
          aria-hidden="true"
        />
      )}
      <aside
        aria-label="Conversation sidebar"
        className={`fixed inset-y-0 left-0 z-20 w-72 shrink-0 border-r border-gray-200 bg-white transition-transform dark:border-gray-800 dark:bg-gray-900 md:static md:translate-x-0 ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <Sidebar onDelete={(id) => setConfirmDelete(id)} />
      </aside>

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-2 px-3 py-3 sm:gap-3 sm:px-4 dark:border-gray-800">
          <button
            type="button"
            onClick={toggleSidebar}
            aria-label="Toggle sidebar"
            className="rounded-md border border-gray-300 px-2 py-1 text-sm dark:border-gray-700 md:hidden"
          >
            ☰
          </button>
          <h1 className="min-w-0 flex-1 truncate text-sm font-semibold">{currentTitle}</h1>

          <div className="relative">
            <button
              type="button"
              onClick={() => setExportOpen((open) => !open)}
              disabled={!chat.currentId}
              aria-label="Export conversation"
              aria-haspopup="menu"
              className="rounded-md border border-gray-300 px-2 py-1 text-sm disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-700"
            >
              ⬇️ <span className="hidden sm:inline">Export</span>
            </button>
            {exportOpen && (
              <div
                role="menu"
                className="absolute right-0 z-30 mt-1 w-44 overflow-hidden rounded-md border border-gray-200 bg-white text-sm shadow-lg dark:border-gray-800 dark:bg-gray-900"
              >
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => void handleExport("md")}
                  className="block w-full px-3 py-2 text-left text-gray-900 hover:bg-gray-100 dark:text-gray-100 dark:hover:bg-gray-800"
                >
                  Markdown (.md)
                </button>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => void handleExport("json")}
                  className="block w-full px-3 py-2 text-left text-gray-900 hover:bg-gray-100 dark:text-gray-100 dark:hover:bg-gray-800"
                >
                  JSON (.json)
                </button>
              </div>
            )}
          </div>

          <Link
            to="/profile"
            aria-label="Open profile"
            className="rounded-md border border-gray-300 px-2 py-1 text-sm dark:border-gray-700"
          >
            👤 <span className="hidden sm:inline">Profile</span>
          </Link>
          <ThemeToggle />
          <button
            type="button"
            onClick={handleLogout}
            className="rounded-md border border-gray-300 px-2 py-1 text-sm text-gray-700 transition-colors hover:bg-gray-100 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800"
          >
            <span aria-hidden="true">⏻</span>
            <span className="sr-only sm:not-sr-only sm:ml-1">Log out</span>
          </button>
        </header>

        {chat.error && (
          <div
            role="alert"
            className="mx-4 mt-3 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200"
          >
            {friendlyError(chat.errorCode, chat.error)}
          </div>
        )}

        <MessageList
          messages={chat.messages}
          isStreaming={chat.isStreaming}
          streamingContent={chat.streamingContent}
          isLoading={chat.isLoadingConversation}
          onRegenerate={chat.regenerate}
        />

        <ChatInput
          disabled={chat.isStreaming}
          isStreaming={chat.isStreaming}
          onSend={chat.send}
          onStop={chat.abort}
        />
      </main>

      <SettingsDrawer
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        onClearConversation={() => setConfirmClear(true)}
        canClear={chat.currentId !== null}
      />

      <ConfirmDialog
        open={confirmDelete !== null}
        title="Delete conversation"
        message="This conversation and all of its messages will be permanently deleted."
        confirmLabel="Delete"
        onConfirm={handleDeleteConfirm}
        onCancel={() => setConfirmDelete(null)}
      />
      <ConfirmDialog
        open={confirmClear}
        title="Clear conversation"
        message="All messages in this conversation will be permanently deleted."
        confirmLabel="Clear"
        onConfirm={handleClearConfirm}
        onCancel={() => setConfirmClear(false)}
      />

      {/* signed-in indicator for E2E + a11y */}
      <span className="sr-only" data-testid="signed-in-user">
        {user?.username}
      </span>
    </div>
  );
}
