"use client";

import { useState } from "react";
import { getToken } from "@/lib/api";

export default function ImageUploader({
  urls,
  onChange,
}: {
  urls: string[];
  onChange: (urls: string[]) => void;
}) {
  const [uploading, setUploading] = useState(false);
  const [urlInput, setUrlInput] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const token = getToken();
      const res = await fetch("/api/uploads", {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        body: formData,
      });
      if (!res.ok) throw new Error("Upload failed");
      const data = await res.json();
      onChange([...urls, data.url]);
    } catch {
      setError("Upload failed. Check file type and size.");
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  }

  function addUrl() {
    if (!urlInput.trim()) return;
    onChange([...urls, urlInput.trim()]);
    setUrlInput("");
  }

  function removeUrl(url: string) {
    onChange(urls.filter((u) => u !== url));
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-2">
        {urls.map((url) => (
          <div key={url} className="relative">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={url} alt="" className="h-16 w-16 rounded border border-slate-200 object-cover" />
            <button
              type="button"
              onClick={() => removeUrl(url)}
              className="absolute -right-1 -top-1 rounded-full bg-red-500 px-1 text-xs text-white"
            >
              x
            </button>
          </div>
        ))}
      </div>
      <div className="flex items-center gap-2">
        <input type="file" accept="image/*" onChange={handleFileUpload} disabled={uploading} className="text-sm" />
        {uploading && <span className="text-xs text-slate-500">Uploading...</span>}
      </div>
      <div className="flex gap-2">
        <input
          type="text"
          value={urlInput}
          onChange={(e) => setUrlInput(e.target.value)}
          placeholder="Or paste an external image URL"
          className="flex-1 rounded border border-slate-300 px-2 py-1 text-sm"
        />
        <button type="button" onClick={addUrl} className="rounded border border-slate-300 px-3 py-1 text-sm">
          Add
        </button>
      </div>
      {error && <p className="text-xs text-red-600">{error}</p>}
    </div>
  );
}
