import type { FormEvent, ReactNode } from "react";
import ThemeToggle from "./ThemeToggle";

export const inputClasses =
  "mt-1 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100 dark:focus:border-indigo-400 dark:focus:ring-indigo-400";

export const labelClasses = "block text-sm font-medium text-gray-700 dark:text-gray-300";

interface AuthFormProps {
  title: string;
  error: string | null;
  submitting: boolean;
  submitLabel: string;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  children: ReactNode;
  footer: ReactNode;
}

export default function AuthForm({
  title,
  error,
  submitting,
  submitLabel,
  onSubmit,
  children,
  footer,
}: AuthFormProps) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4 dark:bg-gray-950">
      <div className="w-full max-w-md">
        <div className="mb-4 flex justify-end">
          <ThemeToggle />
        </div>
        <div className="rounded-lg border border-gray-200 bg-white p-8 shadow-sm dark:border-gray-800 dark:bg-gray-900">
          <h1 className="mb-6 text-2xl font-bold text-gray-900 dark:text-gray-100">{title}</h1>
          {error && (
            <div
              role="alert"
              className="mb-4 rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300"
            >
              {error}
            </div>
          )}
          <form onSubmit={onSubmit} className="space-y-4" noValidate>
            {children}
            <button
              type="submit"
              disabled={submitting}
              className="w-full rounded-md bg-indigo-600 px-4 py-2 font-medium text-white transition-colors hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-indigo-500 dark:hover:bg-indigo-600"
            >
              {submitting ? "Please wait…" : submitLabel}
            </button>
          </form>
          <div className="mt-4 text-center text-sm text-gray-600 dark:text-gray-400">{footer}</div>
        </div>
      </div>
    </div>
  );
}
