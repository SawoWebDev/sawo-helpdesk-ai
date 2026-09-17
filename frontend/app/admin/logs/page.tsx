"use client";

import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { apiFetch, apiGet, apiPost, ApiError } from "@/lib/api";
import { useUnreadSessions } from "@/lib/useUnreadSessions";
import Pagination from "@/components/admin/Pagination";
import DateRangePopover from "@/components/admin/logs/DateRangePopover";
import ConsumptionModal, { SessionUsageRow } from "@/components/admin/logs/ConsumptionModal";
import { buildSearchRegex, formatCost, formatDayLabel, formatDisplayDate, formatTime } from "@/components/admin/logs/format";
import {
  ArrowLeft,
  BarChart3,
  ChevronDown,
  ChevronUp,
  Copy,
  MoreVertical,
  Search,
  Trash2,
} from "lucide-react";

interface ChatLogRow {
  id: number;
  question_text: string;
  answer_text: string;
  matched_faq_ids: number[];
  matched_vault_ids: number[];
  confidence_score: number | null;
  engine_used: string;
  session_id: string | null;
  ip_address: string | null;
  created_at: string;
}

interface SessionSummary {
  session_id: string;
  ip_address: string | null;
  message_count: number;
  first_question: string;
  first_at: string;
  last_at: string;
  session_cost_usd: number;
  match_count: number | null;
  preview_text: string | null;
}

interface Paginated<T> {
  items: T[];
  total: number;
}

const PAGE_SIZE = 20;

function shortId(id: string): string {
  return id.slice(0, 8);
}

function sessionHeadline(s: SessionSummary): string {
  return s.ip_address || `Conversation #${shortId(s.session_id)}`;
}

function highlightText(text: string, regex: RegExp | null): React.ReactNode {
  if (!regex) return text;
  const re = new RegExp(regex.source, regex.flags.includes("g") ? regex.flags : regex.flags + "g");
  const parts: React.ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let key = 0;
  re.lastIndex = 0;
  while ((match = re.exec(text)) !== null) {
    if (match.index > lastIndex) parts.push(text.slice(lastIndex, match.index));
    parts.push(
      <mark key={key++} data-match className="rounded-sm bg-amber-200 px-0.5 dark:bg-amber-500/40">
        {match[0]}
      </mark>
    );
    lastIndex = match.index + match[0].length;
    if (match[0].length === 0) re.lastIndex++;
  }
  if (lastIndex < text.length) parts.push(text.slice(lastIndex));
  return parts.length ? parts : text;
}

interface BubbleItem {
  kind: "separator" | "bubble";
  day?: string;
  key: string;
  role?: "user" | "assistant";
  text?: string;
  createdAt?: string;
  log?: ChatLogRow;
}

function buildBubbles(thread: ChatLogRow[]): BubbleItem[] {
  const items: BubbleItem[] = [];
  let lastDay: string | null = null;
  for (const log of thread) {
    const d = new Date(log.created_at);
    const dayKey = d.toDateString();
    if (dayKey !== lastDay) {
      items.push({ kind: "separator", key: `sep-${dayKey}`, day: formatDayLabel(d) });
      lastDay = dayKey;
    }
    items.push({ kind: "bubble", key: `${log.id}-q`, role: "user", text: log.question_text, createdAt: log.created_at, log });
    items.push({ kind: "bubble", key: `${log.id}-a`, role: "assistant", text: log.answer_text, createdAt: log.created_at, log });
  }
  return items;
}

