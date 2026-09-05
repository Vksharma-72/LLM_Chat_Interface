import { useState } from "react";
import { useNavigate } from "react-router-dom";
import ChatInput from "../components/ChatInput";
import ConfirmDialog from "../components/ConfirmDialog";
import MessageList from "../components/MessageList";
import SettingsDrawer from "../components/SettingsDrawer";
import Sidebar from "../components/Sidebar";
import ThemeToggle from "../components/ThemeToggle";
import { useChat } from "../hooks/useChat";
import { useAuthStore } from "../stores/authStore";
import { useUiStore } from "../stores/uiStore";

export default function ChatPage() {
  const navigate = useNavigate();
  const user = useAuthStore((state) => state.user);
  const logout = useAuthStore((state) => state.logout);

  const chat = useChat();
  const sidebarOpen = useUiStore((state) => state.sidebarOpen);
  const toggleSidebar = useUiStore((state) => state.toggleSidebar);
  const settingsOpen = useUiStore((state) => state.settingsOpen);
  const setSettingsOpen = useUiStore((state) => state.setSettingsOpen);

  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [confirmClear, setConfirmClear] = useState(false);

  const currentTitle =
    chat.conversations.find((conversation) => conversation.id === chat.currentId)?.title ??
    "New chat";

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  const handleDeleteConfirm = async () => {
    if (confirmDelete) {
      await chat.deleteConversation(confirmDelete);
    }
    setConfirmDelete(null);
  };

  const handleClearConfirm = async () => {
    await chat.clearCurrent();
    setConfirmClear(false);
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
        <header className="flex items-center gap-3 border-b border-gray-200 px-4 py-3 dark:border-gray-800">
          <button
            type="button"
            onClick={toggleSidebar}
            aria-label="Toggle sidebar"
            className="rounded-md border border-gray-300 px-2 py-1 text-sm dark:border-gray-700 md:hidden"
          >
            ☰
          </button>
          <h1 className="min-w-0 flex-1 truncate text-sm font-semibold">{currentTitle}</h1>
          <ThemeToggle />
          <button
            type="button"
            onClick={() => setSettingsOpen(true)}
            aria-label="Open settings"
            className="rounded-md border border-gray-300 px-2 py-1 text-sm dark:border-gray-700"
          >
            ⚙️
          </button>
          <button
            type="button"
            onClick={handleLogout}
            className="rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-700 transition-colors hover:bg-gray-100 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800"
          >
            Log out
          </button>
        </header>

        {chat.error && (
          <div
            role="alert"
            className="mx-4 mt-3 rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300"
          >
            {chat.error}
          </div>
        )}

        <MessageList
          messages={chat.messages}
          isStreaming={chat.isStreaming}
          streamingContent={chat.streamingContent}
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
