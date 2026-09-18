"use client";

import { useMemo, useState } from "react";
import { X } from "lucide-react";
import { colorFor, fmtMs, formatCompact, formatCost, formatDurationShort, formatTime, money4, shortModel } from "./format";
import { ModelIcon, providerMeta } from "@/lib/modelProviders";

export interface SessionUsageRow {
  id: number;
  model: string;
  is_free: boolean;
  request_type: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
  provider: string | null;
  finish_reason: string | null;
  latency_ms: number | null;
  created_at: string;
}

function ModelBadge({ model }: { model: string }) {
  const hasIcon = !!providerMeta(model).icon;
  return (
    <span className="inline-flex items-center gap-1.5">
      {hasIcon ? (
        <ModelIcon id={model} />
      ) : (
        <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: colorFor(model) }} aria-hidden />
      )}
      <span className="font-semibold">{shortModel(model)}</span>
    </span>
  );
}

// A separate hash-namespace from ModelBadge so a provider named e.g. "OpenAI"
// never coincidentally shares a model's color.
function ProviderBadge({ provider }: { provider: string | null }) {
  if (!provider) return <span className="text-slate-400 dark:text-slate-500">—</span>;
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: colorFor(`provider:${provider}`) }} aria-hidden />
      {provider}
    </span>
  );
}

function providerSummary(rows: SessionUsageRow[]): React.ReactNode {
  const providers = Array.from(new Set(rows.map((r) => r.provider).filter((p): p is string => !!p)));
  if (providers.length === 0) return <span className="text-slate-400 dark:text-slate-500">—</span>;
  if (providers.length === 1) return <ProviderBadge provider={providers[0]} />;
  return <span className="text-slate-500 dark:text-slate-400">{providers.length} providers</span>;
}

function speedFor(row: SessionUsageRow): number | null {
  if (!row.latency_ms) return null;
  return row.completion_tokens / (row.latency_ms / 1000);
}

function StatTile({
  label,
  value,
  detail,
  accent,
}: {
  label: string;
  value: React.ReactNode;
  detail?: React.ReactNode;
  accent?: string;
}) {
  return (
    <div
      className="rounded-lg border border-t-[3px] border-slate-200 bg-white p-3 dark:border-white/10 dark:bg-white/5"
      style={accent ? { borderTopColor: accent } : undefined}
    >
      <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</p>
      <p className="mt-1 text-xl font-semibold text-slate-800 dark:text-slate-100">{value}</p>
      {detail && <p className="mt-0.5 text-[11px] text-slate-400 dark:text-slate-500">{detail}</p>}
    </div>
  );
}

interface ModelAgg {
  model: string;
  cost: number;
  tokens: number;
  promptTokens: number;
  completionTokens: number;
  calls: SessionUsageRow[];
}

