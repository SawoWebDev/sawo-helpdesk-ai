"use client";

export interface CategoryOption {
  id: number;
  name: string;
  parent_id: number | null;
}

function buildLabel(categories: CategoryOption[], category: CategoryOption): string {
  const path: string[] = [category.name];
  let current = category;
  while (current.parent_id !== null) {
    const parent = categories.find((c) => c.id === current.parent_id);
    if (!parent) break;
    path.unshift(parent.name);
    current = parent;
  }
  return path.join(" > ");
}

export default function CategorySelect({
  categories,
  value,
  onChange,
  allowEmpty = true,
}: {
  categories: CategoryOption[];
  value: number | null;
  onChange: (id: number | null) => void;
  allowEmpty?: boolean;
}) {
  return (
    <select
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}
      className="rounded border border-slate-300 px-3 py-2 text-sm"
    >
      {allowEmpty && <option value="">No category</option>}
      {categories.map((c) => (
        <option key={c.id} value={c.id}>
          {buildLabel(categories, c)}
        </option>
      ))}
    </select>
  );
}
