import { useNavigate } from "react-router-dom";
import ThemeToggle from "../components/ThemeToggle";
import { useAuthStore } from "../stores/authStore";

export default function ChatPage() {
  const navigate = useNavigate();
  const user = useAuthStore((state) => state.user);
  const logout = useAuthStore((state) => state.logout);

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  return (
    <div className="min-h-screen bg-gray-50 text-gray-900 dark:bg-gray-950 dark:text-gray-100">
      <header className="flex items-center justify-between border-b border-gray-200 px-6 py-4 dark:border-gray-800">
        <h1 className="text-lg font-semibold">Chat</h1>
        <div className="flex items-center gap-3">
          <ThemeToggle />
          <button
            type="button"
            onClick={handleLogout}
            className="rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-700 transition-colors hover:bg-gray-100 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800"
          >
            Log out
          </button>
        </div>
      </header>
      <main className="flex min-h-[calc(100vh-65px)] items-center justify-center px-4">
        <p className="text-center text-gray-500 dark:text-gray-400">
          The chat UI arrives in Step 7.
          <br />
          You are signed in as <strong>{user?.username ?? "…"}</strong>.
        </p>
      </main>
    </div>
  );
}
