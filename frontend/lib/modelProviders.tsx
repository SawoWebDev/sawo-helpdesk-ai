// Shared provider metadata (label + brand icon) for OpenRouter model ids,
// used anywhere a model needs to be identified visually: the settings model
// picker, the AI usage tables, and the analytics dashboards.
//
// Icons come from Simple Icons' free CDN (an <img> that just disappears on
// error rather than showing a broken-image glyph if a slug doesn't exist or
// the CDN is unreachable — the provider label is always shown as text too,
// so identification never actually depends on the icon loading).
// "openai" is the one exception: cdn.simpleicons.org 404s on that slug (a
// trademark-driven removal), so it's self-hosted at
// /public/assets/icons/openai.svg instead (Simple Icons is CC0-licensed).
// It can't be recolored via URL like the others, so it renders in its
// default black on a small white chip so it stays legible in dark mode too.
export const PROVIDER_META: Record<string, { label: string; icon: string | null }> = {
  openai: { label: "OpenAI", icon: "/assets/icons/openai.svg" },
  anthropic: { label: "Anthropic", icon: "https://cdn.simpleicons.org/anthropic/191919" },
  google: { label: "Google", icon: "https://cdn.simpleicons.org/google/4285F4" },
  deepseek: { label: "DeepSeek", icon: "https://cdn.simpleicons.org/deepseek/4D6BFE" },
};

export function providerMeta(id: string) {
  const key = id.split("/")[0];
  return PROVIDER_META[key] || { label: key, icon: null };
}

/** Small round brand-icon chip for a model id's provider; renders nothing
 * (not even a placeholder) when the provider has no known icon, so callers
 * can render it unconditionally without leaving a gap. */
export function ModelIcon({ id, size = 16, className = "" }: { id: string; size?: number; className?: string }) {
  const provider = providerMeta(id);
  if (!provider.icon) return null;
  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center rounded-full bg-white p-0.5 ${className}`}
      style={{ height: size, width: size }}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={provider.icon}
        alt=""
        className="h-full w-full object-contain"
        onError={(e) => (e.currentTarget.parentElement!.style.display = "none")}
      />
    </span>
  );
}