export default function LogsPage() {
  const { isUnread, markRead, markUnread } = useUnreadSessions();

  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [dateFrom, setDateFrom] = useState<string | null>(null);
  const [dateTo, setDateTo] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [selectMode, setSelectMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [deleting, setDeleting] = useState(false);
  const [rowMenuFor, setRowMenuFor] = useState<string | null>(null);

  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [selectedSession, setSelectedSession] = useState<SessionSummary | null>(null);
  const [thread, setThread] = useState<ChatLogRow[] | null>(null);
  const [threadLoading, setThreadLoading] = useState(false);
  const [threadMenuOpen, setThreadMenuOpen] = useState(false);
  const [savingLogId, setSavingLogId] = useState<number | null>(null);

  const [showConsumption, setShowConsumption] = useState(false);
  const [usage, setUsage] = useState<SessionUsageRow[] | null>(null);

  const [matchIndex, setMatchIndex] = useState(-1);
  const [matchTotal, setMatchTotal] = useState(0);
  const threadRef = useRef<HTMLDivElement>(null);
  const rowMenuRef = useRef<HTMLDivElement>(null);

  // Debounce the search box 350ms before it drives a refetch.
  useEffect(() => {
    const t = setTimeout(() => {
      setSearch(searchInput);
      setPage(1);
    }, 350);
    return () => clearTimeout(t);
  }, [searchInput]);

  function loadSessions() {
    const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
    if (search) params.set("search", search);
    if (dateFrom) params.set("start_at", new Date(`${dateFrom}T00:00:00`).toISOString());
    if (dateTo) params.set("end_at", new Date(`${dateTo}T23:59:59.999`).toISOString());
    setLoading(true);
    apiGet<Paginated<SessionSummary>>(`/api/logs/sessions?${params.toString()}`)
      .then((data) => {
        setSessions(data.items);
        setTotal(data.total);
      })
      .finally(() => setLoading(false));
  }

  useEffect(loadSessions, [page, search, dateFrom, dateTo]);

  useEffect(() => {
    function handleOutside(e: MouseEvent) {
      if (rowMenuRef.current && !rowMenuRef.current.contains(e.target as Node)) setRowMenuFor(null);
    }
    document.addEventListener("mousedown", handleOutside);
    return () => document.removeEventListener("mousedown", handleOutside);
  }, []);

  function openSession(session: SessionSummary) {
    setSelectedSessionId(session.session_id);
    setSelectedSession(session);
    setThread(null);
    setThreadLoading(true);
    setThreadMenuOpen(false);
    setUsage(null);
    setShowConsumption(false);
    markRead(session.session_id, session.last_at);
    apiGet<ChatLogRow[]>(`/api/logs/sessions/${encodeURIComponent(session.session_id)}`)
      .then(setThread)
      .catch(() => setThread([]))
      .finally(() => setThreadLoading(false));
  }

  function closeThread() {
    setSelectedSessionId(null);
    setSelectedSession(null);
    setThread(null);
  }

  const searchRegex = useMemo(() => buildSearchRegex(search), [search]);
  const bubbles = useMemo(() => (thread ? buildBubbles(thread) : []), [thread]);

  useEffect(() => {
    if (!threadRef.current) return;
    const marks = threadRef.current.querySelectorAll<HTMLElement>("mark[data-match]");
    setMatchTotal(marks.length);
    setMatchIndex(marks.length ? 0 : -1);
  }, [thread, search]);

  useEffect(() => {
    if (!threadRef.current || matchIndex < 0) return;
    const marks = threadRef.current.querySelectorAll<HTMLElement>("mark[data-match]");
    marks.forEach((m, i) => {
      if (i === matchIndex) {
        m.classList.add("bg-amber-400", "outline", "outline-2", "outline-amber-600");
        m.classList.remove("bg-amber-200", "dark:bg-amber-500/40");
        m.scrollIntoView({ block: "center", behavior: "smooth" });
      } else {
        m.classList.remove("bg-amber-400", "outline", "outline-2", "outline-amber-600");
        m.classList.add("bg-amber-200", "dark:bg-amber-500/40");
      }
    });
  }, [matchIndex]);

  function toggleSelect(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleSelectAll() {
    setSelectedIds((prev) => {
      const allSelected = sessions.every((s) => prev.has(s.session_id));
      if (allSelected) return new Set();
      return new Set(sessions.map((s) => s.session_id));
    });
  }

  async function deleteSessions(ids: string[]) {
    if (ids.length === 0) return;
    if (!confirm(`Delete ${ids.length} conversation(s)? This cannot be undone.`)) return;
    setDeleting(true);
    setError(null);
    try {
      await apiFetch("/api/logs/sessions", { method: "DELETE", body: JSON.stringify({ session_ids: ids }) });
      if (selectedSessionId && ids.includes(selectedSessionId)) closeThread();
      setSelectedIds(new Set());
      setSelectMode(false);
      loadSessions();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to delete conversation(s)");
    } finally {
      setDeleting(false);
    }
  }

  async function loadUsage() {
    if (!selectedSessionId) return;
    setShowConsumption(true);
    if (usage) return;
    try {
      const data = await apiGet<SessionUsageRow[]>(`/api/logs/sessions/${encodeURIComponent(selectedSessionId)}/usage`);
      setUsage(data);
    } catch {
      setUsage([]);
    }
  }

  async function handleSaveAsFaq(log: ChatLogRow) {
    if (!confirm("Save this answer as a new published FAQ entry? The chat log will be removed.")) return;
    setSavingLogId(log.id);
    setError(null);
    try {
      await apiPost(`/api/logs/${log.id}/save-as-faq`, {});
      setThread((prev) => (prev ? prev.filter((l) => l.id !== log.id) : prev));
      loadSessions();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to save as FAQ");
    } finally {
      setSavingLogId(null);
    }
  }

  function copySessionId() {
    if (selectedSessionId) navigator.clipboard?.writeText(selectedSessionId).catch(() => {});
    setThreadMenuOpen(false);
  }

  const allOnPageSelected = sessions.length > 0 && sessions.every((s) => selectedIds.has(s.session_id));
  const someOnPageSelected = sessions.some((s) => selectedIds.has(s.session_id));

  return (
    <div className="flex h-[calc(100vh-3rem)] flex-col">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-800 dark:text-slate-100">Chat Logs</h1>
      </div>

      {error && (
        <p className="mb-3 rounded bg-red-50 px-3 py-2 text-sm text-red-800 dark:bg-red-500/15 dark:text-red-300">{error}</p>
      )}

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="relative min-w-[200px] flex-1">
          <Search size={14} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="search"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Search message text…"
            className="w-full rounded border border-slate-300 py-2 pl-8 pr-3 text-sm dark:border-white/15 dark:bg-white/5 dark:text-slate-100"
          />
        </div>
        <DateRangePopover
          from={dateFrom}
          to={dateTo}
          onChange={(f, t) => {
            setDateFrom(f);
            setDateTo(t);
            setPage(1);
          }}
        />
      </div>

      <div className="flex min-h-0 flex-1 gap-4">
        {/* Session list column */}
        <div className={`flex min-h-0 w-full flex-col md:w-80 md:shrink-0 ${selectedSessionId ? "hidden md:flex" : "flex"}`}>
          {selectMode && (
            <div className="mb-2 flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm dark:border-white/10 dark:bg-night-surface">
              <input
                type="checkbox"
                checked={allOnPageSelected}
                ref={(el) => {
                  if (el) el.indeterminate = someOnPageSelected && !allOnPageSelected;
                }}
                onChange={toggleSelectAll}
              />
              <span className="text-slate-500 dark:text-slate-400">{selectedIds.size} selected</span>
              <div className="ml-auto flex items-center gap-3">
                {selectedIds.size > 0 && (
                  <button
                    onClick={() => deleteSessions(Array.from(selectedIds))}
                    disabled={deleting}
                    className="text-red-600 hover:underline disabled:opacity-50 dark:text-red-400"
                  >
                    Delete
                  </button>
                )}
                <button
                  onClick={() => {
                    setSelectMode(false);
                    setSelectedIds(new Set());
                  }}
                  className="text-slate-500 hover:underline dark:text-slate-400"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          <div className="flex-1 overflow-y-auto rounded-lg border border-slate-200 bg-white dark:border-white/10 dark:bg-night-surface">
            {loading && sessions.length === 0 && (
              <p className="p-6 text-center text-sm text-slate-400 dark:text-slate-500">Loading…</p>
            )}
            {!loading && sessions.length === 0 && (
              <div className="p-6 text-center">
                <p className="font-medium text-slate-600 dark:text-slate-300">
                  {search || dateFrom ? "No conversations match these filters." : "No conversations yet."}
                </p>
                <p className="mt-1 text-sm text-slate-400 dark:text-slate-500">
                  {search || dateFrom ? "Try a different date range or search term." : "Sessions appear here as visitors chat with the bot."}
                </p>
              </div>
            )}
            <ul className="divide-y divide-slate-100 dark:divide-white/10">
              {sessions.map((s) => {
                const unread = isUnread(s.session_id, s.last_at);
                const active = s.session_id === selectedSessionId;
                const preview = search && s.preview_text ? s.preview_text : s.first_question;
                return (
                  <li key={s.session_id} className={`relative ${active ? "bg-sawo-bg dark:bg-white/10" : ""}`}>
                    <div className="flex items-start gap-2 px-3 py-2.5">
                      {selectMode && (
                        <input
                          type="checkbox"
                          className="mt-1 shrink-0"
                          checked={selectedIds.has(s.session_id)}
                          onChange={() => toggleSelect(s.session_id)}
                        />
                      )}
                      <button onClick={() => openSession(s)} className="min-w-0 flex-1 text-left">
                        <div className="flex items-center justify-between gap-2">
                          <span className="flex min-w-0 items-center gap-1.5">
                            {unread && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-red-500" aria-hidden />}
                            <span className={`truncate text-sm ${unread ? "font-bold text-slate-800 dark:text-slate-100" : "font-medium text-slate-700 dark:text-slate-200"}`}>
                              {sessionHeadline(s)}
                            </span>
                          </span>
                          {s.match_count && s.match_count > 1 && (
                            <span className="shrink-0 rounded-full border border-slate-300 px-1.5 text-[10px] text-slate-500 dark:border-white/15 dark:text-slate-400">
                              {s.match_count} matches
                            </span>
                          )}
                        </div>
                        <p className={`mt-0.5 line-clamp-2 text-xs ${unread ? "font-semibold text-slate-700 dark:text-slate-200" : "text-slate-500 dark:text-slate-400"}`}>
                          {preview}
                        </p>
                        <p className="mt-1 text-[11px] text-slate-400 dark:text-slate-500">
                          {s.message_count} message{s.message_count === 1 ? "" : "s"} · {formatCost(s.session_cost_usd)} ·{" "}
                          {formatDisplayDate(s.last_at)} · #{shortId(s.session_id)}
                        </p>
                      </button>
                      <div className="relative shrink-0" ref={rowMenuFor === s.session_id ? rowMenuRef : undefined}>
                        <button
                          onClick={() => setRowMenuFor(rowMenuFor === s.session_id ? null : s.session_id)}
                          className="rounded p-1 text-slate-400 hover:bg-slate-100 dark:hover:bg-white/10"
                        >
                          <MoreVertical size={14} />
                        </button>
                        {rowMenuFor === s.session_id && (
                          <div className="absolute right-0 top-6 z-10 w-40 rounded-md border border-slate-200 bg-white py-1 text-sm shadow-lg dark:border-white/10 dark:bg-night-surface">
                            <button
                              onClick={() => {
                                setSelectMode(true);
                                toggleSelect(s.session_id);
                                setRowMenuFor(null);
                              }}
                              className="block w-full px-3 py-1.5 text-left hover:bg-slate-50 dark:hover:bg-white/5"
                            >
                              Select
                            </button>
                            <button
                              onClick={() => {
                                if (unread) markRead(s.session_id, s.last_at);
                                else markUnread(s.session_id);
                                setRowMenuFor(null);
                              }}
                              className="block w-full px-3 py-1.5 text-left hover:bg-slate-50 dark:hover:bg-white/5"
                            >
                              Mark as {unread ? "read" : "unread"}
                            </button>
                            <button
                              onClick={() => {
                                setRowMenuFor(null);
                                deleteSessions([s.session_id]);
                              }}
                              className="block w-full px-3 py-1.5 text-left text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-500/10"
                            >
                              Delete
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
          <Pagination page={page} pageSize={PAGE_SIZE} total={total} onPageChange={setPage} />
        </div>

        {/* Thread column */}
        <div className={`min-h-0 flex-1 flex-col ${selectedSessionId ? "flex" : "hidden md:flex"}`}>
          {!selectedSessionId ? (
            <div className="flex flex-1 items-center justify-center rounded-lg border border-dashed border-slate-300 text-sm text-slate-400 dark:border-white/15 dark:text-slate-500">
              Select a conversation to view its transcript.
            </div>
          ) : (
            <div className="flex min-h-0 flex-1 flex-col rounded-lg border border-slate-200 bg-white dark:border-white/10 dark:bg-night-surface">
              <div className="border-b border-slate-200 px-4 py-3 dark:border-white/10">
                <div className="flex items-center gap-2">
                  <button onClick={closeThread} className="rounded p-1 text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-white/10 md:hidden">
                    <ArrowLeft size={16} />
                  </button>
                  <h2 className="min-w-0 flex-1 truncate text-sm font-semibold text-slate-800 dark:text-slate-100">
                    {selectedSession ? sessionHeadline(selectedSession) : ""}
                  </h2>
                  <div className="relative shrink-0">
                    <button
                      onClick={() => setThreadMenuOpen((o) => !o)}
                      className="rounded p-1 text-slate-400 hover:bg-slate-100 dark:hover:bg-white/10"
                    >
                      <MoreVertical size={16} />
                    </button>
                    {threadMenuOpen && (
                      <div className="absolute right-0 top-7 z-10 w-44 rounded-md border border-slate-200 bg-white py-1 text-sm shadow-lg dark:border-white/10 dark:bg-night-surface">
                        <button
                          onClick={() => {
                            setThreadMenuOpen(false);
                            loadUsage();
                          }}
                          className="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-slate-50 dark:hover:bg-white/5"
                        >
                          <BarChart3 size={14} /> Analytics
                        </button>
                        <button onClick={copySessionId} className="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-slate-50 dark:hover:bg-white/5">
                          <Copy size={14} /> Copy ID
                        </button>
                        <button
                          onClick={() => {
                            setThreadMenuOpen(false);
                            if (selectedSessionId) deleteSessions([selectedSessionId]);
                          }}
                          className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-500/10"
                        >
                          <Trash2 size={14} /> Delete
                        </button>
                      </div>
                    )}
                  </div>
                </div>
                {selectedSession && (
                  <p className="mt-0.5 text-xs text-slate-400 dark:text-slate-500">
                    {selectedSession.message_count} message{selectedSession.message_count === 1 ? "" : "s"} ·{" "}
                    {formatDisplayDate(selectedSession.first_at)}
                    {selectedSession.first_at.slice(0, 10) !== selectedSession.last_at.slice(0, 10)
                      ? ` – ${formatDisplayDate(selectedSession.last_at)}`
                      : ""}{" "}
                    · {formatCost(selectedSession.session_cost_usd)}
                  </p>
                )}
              </div>

              {search && matchTotal > 0 && (
                <div className="flex items-center gap-2 border-b border-slate-100 bg-amber-50/60 px-4 py-1.5 text-xs dark:border-white/10 dark:bg-amber-500/10">
                  <span className="text-slate-600 dark:text-slate-300">
                    Match {matchIndex + 1} of {matchTotal}
                  </span>
                  <button
                    onClick={() => setMatchIndex((i) => (i - 1 + matchTotal) % matchTotal)}
                    className="rounded p-0.5 hover:bg-amber-100 dark:hover:bg-white/10"
                  >
                    <ChevronUp size={14} />
                  </button>
                  <button
                    onClick={() => setMatchIndex((i) => (i + 1) % matchTotal)}
                    className="rounded p-0.5 hover:bg-amber-100 dark:hover:bg-white/10"
                  >
                    <ChevronDown size={14} />
                  </button>
                </div>
              )}

              <div ref={threadRef} className="flex-1 overflow-y-auto px-4 py-4">
                {threadLoading && <p className="text-center text-sm text-slate-400 dark:text-slate-500">Loading conversation…</p>}
                {!threadLoading && thread && thread.length === 0 && (
                  <p className="text-center text-sm text-slate-400 dark:text-slate-500">This conversation has no messages.</p>
                )}
                {!threadLoading &&
                  bubbles.map((item) => {
                    if (item.kind === "separator") {
                      return (
                        <div key={item.key} className="my-3 flex items-center gap-3 text-[11px] text-slate-400 dark:text-slate-500">
                          <div className="h-px flex-1 bg-slate-200 dark:bg-white/10" />
                          {item.day}
                          <div className="h-px flex-1 bg-slate-200 dark:bg-white/10" />
                        </div>
                      );
                    }
                    const isUser = item.role === "user";
                    const log = item.log!;
                    const hasMatch = log.matched_faq_ids.length > 0 || log.matched_vault_ids.length > 0;
                    return (
                      <div key={item.key} className={`mb-2 flex ${isUser ? "justify-start" : "justify-end"}`}>
                        <div className={`max-w-[75%] ${isUser ? "" : "text-right"}`}>
                          <p className="mb-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
                            {isUser ? "Visitor" : "Bot"}
                          </p>
                          <div
                            className={`whitespace-pre-wrap rounded-xl px-3 py-2 text-left text-sm shadow-sm ${
                              isUser
                                ? "rounded-tl-sm border-l-4 border-sawo bg-sawo-bg text-slate-800 dark:border-sawo-light dark:bg-white/5 dark:text-slate-100"
                                : "rounded-tr-sm bg-sawo text-white dark:bg-sawo-dark"
                            }`}
                          >
                            {highlightText(item.text || "", searchRegex)}
                          </div>
                          <p className="mt-0.5 text-[10px] text-slate-400 dark:text-slate-500">{formatTime(item.createdAt!)}</p>
                          {!isUser && hasMatch && (
                            <button
                              onClick={() => handleSaveAsFaq(log)}
                              disabled={savingLogId === log.id}
                              className="mt-0.5 text-[11px] font-medium text-sawo-dark hover:underline disabled:opacity-50 dark:text-sawo-light"
                            >
                              {savingLogId === log.id ? "Saving…" : "Save as FAQ"}
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  })}
              </div>
            </div>
          )}
        </div>
      </div>

      <ConsumptionModal
        open={showConsumption}
        onClose={() => setShowConsumption(false)}
        sessionLabel={selectedSessionId ? `#${shortId(selectedSessionId)}` : ""}
        usage={usage}
        firstMessageAt={selectedSession?.first_at ?? null}
        lastMessageAt={selectedSession?.last_at ?? null}
      />
    </div>
  );
}
