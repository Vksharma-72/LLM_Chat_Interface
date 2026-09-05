import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { format } from "date-fns";
import ThemeToggle from "../components/ThemeToggle";
import { useToast } from "../components/Toast";
import { api, getErrorMessage } from "../services/api";
import { useAuthStore } from "../stores/authStore";
import type { UsageDay } from "../types/usage";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export default function ProfilePage() {
  const navigate = useNavigate();
  const user = useAuthStore((state) => state.user);
  const setUser = useAuthStore((state) => state.setUser);
  const logout = useAuthStore((state) => state.logout);
  const { push } = useToast();

  const [username, setUsername] = useState(user?.username ?? "");
  const [usernameBusy, setUsernameBusy] = useState(false);
  const [usernameError, setUsernameError] = useState<string | null>(null);

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [passwordBusy, setPasswordBusy] = useState(false);
  const [passwordError, setPasswordError] = useState<string | null>(null);

  const [usageDays, setUsageDays] = useState<UsageDay[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .get<{ days: UsageDay[] }>("/users/usage")
      .then((response) => {
        if (!cancelled) {
          setUsageDays(response.data.days);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setUsageDays([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!user) {
    return null;
  }

  const handleUsernameSave = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setUsernameError(null);
    const trimmed = username.trim();
    if (!trimmed || trimmed === user.username) {
      return;
    }
    setUsernameBusy(true);
    try {
      const response = await api.put<typeof user>("/users/me", { username: trimmed });
      setUser(response.data);
      push("Username updated");
    } catch (err) {
      setUsernameError(getErrorMessage(err));
    } finally {
      setUsernameBusy(false);
    }
  };

  const handlePasswordChange = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setPasswordError(null);
    if (newPassword.length < 8) {
      setPasswordError("New password must be at least 8 characters");
      return;
    }
    setPasswordBusy(true);
    try {
      await api.put("/users/me/password", {
        current_password: currentPassword,
        new_password: newPassword,
      });
      setCurrentPassword("");
      setNewPassword("");
      push("Password updated");
    } catch (err) {
      setPasswordError(getErrorMessage(err));
    } finally {
      setPasswordBusy(false);
    }
  };

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  const cardClasses =
    "rounded-lg border border-gray-200 bg-white p-6 shadow-sm dark:border-gray-800 dark:bg-gray-900";
  const inputClasses =
    "mt-1 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-gray-900 focus:border-indigo-500 focus:outline-none dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100";
  const labelClasses = "block text-sm font-medium text-gray-700 dark:text-gray-300";

  return (
    <div className="min-h-screen bg-gray-50 text-gray-900 dark:bg-gray-950 dark:text-gray-100">
      <header className="flex items-center justify-between border-b border-gray-200 px-6 py-4 dark:border-gray-800">
        <div className="flex items-center gap-4">
          <Link
            to="/chat"
            className="text-sm text-indigo-600 hover:underline dark:text-indigo-400"
          >
            ← Back to chat
          </Link>
          <h1 className="text-lg font-semibold">Profile</h1>
        </div>
        <ThemeToggle />
      </header>

      <main className="mx-auto max-w-3xl space-y-6 px-4 py-6">
        <section className={cardClasses} aria-label="Account information">
          <h2 className="mb-4 text-base font-semibold">Account</h2>
          <dl className="grid grid-cols-1 gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-gray-500 dark:text-gray-400">Email</dt>
              <dd data-testid="profile-email">{user.email}</dd>
            </div>
            <div>
              <dt className="text-gray-500 dark:text-gray-400">Member since</dt>
              <dd>{format(new Date(user.created_at), "MMM d, yyyy")}</dd>
            </div>
            <div>
              <dt className="text-gray-500 dark:text-gray-400">Role</dt>
              <dd>{user.is_admin ? "Admin" : "Member"}</dd>
            </div>
          </dl>
        </section>

        <section className={cardClasses} aria-label="Usage, last 30 days">
          <h2 className="mb-4 text-base font-semibold">Usage — last 30 days</h2>
          {usageDays === null ? (
            <div className="h-60 animate-pulse rounded-md bg-gray-100 dark:bg-gray-800" />
          ) : (
            <div className="h-60 w-full" data-testid="usage-chart">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={usageDays}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#8884" />
                  <XAxis
                    dataKey="date"
                    tickFormatter={(value: string) => value.slice(5)}
                    minTickGap={24}
                    tick={{ fontSize: 11 }}
                  />
                  <YAxis allowDecimals={false} tick={{ fontSize: 11 }} width={40} />
                  <Tooltip />
                  <Bar dataKey="tokens" fill="#6366f1" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </section>

        <section className={cardClasses} aria-label="Edit username">
          <h2 className="mb-4 text-base font-semibold">Username</h2>
          {usernameError && (
            <div role="alert" className="mb-3 rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300">
              {usernameError}
            </div>
          )}
          <form onSubmit={handleUsernameSave} className="flex items-end gap-3">
            <div className="flex-1">
              <label htmlFor="profile-username" className={labelClasses}>
                Username
              </label>
              <input
                id="profile-username"
                type="text"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                className={inputClasses}
              />
            </div>
            <button
              type="submit"
              disabled={usernameBusy || username.trim() === user.username}
              className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-indigo-500"
            >
              {usernameBusy ? "Saving…" : "Save"}
            </button>
          </form>
        </section>

        <section className={cardClasses} aria-label="Change password">
          <h2 className="mb-4 text-base font-semibold">Change password</h2>
          {passwordError && (
            <div role="alert" className="mb-3 rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300">
              {passwordError}
            </div>
          )}
          <form onSubmit={handlePasswordChange} className="space-y-4">
            <div>
              <label htmlFor="current-password" className={labelClasses}>
                Current password
              </label>
              <input
                id="current-password"
                type="password"
                autoComplete="current-password"
                value={currentPassword}
                onChange={(event) => setCurrentPassword(event.target.value)}
                className={inputClasses}
              />
            </div>
            <div>
              <label htmlFor="new-password" className={labelClasses}>
                New password
              </label>
              <input
                id="new-password"
                type="password"
                autoComplete="new-password"
                value={newPassword}
                onChange={(event) => setNewPassword(event.target.value)}
                className={inputClasses}
              />
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                At least 8 characters.
              </p>
            </div>
            <button
              type="submit"
              disabled={passwordBusy}
              className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-indigo-500"
            >
              {passwordBusy ? "Updating…" : "Update password"}
            </button>
          </form>
        </section>

        <button
          type="button"
          onClick={handleLogout}
          className="w-full rounded-md border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800"
        >
          Log out
        </button>
      </main>
    </div>
  );
}
