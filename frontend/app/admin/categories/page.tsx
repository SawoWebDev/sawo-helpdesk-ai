"use client";

import { FormEvent, useEffect, useState } from "react";
import { apiDelete, apiGet, apiPost, apiPut, ApiError } from "@/lib/api";
import CategorySelect, { CategoryOption } from "@/components/admin/CategorySelect";

interface Category extends CategoryOption {
  faq_count: number;
  child_count: number;
}

export default function CategoriesPage() {
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
        if (confirm(`"${cat.name}" has child categories or FAQs attached. Delete anyway?`)) {
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
      <h1 className="mb-6 text-xl font-semibold text-slate-800">Categories</h1>

      <form onSubmit={handleCreate} className="mb-6 flex items-end gap-2 rounded-lg border border-slate-200 bg-white p-4">
        <div className="flex flex-col gap-1">
          <label className="text-xs text-slate-500">Name</label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            className="rounded border border-slate-300 px-3 py-2 text-sm"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-slate-500">Parent (optional)</label>
          <CategorySelect categories={categories} value={parentId} onChange={setParentId} />
        </div>
        <button type="submit" className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white">
          Add Category
        </button>
      </form>

      {error && <p className="mb-3 text-sm text-red-600">{error}</p>}

      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-slate-500">
            <tr>
              <th className="px-4 py-2">Name</th>
              <th className="px-4 py-2">Parent</th>
              <th className="px-4 py-2">FAQs</th>
              <th className="px-4 py-2">Children</th>
              <th className="px-4 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {categories.map((cat) => {
              const parent = categories.find((c) => c.id === cat.parent_id);
              return (
                <tr key={cat.id} className="border-t border-slate-100">
                  <td className="px-4 py-2">
                    {editingId === cat.id ? (
                      <input
                        value={editName}
                        onChange={(e) => setEditName(e.target.value)}
                        className="rounded border border-slate-300 px-2 py-1 text-sm"
                      />
                    ) : (
                      cat.name
                    )}
                  </td>
                  <td className="px-4 py-2 text-slate-500">{parent?.name ?? "—"}</td>
                  <td className="px-4 py-2">{cat.faq_count}</td>
                  <td className="px-4 py-2">{cat.child_count}</td>
                  <td className="px-4 py-2 text-right">
                    {editingId === cat.id ? (
                      <>
                        <button onClick={() => handleRename(cat)} className="mr-2 text-blue-600">
                          Save
                        </button>
                        <button onClick={() => setEditingId(null)} className="text-slate-500">
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
                          className="mr-3 text-blue-600"
                        >
                          Rename
                        </button>
                        <button onClick={() => handleDelete(cat)} className="text-red-600">
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
