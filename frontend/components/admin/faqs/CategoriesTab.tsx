"use client";

import { FormEvent, useEffect, useState } from "react";
import { apiDelete, apiGet, apiPost, apiPut, ApiError } from "@/lib/api";
import CategorySelect, { CategoryOption } from "@/components/admin/CategorySelect";

interface Category extends CategoryOption {
  faq_count: number;
  child_count: number;
  vault_count: number;
  library_source_count: number;
}

export default function CategoriesTab() {
  const [categories, setCategories] = useState<Category[]>([]);
  const [name, setName] = useState("");
  const [parentId, setParentId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");

  async function load() {
    const data = await apiGet<Category[]>("/api/categories");
    setCategories(data);
  }

  useEffect(() => {
    load();
  }, []);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await apiPost("/api/categories", { name, parent_id: parentId });
      setName("");
      setParentId(null);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create category");
    }
  }

  async function handleDelete(cat: Category, force = false) {
    setError(null);
    try {
      await apiDelete(`/api/categories/${cat.id}${force ? "?force=true" : ""}`);
      await load();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        if (confirm(`"${cat.name}" has child categories, FAQs, or Library documents attached. Delete anyway?`)) {
          await handleDelete(cat, true);
        }
      } else {
        setError(err instanceof ApiError ? err.message : "Failed to delete category");
      }
    }
  }

  async function handleRename(cat: Category) {
    if (!editName.trim()) return;
    await apiPut(`/api/categories/${cat.id}`, { name: editName });
    setEditingId(null);
    await load();
  }

  return (
    <div>
      <form onSubmit={handleCreate} className="mb-6 flex items-end gap-2 rounded-lg border border-slate-200 bg-white p-4 dark:border-white/10 dark:bg-night-surface">
        <div className="flex flex-col gap-1">
          <label className="text-xs text-slate-500 dark:text-slate-400">Name</label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            className="rounded border border-slate-300 px-3 py-2 text-sm dark:border-white/15 dark:bg-white/5 dark:text-slate-100"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-slate-500 dark:text-slate-400">Parent (optional)</label>
          <CategorySelect categories={categories} value={parentId} onChange={setParentId} />
        </div>
        <button type="submit" className="rounded bg-sawo px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-sawo-dark dark:bg-sawo-dark dark:hover:bg-sawo-darker">
          Add Category
        </button>
      </form>

      {error && <p className="mb-3 text-sm text-red-600 dark:text-red-400">{error}</p>}

      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white dark:border-white/10 dark:bg-night-surface">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-slate-500 dark:bg-white/5 dark:text-slate-400">
            <tr>
              <th className="px-4 py-2">Name</th>
              <th className="px-4 py-2">Parent</th>
              <th className="px-4 py-2">FAQs</th>
              <th className="px-4 py-2">Library</th>
              <th className="px-4 py-2">Children</th>
              <th className="px-4 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {categories.map((cat) => {
              const parent = categories.find((c) => c.id === cat.parent_id);
              return (
                <tr key={cat.id} className="border-t border-slate-100 dark:border-white/10">
                  <td className="px-4 py-2">
                    {editingId === cat.id ? (
                      <input
                        value={editName}
                        onChange={(e) => setEditName(e.target.value)}
                        className="rounded border border-slate-300 px-2 py-1 text-sm dark:border-white/15 dark:bg-white/5 dark:text-slate-100"
                      />
                    ) : (
                      cat.name
                    )}
                  </td>
                  <td className="px-4 py-2 text-slate-500 dark:text-slate-400">{parent?.name ?? "—"}</td>
                  <td className="px-4 py-2">{cat.faq_count}</td>
                  <td className="px-4 py-2">{cat.vault_count + cat.library_source_count}</td>
                  <td className="px-4 py-2">{cat.child_count}</td>
                  <td className="px-4 py-2 text-right">
                    {editingId === cat.id ? (
                      <>
                        <button onClick={() => handleRename(cat)} className="mr-2 text-sawo-dark dark:text-sawo-light">
                          Save
                        </button>
                        <button onClick={() => setEditingId(null)} className="text-slate-500 dark:text-slate-400">
                          Cancel
                        </button>
                      </>
                    ) : (
                      <>
                        <button
                          onClick={() => {
                            setEditingId(cat.id);
                            setEditName(cat.name);
                          }}
                          className="mr-3 text-sawo-dark dark:text-sawo-light"
                        >
                          Rename
                        </button>
                        <button onClick={() => handleDelete(cat)} className="text-red-600 dark:text-red-400">
                          Delete
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
