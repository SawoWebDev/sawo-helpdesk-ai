"use client";

import { FormEvent, useState } from "react";
import { login } from "@/lib/auth";
import { ApiError } from "@/lib/api";
import ThemeToggle from "@/components/chat/ThemeToggle";

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login(username, password);
      // Full navigation, not router.replace: AdminLayout's user check runs once
      // on mount and persists across client-side route changes, so a client
      // transition here would land on the dashboard still holding the stale
      // "no user" state and immediately bounce back to this page.
      window.location.href = "/admin/dashboard";
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Login failed");
      setSubmitting(false);
    }
  }

  return (
    <div className="relative flex h-screen items-center justify-center bg-slate-50 dark:bg-night-bg">
      <div className="absolute right-4 top-4">
        <ThemeToggle variant="neutral" />
      </div>
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm rounded-lg border border-slate-200 bg-white p-6 shadow-sm dark:border-white/10 dark:bg-night-surface"
      >
        <h1 className="mb-4 text-lg font-semibold text-slate-800 dark:text-slate-100">Admin Login</h1>
        <div className="mb-3 flex flex-col gap-1">
          <label className="text-sm text-slate-600 dark:text-slate-300">Username</label>
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="rounded border border-slate-300 px-3 py-2 text-sm dark:border-white/15 dark:bg-white/5 dark:text-slate-100"
            required
          />
        </div>
        <div className="mb-4 flex flex-col gap-1">
          <label className="text-sm text-slate-600 dark:text-slate-300">Password</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="rounded border border-slate-300 px-3 py-2 text-sm dark:border-white/15 dark:bg-white/5 dark:text-slate-100"
            required
          />
        </div>
        {error && <p className="mb-3 text-sm text-red-600 dark:text-red-400">{error}</p>}
        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded bg-sawo px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-sawo-dark disabled:opacity-50 dark:bg-sawo-dark dark:hover:bg-sawo-darker"
        >
          {submitting ? "Logging in..." : "Log in"}
        </button>
      </form>
    </div>
  );
}
