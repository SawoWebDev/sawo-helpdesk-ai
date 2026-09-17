"use client";

import { FormEvent, useEffect, useState } from "react";
import { apiDelete, apiGet, apiPost, apiPut, ApiError } from "@/lib/api";
import { useCurrentUser } from "@/lib/useCurrentUser";

interface User {
  id: number;
  username: string;
  email: string | null;
  role: "admin" | "agent";
  is_active: boolean;
  created_at: string;
}

interface Paginated<T> {
  items: T[];
  total: number;
}

export default function UsersPage() {
  const { user: currentUser } = useCurrentUser();
  const [users, setUsers] = useState<User[]>([]);
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<"admin" | "agent">("agent");
  const [error, setError] = useState<string | null>(null);

  async function load() {
    const data = await apiGet<Paginated<User>>("/api/users?page=1&page_size=100");
    setUsers(data.items);
  }

  useEffect(() => {
    load();
  }, []);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await apiPost("/api/users", { username, email: email || null, password, role });
      setUsername("");
      setEmail("");
      setPassword("");
      setRole("agent");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create user");
    }
  }

  async function toggleActive(u: User) {
    await apiPut(`/api/users/${u.id}`, { is_active: !u.is_active });
    await load();
  }

  async function handleDelete(u: User) {
    if (!confirm(`Delete user "${u.username}"?`)) return;
    try {
      await apiDelete(`/api/users/${u.id}`);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to delete user");
    }
  }

  return (
    <div>
      <h1 className="mb-6 text-xl font-semibold text-slate-800 dark:text-slate-100">User Management</h1>

      <form onSubmit={handleCreate} className="mb-6 flex flex-wrap items-end gap-2 rounded-lg border border-slate-200 bg-white p-4 dark:border-white/10 dark:bg-night-surface">
        <div className="flex flex-col gap-1">
          <label className="text-xs text-slate-500 dark:text-slate-400">Username</label>
          <input value={username} onChange={(e) => setUsername(e.target.value)} required className="rounded border border-slate-300 px-3 py-2 text-sm dark:border-white/15 dark:bg-white/5 dark:text-slate-100" />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-slate-500 dark:text-slate-400">Email (optional)</label>
          <input value={email} onChange={(e) => setEmail(e.target.value)} className="rounded border border-slate-300 px-3 py-2 text-sm dark:border-white/15 dark:bg-white/5 dark:text-slate-100" />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-slate-500 dark:text-slate-400">Password</label>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} className="rounded border border-slate-300 px-3 py-2 text-sm dark:border-white/15 dark:bg-white/5 dark:text-slate-100" />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-slate-500 dark:text-slate-400">Role</label>
          <select value={role} onChange={(e) => setRole(e.target.value as "admin" | "agent")} className="rounded border border-slate-300 px-3 py-2 text-sm dark:border-white/15 dark:bg-white/5 dark:text-slate-100">
            <option value="agent">Agent</option>
            <option value="admin">Admin</option>
          </select>
        </div>
        <button type="submit" className="rounded bg-sawo px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-sawo-dark dark:bg-sawo-dark dark:hover:bg-sawo-darker">
          Add User
        </button>
      </form>

      {error && <p className="mb-3 text-sm text-red-600 dark:text-red-400">{error}</p>}

      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white dark:border-white/10 dark:bg-night-surface">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-slate-500 dark:bg-white/5 dark:text-slate-400">
            <tr>
              <th className="px-4 py-2">Username</th>
              <th className="px-4 py-2">Email</th>
              <th className="px-4 py-2">Role</th>
              <th className="px-4 py-2">Status</th>
              <th className="px-4 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} className="border-t border-slate-100 dark:border-white/10">
                <td className="px-4 py-2">{u.username}</td>
                <td className="px-4 py-2 text-slate-500 dark:text-slate-400">{u.email ?? "—"}</td>
                <td className="px-4 py-2">{u.role}</td>
                <td className="px-4 py-2">{u.is_active ? "Active" : "Deactivated"}</td>
                <td className="px-4 py-2 text-right">
                  <button onClick={() => toggleActive(u)} className="mr-3 text-sawo-dark dark:text-sawo-light">
                    {u.is_active ? "Deactivate" : "Activate"}
                  </button>
                  {currentUser?.id !== u.id && (
                    <button onClick={() => handleDelete(u)} className="text-red-600 dark:text-red-400">
                      Delete
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