export default function ConsumptionModal({
  open,
  onClose,
  sessionLabel,
  usage,
  firstMessageAt,
  lastMessageAt,
}: {
  open: boolean;
  onClose: () => void;
  sessionLabel: string;
  usage: SessionUsageRow[] | null;
  firstMessageAt: string | null;
  lastMessageAt: string | null;
}) {
  const [modelFilter, setModelFilter] = useState<string>("all");

  const byModel = useMemo<ModelAgg[]>(() => {
    if (!usage) return [];
    const map = new Map<string, ModelAgg>();
    for (const u of usage) {
      const agg = map.get(u.model) ?? { model: u.model, cost: 0, tokens: 0, promptTokens: 0, completionTokens: 0, calls: [] };
      agg.cost += u.cost_usd;
      agg.tokens += u.total_tokens;
      agg.promptTokens += u.prompt_tokens;
      agg.completionTokens += u.completion_tokens;
      agg.calls.push(u);
      map.set(u.model, agg);
    }
    return Array.from(map.values()).sort((a, b) => b.tokens - a.tokens);
  }, [usage]);

  if (!open) return null;

  const calls = usage ?? [];
  const totalCost = calls.reduce((s, m) => s + m.cost_usd, 0);
  const totalTokens = calls.reduce((s, m) => s + m.total_tokens, 0);
  const totalIn = calls.reduce((s, m) => s + m.prompt_tokens, 0);
  const totalOut = calls.reduce((s, m) => s + m.completion_tokens, 0);
  const durationMs =
    firstMessageAt && lastMessageAt ? new Date(lastMessageAt).getTime() - new Date(firstMessageAt).getTime() : null;
  const mostUsedModel = byModel[0];
  const peakCall = calls.length ? calls.reduce((a, b) => (b.total_tokens > a.total_tokens ? b : a)) : null;
  const maxModelTokens = Math.max(...byModel.map((m) => m.tokens), 1);

  const filteredCalls = modelFilter === "all" ? calls : calls.filter((c) => c.model === modelFilter);
  const mostExpensive = filteredCalls.length ? filteredCalls.reduce((a, b) => (b.cost_usd > a.cost_usd ? b : a)) : null;
  const filteredIn = filteredCalls.reduce((s, m) => s + m.prompt_tokens, 0);
  const filteredOut = filteredCalls.reduce((s, m) => s + m.completion_tokens, 0);
  const timedCalls = filteredCalls.filter((c) => c.latency_ms != null);
  const avgLatency = timedCalls.length ? timedCalls.reduce((s, c) => s + (c.latency_ms || 0), 0) / timedCalls.length : null;
  const fastestCall = timedCalls.length ? timedCalls.reduce((a, b) => ((b.latency_ms || 0) < (a.latency_ms || 0) ? b : a)) : null;
  const slowestCall = timedCalls.length ? timedCalls.reduce((a, b) => ((b.latency_ms || 0) > (a.latency_ms || 0) ? b : a)) : null;
  const realModels = byModel.filter((m) => m.tokens > 0);
  const mostEfficient =
    realModels.length > 1 ? realModels.reduce((a, b) => (b.cost / b.tokens < a.cost / a.tokens ? b : a)) : null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div
        className="flex max-h-[90vh] w-full max-w-4xl flex-col overflow-hidden rounded-xl bg-white shadow-2xl dark:bg-night-surface"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4 dark:border-white/10">
          <div>
            <h2 className="text-base font-semibold text-slate-800 dark:text-slate-100">Conversation Analytics</h2>
            <p className="text-xs text-slate-500 dark:text-slate-400">Usage for {sessionLabel}</p>
          </div>
          <button onClick={onClose} className="rounded p-1 text-slate-400 hover:bg-slate-100 dark:text-slate-500 dark:hover:bg-white/10">
            <X size={18} />
          </button>
        </div>

        <div className="overflow-y-auto p-5">
          {calls.length === 0 ? (
            <div className="rounded-lg border border-dashed border-slate-300 p-6 text-center dark:border-white/15">
              <p className="font-medium text-slate-700 dark:text-slate-200">No AI usage recorded for this conversation.</p>
              <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
                This happens for conversations logged before session-linked cost/token tracking existed, or ones where
                every AI call failed before a reply came back.
              </p>
            </div>
          ) : (
            <>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <StatTile label="Total tokens" value={formatCompact(totalTokens)} detail={`${formatCompact(totalIn)} in · ${formatCompact(totalOut)} out`} />
                <StatTile label="Total cost" value={formatCost(totalCost)} detail={`${formatCost(totalCost / calls.length)} avg/call`} />
                <StatTile label="AI calls" value={String(calls.length)} detail={`${byModel.length} model${byModel.length === 1 ? "" : "s"}`} />
                <StatTile
                  label="Duration"
                  value={formatDurationShort(durationMs)}
                  detail={firstMessageAt ? new Date(firstMessageAt).toLocaleString(undefined, { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" }) : undefined}
                />
                <StatTile label="Avg tokens/call" value={formatCompact(Math.round(totalTokens / calls.length))} detail="across the conversation" />
                {mostUsedModel && (
                  <StatTile
                    label="Most-used model"
                    value={<ModelBadge model={mostUsedModel.model} />}
                    detail={`${formatCompact(mostUsedModel.tokens)} tok`}
                    accent={colorFor(mostUsedModel.model)}
                  />
                )}
                {peakCall && <StatTile label="Peak call" value={formatCompact(peakCall.total_tokens)} detail={formatTime(peakCall.created_at)} />}
              </div>

              <div className="mt-5">
                <h3 className="mb-2 text-sm font-semibold text-slate-700 dark:text-slate-300">Model breakdown</h3>
                <div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-white/10">
                  <table className="w-full min-w-[560px] text-sm">
                    <thead className="bg-slate-50 text-left text-[11px] uppercase tracking-wide text-slate-500 dark:bg-white/5 dark:text-slate-400">
                      <tr>
                        <th className="px-3 py-2">Model</th>
                        <th className="px-3 py-2">Provider</th>
                        <th className="px-3 py-2 text-right">Input</th>
                        <th className="px-3 py-2 text-right">Output</th>
                        <th className="px-3 py-2 text-right">Total</th>
                        <th className="px-3 py-2 text-right">Cost</th>
                        <th className="px-3 py-2 text-right">%</th>
                      </tr>
                    </thead>
                    <tbody>
                      {byModel.map((m) => (
                        <tr key={m.model} className="border-t border-slate-100 dark:border-white/10">
                          <td className="px-3 py-2">
                            <ModelBadge model={m.model} />
                          </td>
                          <td className="px-3 py-2">{providerSummary(m.calls)}</td>
                          <td className="px-3 py-2 text-right tabular-nums">{m.promptTokens.toLocaleString()}</td>
                          <td className="px-3 py-2 text-right tabular-nums">{m.completionTokens.toLocaleString()}</td>
                          <td className="px-3 py-2 text-right tabular-nums">{formatCompact(m.tokens)}</td>
                          <td className="px-3 py-2 text-right tabular-nums">{formatCost(m.cost)}</td>
                          <td className="px-3 py-2 text-right tabular-nums">{Math.round((m.cost / totalCost) * 100)}%</td>
                        </tr>
                      ))}
                    </tbody>
                    <tfoot>
                      <tr className="border-t border-slate-200 font-semibold dark:border-white/10">
                        <td className="px-3 py-2" colSpan={2}>
                          Total
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums">{totalIn.toLocaleString()}</td>
                        <td className="px-3 py-2 text-right tabular-nums">{totalOut.toLocaleString()}</td>
                        <td className="px-3 py-2 text-right tabular-nums">{formatCompact(totalTokens)}</td>
                        <td className="px-3 py-2 text-right tabular-nums">{formatCost(totalCost)}</td>
                        <td className="px-3 py-2 text-right tabular-nums">100%</td>
                      </tr>
                    </tfoot>
                  </table>
                </div>
              </div>

              <div className="mt-5">
                <h3 className="mb-2 text-sm font-semibold text-slate-700 dark:text-slate-300">Token flow (input vs. output)</h3>
                <div className="flex flex-col gap-1.5 rounded-lg border border-slate-200 p-3 dark:border-white/10">
                  {byModel.map((m) => {
                    const widthPct = Math.round((m.tokens / maxModelTokens) * 100);
                    const inPct = m.tokens ? Math.round((m.promptTokens / m.tokens) * 100) : 0;
                    return (
                      <div key={m.model} className="flex items-center gap-2">
                        <div className="w-32 shrink-0 truncate text-xs font-medium text-slate-600 dark:text-slate-300" title={m.model}>
                          {shortModel(m.model)}
                        </div>
                        <div className="h-4 flex-1 overflow-hidden rounded bg-slate-100 dark:bg-white/10">
                          <div className="flex h-full" style={{ width: `${widthPct}%` }}>
                            <div className="h-full bg-[#2a78d6]" style={{ width: `${inPct}%` }} />
                            <div className="h-full bg-sawo dark:bg-sawo-dark" style={{ width: `${100 - inPct}%` }} />
                          </div>
                        </div>
                        <div className="w-12 shrink-0 text-right text-xs tabular-nums text-slate-500 dark:text-slate-400">
                          {formatCompact(m.tokens)}
                        </div>
                      </div>
                    );
                  })}
                  <div className="mt-1 flex items-center gap-4 text-[11px] text-slate-400 dark:text-slate-500">
                    <span className="flex items-center gap-1.5">
                      <span className="h-2 w-2 rounded-full bg-[#2a78d6]" /> Input
                    </span>
                    <span className="flex items-center gap-1.5">
                      <span className="h-2 w-2 rounded-full bg-sawo dark:bg-sawo-dark" /> Output
                    </span>
                  </div>
                </div>
              </div>

              <div className="mt-5">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">Per-call detail</h3>
                  <div className="flex items-center gap-2">
                    <select
                      value={modelFilter}
                      onChange={(e) => setModelFilter(e.target.value)}
                      className="rounded border border-slate-300 px-2 py-1 text-xs dark:border-white/15 dark:bg-white/5 dark:text-slate-100"
                    >
                      <option value="all">All models</option>
                      {byModel.map((m) => (
                        <option key={m.model} value={m.model}>
                          {shortModel(m.model)}
                        </option>
                      ))}
                    </select>
                    <span className="text-xs text-slate-400 dark:text-slate-500">
                      {filteredCalls.length} call{filteredCalls.length === 1 ? "" : "s"}
                    </span>
                  </div>
                </div>
                <div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-white/10">
                  <table className="w-full min-w-[760px] text-sm">
                    <thead className="bg-slate-50 text-left text-[11px] uppercase tracking-wide text-slate-500 dark:bg-white/5 dark:text-slate-400">
                      <tr>
                        <th className="px-3 py-2">Time</th>
                        <th className="px-3 py-2">Model</th>
                        <th className="px-3 py-2">Provider</th>
                        <th className="px-3 py-2 text-right">Input</th>
                        <th className="px-3 py-2 text-right">Output</th>
                        <th className="px-3 py-2 text-right">Total</th>
                        <th className="px-3 py-2 text-right">Latency</th>
                        <th className="px-3 py-2 text-right">Speed</th>
                        <th className="px-3 py-2">Finish</th>
                        <th className="px-3 py-2 text-right">Cost</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredCalls.map((c) => {
                        const speed = speedFor(c);
                        return (
                          <tr key={c.id} className="border-t border-slate-100 dark:border-white/10">
                            <td className="px-3 py-2 text-xs text-slate-500 dark:text-slate-400">{formatTime(c.created_at)}</td>
                            <td className="px-3 py-2">
                              <ModelBadge model={c.model} />
                            </td>
                            <td className="px-3 py-2 text-xs">
                              <ProviderBadge provider={c.provider} />
                            </td>
                            <td className="px-3 py-2 text-right tabular-nums">{c.prompt_tokens.toLocaleString()}</td>
                            <td className="px-3 py-2 text-right tabular-nums">{c.completion_tokens.toLocaleString()}</td>
                            <td className="px-3 py-2 text-right tabular-nums">{c.total_tokens.toLocaleString()}</td>
                            <td className="px-3 py-2 text-right tabular-nums">{fmtMs(c.latency_ms)}</td>
                            <td className="px-3 py-2 text-right tabular-nums">{speed != null ? `${speed.toFixed(1)} tok/s` : "—"}</td>
                            <td className="px-3 py-2 text-xs text-slate-500 dark:text-slate-400">{c.finish_reason || "—"}</td>
                            <td className="px-3 py-2 text-right tabular-nums">{formatCost(c.cost_usd)}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>

                <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
                  {mostExpensive && (
                    <StatTile
                      label="Most expensive call"
                      value={formatCost(mostExpensive.cost_usd)}
                      detail={`${mostExpensive.provider || shortModel(mostExpensive.model)} · ${formatTime(mostExpensive.created_at)}`}
                    />
                  )}
                  {mostEfficient && (
                    <StatTile
                      label="Most efficient model"
                      value={shortModel(mostEfficient.model)}
                      detail={`${money4((mostEfficient.cost / mostEfficient.tokens) * 1000)}/1K`}
                    />
                  )}
                  <StatTile
                    label="Efficiency ratio"
                    value={filteredIn ? `${(filteredOut / filteredIn).toFixed(2)} out/in` : "—"}
                    detail={`${formatCompact(filteredIn)} in · ${formatCompact(filteredOut)} out`}
                  />
                  <StatTile label="Avg latency" value={fmtMs(avgLatency)} detail={`across ${timedCalls.length} timed call(s)`} />
                  {fastestCall && (
                    <StatTile
                      label="Fastest call"
                      value={fmtMs(fastestCall.latency_ms)}
                      detail={`${fastestCall.provider || shortModel(fastestCall.model)} · ${formatTime(fastestCall.created_at)}`}
                    />
                  )}
                  {slowestCall && (
                    <StatTile
                      label="Slowest call"
                      value={fmtMs(slowestCall.latency_ms)}
                      detail={`${slowestCall.provider || shortModel(slowestCall.model)} · ${formatTime(slowestCall.created_at)}`}
                    />
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
