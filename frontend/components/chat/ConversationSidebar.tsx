"use client";

import { MessageSquare } from "lucide-react";
import { ConversationSummary } from "@/lib/conversations";

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function groupLabel(iso: string): "Today" | "Yesterday" | "Older" {
  const date = new Date(iso);
  const now = new Date();
  const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const diffDays = Math.round((startOfDay(now) - startOfDay(date)) / 86_400_000);
  if (diffDays <= 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  return "Older";
}

export default function ConversationSidebar({
  conversations,
  activeId,
  onSelect,
  onNewChat,
}: {
  conversations: ConversationSummary[];
  activeId: number | null;
  onSelect: (id: number) => void;
  onNewChat: () => void;
}) {
  const groups: Record<"Today" | "Yesterday" | "Older", ConversationSummary[]> = {
    Today: [],
    Yesterday: [],
    Older: [],
  };
  for (const conversation of conversations) {
    groups[groupLabel(conversation.updated_at)].push(conversation);
  }

  return (
    // Brown gradient in light mode (same brand gradient as the header); dark
    // mode swaps to a translucent black glass panel (not the lighter, neutral
    // `.glass` frost used elsewhere) with a single border on the sidebar's
    // one true edge — its right side — rather than a glow ring all around.
    <aside className="relative z-10 flex h-full w-64 shrink-0 flex-col border-r border-sawo-border/50 bg-gradient-to-br from-sawo-light to-sawo-dark dark:border-white/10 dark:bg-none dark:bg-black/40 dark:backdrop-blur-2xl">
      <div className="shrink-0 p-3">
        <button type="button" onClick={onNewChat} className="group relative w-full rounded-xl text-left">
          {/* Light mode: same simple card treatment as the topic/popular-
              question cards. Dark mode: its own, more visible glass panel —
              sitting on the sidebar's own dark glass, the shared `.glass`
              tint read as barely-there, so this spells out translucency,
              blur, and a lit border explicitly instead. */}
          <span className="relative flex w-full items-center justify-center rounded-xl border border-transparent bg-gradient-to-br from-white to-sawo-bg px-3 py-2 text-sm font-semibold text-sawo-dark shadow-[inset_0_1px_1px_rgba(255,255,255,0.9),inset_0_-2px_4px_-1px_rgba(139,105,71,0.12),0_6px_14px_-10px_rgba(139,105,71,0.35)] transition-colors duration-200 group-enabled:group-hover:border-sawo/40 dark:border-white/15 dark:bg-none dark:bg-white/10 dark:text-slate-100 dark:shadow-[inset_0_1px_0_rgba(255,255,255,0.15),0_4px_16px_-4px_rgba(0,0,0,0.5)] dark:backdrop-blur-md dark:group-enabled:group-hover:border-white/25 dark:group-enabled:group-hover:bg-white/15">
            New Chat
          </span>
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-3 pb-3">
        <h2 className="px-1 pb-2 text-[11px] font-bold uppercase tracking-wide text-white dark:text-slate-400">
          Your Recent Conversations
        </h2>

        {conversations.length === 0 && (
          <p className="px-1 text-sm text-white dark:text-slate-400">No conversations yet.</p>
        )}

        {(["Today", "Yesterday", "Older"] as const).map((label) =>
          groups[label].length === 0 ? null : (
            <div key={label} className="mb-3">
              <h3 className="px-1 pb-1 text-[11px] font-semibold text-white/60 dark:text-slate-500">{label}</h3>
              <ul className="flex flex-col gap-1">
                {groups[label].map((conversation) => (
                  <li key={conversation.id}>
                    <button
                      type="button"
                      onClick={() => onSelect(conversation.id)}
                      aria-current={conversation.id === activeId ? "true" : undefined}
                      className={`flex w-full flex-col gap-0.5 rounded-xl px-3 py-2 text-left transition-colors ${
                        conversation.id === activeId
                          ? "bg-white/15 dark:bg-white/10"
                          : "hover:bg-white/10 dark:hover:bg-white/5"
                      }`}
                    >
                      <span className="flex items-center gap-1.5 truncate text-sm font-medium text-white dark:text-slate-100">
                        <MessageSquare size={13} className="shrink-0 text-white/70 dark:text-slate-400" />
                        <span className="truncate">{conversation.title}</span>
                      </span>
                      <span className="pl-[19px] text-xs text-white/60 dark:text-slate-500">
                        {formatTime(conversation.updated_at)}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )
        )}
      </div>

      {/* A glare confined to the one edge that actually borders something —
          the right side — instead of a ring around the whole panel. */}
      <span
        aria-hidden
        className="pointer-events-none absolute inset-y-0 right-0 w-px dark:bg-gradient-to-b dark:from-white/50 dark:via-white/10 dark:to-transparent dark:shadow-[0_0_8px_1px_rgba(255,255,255,0.2)]"
      />
    </aside>
  );
}
