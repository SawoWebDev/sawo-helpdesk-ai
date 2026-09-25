"use client";

import { Fragment, useEffect, useState } from "react";
import { apiGet } from "@/lib/api";
import { useIsDark } from "@/lib/useIsDark";
import { CATEGORICAL, SEQUENTIAL_DARK, SEQUENTIAL_LIGHT, STATUS, pick, sourceColor, sourceLabel } from "@/components/admin/analytics/colors";
import { BreakdownList, Card, MetricCard, RangeTabs } from "@/components/admin/analytics/StatPrimitives";
import TrendChart from "@/components/admin/analytics/TrendChart";
import StackedBarChart from "@/components/admin/analytics/StackedBarChart";
import Pagination from "@/components/admin/Pagination";
import { fmtMs, formatTime } from "@/components/admin/logs/format";
import { ModelIcon } from "@/lib/modelProviders";
import PageHeader from "@/components/admin/PageHeader";
import {
  Activity,
  BadgeCheck,
  BookOpen,
  Bot,
  CircleHelp,
  Clock3,
  ChevronRight,
  Gauge,
  MessagesSquare,
  Sparkles,
  ThumbsUp,
  Users,
  WalletCards,
} from "lucide-react";

interface OverviewStats {
  chats_today: number;
  chats_7d: number;
  chats_30d: number;
  unique_sessions_7d: number;
  answered_rate_7d: number;
  chats_7d_delta_pct: number | null;
  answered_rate_delta_7d_points: number | null;
  ai_cost_7d_usd: number;
  ai_cost_7d_delta_pct: number | null;
  avg_latency_7d_ms: number | null;
  p95_latency_7d_ms: number | null;
  cost_per_answer_7d_usd: number | null;
  satisfaction_rate_7d: number | null;
  rated_total_7d: number;
  satisfaction_rate_delta_7d_points: number | null;
  unanswered_pending: number;
  faq_total: number;
  faq_published: number;
  ai_cost_today_usd: number;
  ai_cost_30d_usd: number;
  active_model: string;
  active_model_is_free: boolean;
}

interface ChatTrendPoint {
  day: string;
  messages: number;
  sessions: number;
  answered: number;
  unanswered: number;
}

interface ConfidenceBucket {
  bucket: string;
  count: number;
}

interface CategoryBreakdown {
  category_id: number | null;
  category_name: string;
  count: number;
}

interface SourceBreakdown {
  source: string;
  count: number;
}

interface ContentGrowthPoint {
  day: string;
  by_source: Record<string, number>;
  total: number;
}

interface ModelUsage {
  model: string;
  is_free: boolean;
  requests_total: number;
  tokens_total: number;
  prompt_tokens_total: number;
  completion_tokens_total: number;
  cost_total_usd: number;
  requests_today: number;
  tokens_today: number;
  cost_today_usd: number;
  last_used_at: string | null;
}

interface UsageCall {
  id: number;
  model: string;
  is_free: boolean;
  request_type: string;
  feature: string | null;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
  provider: string | null;
  finish_reason: string | null;
  latency_ms: number | null;
  session_id: string | null;
  created_at: string;
}

interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

interface OpenRouterBalance {
  configured: boolean;
  total_credits: number;
  total_usage: number;
  balance: number;
  error: string | null;
}

interface DailyModelUsage {
  day: string;
  requests: number;
  tokens: number;
  cost_usd: number;
}

interface FeatureUsage {
  feature: string;
  requests_total: number;
  tokens_total: number;
  cost_total_usd: number;
}

function formatCost(usd: number | null | undefined): string {
  if (usd === null || usd === undefined) return "N/A";
  if (usd === 0) return "$0.00";
  if (usd < 0.0001) return "<$0.0001";
  if (usd < 0.01) return `$${usd.toFixed(4)}`;
  return `$${usd.toFixed(2)}`;
}

function formatDelta(value: number | null | undefined, suffix = "%"): string {
  if (value === null || value === undefined) return "No prior period";
  if (value === 0) return `0${suffix} vs prior 7d`;
  return `${value > 0 ? "+" : ""}${value}${suffix} vs prior 7d`;
}

function deltaClass(value: number | null | undefined, invert = false): string {
  if (value === null || value === undefined || value === 0) return "bg-slate-100 text-slate-600 dark:bg-white/10 dark:text-slate-300";
  const positive = invert ? value < 0 : value > 0;
  return positive
    ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300"
    : "bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300";
}

const FAQ_SOURCE_ORDER = ["manual", "chat_log", "chat_auto", "import"];

// Human labels for ai_usage_logs.feature values (services/ai_usage.py's
// FEATURE_* constants) — "other" covers legacy rows logged before this
// column existed, plus anything not in this map.
const FEATURE_LABELS: Record<string, string> = {
  chat_query_embedding: "Chat – Query Embedding",
  relevance_check: "Chat – Relevance Check",
  chat_answer_generation: "Chat – Answer Generation",
  grounding_check: "Grounding Check",
  chat_off_topic_reply: "Chat – Off-topic Reply",
  library_ingest: "Library – Crawling / Ingestion",
  library_search: "Library – Search",
  library_search_answer: "Library – Search Answer",
  vault_search: "Vault – Search",
  faq_dedup: "FAQ – Duplicate Check",
  faq_reindex: "FAQ – Reindexing",
  vault_reindex: "Vault – Reindexing",
  other: "Other / Legacy",
};

function featureLabel(feature: string): string {
  return FEATURE_LABELS[feature] ?? feature;
}

export default function AnalyticsPage() {
  const isDark = useIsDark();
  const [days, setDays] = useState(30);

  const [overview, setOverview] = useState<OverviewStats | null>(null);
  const [chatTrend, setChatTrend] = useState<ChatTrendPoint[] | null>(null);
  const [confidence, setConfidence] = useState<ConfidenceBucket[] | null>(null);
  const [categories, setCategories] = useState<CategoryBreakdown[] | null>(null);
  const [faqSources, setFaqSources] = useState<SourceBreakdown[] | null>(null);
  const [contentGrowth, setContentGrowth] = useState<ContentGrowthPoint[] | null>(null);
  const [modelUsage, setModelUsage] = useState<ModelUsage[] | null>(null);
  const [featureUsage, setFeatureUsage] = useState<FeatureUsage[] | null>(null);
  const [expandedModel, setExpandedModel] = useState<string | null>(null);
  const [dailyModelUsage, setDailyModelUsage] = useState<DailyModelUsage[] | null>(null);
  const [dailyModelLoading, setDailyModelLoading] = useState(false);
  const [orBalance, setOrBalance] = useState<OpenRouterBalance | null>(null);

  const [calls, setCalls] = useState<Paginated<UsageCall> | null>(null);
  const [callsPage, setCallsPage] = useState(1);
  const [callsModelFilter, setCallsModelFilter] = useState("");
  const callsPageSize = 20;

  function loadModelUsage() {
    apiGet<ModelUsage[]>("/api/usage/models").then(setModelUsage);
  }

  function loadCalls() {
    const params = new URLSearchParams({ page: String(callsPage), page_size: String(callsPageSize) });
    if (callsModelFilter) params.set("model", callsModelFilter);
    apiGet<Paginated<UsageCall>>(`/api/usage/calls?${params.toString()}`).then(setCalls);
  }

  async function toggleModel(model: string) {
    if (expandedModel === model) {
      setExpandedModel(null);
      setDailyModelUsage(null);
      return;
    }
    setExpandedModel(model);
    setDailyModelUsage(null);
    setDailyModelLoading(true);
    try {
      const data = await apiGet<DailyModelUsage[]>(`/api/usage/models/daily?model=${encodeURIComponent(model)}`);
      setDailyModelUsage(data);
    } finally {
      setDailyModelLoading(false);
    }
  }

  useEffect(() => {
    apiGet<OverviewStats>("/api/analytics/overview").then(setOverview);
    apiGet<SourceBreakdown[]>("/api/analytics/faq-sources").then(setFaqSources);
    apiGet<FeatureUsage[]>("/api/analytics/usage-by-feature").then(setFeatureUsage);
    apiGet<OpenRouterBalance>("/api/usage/openrouter-balance").then(setOrBalance);
    loadModelUsage();
    const interval = setInterval(loadModelUsage, 30000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    loadCalls();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [callsPage, callsModelFilter]);

  useEffect(() => {
    setChatTrend(null);
    setConfidence(null);
    setCategories(null);
    setContentGrowth(null);
    apiGet<ChatTrendPoint[]>(`/api/analytics/chat-trend?days=${days}`).then(setChatTrend);
    apiGet<ConfidenceBucket[]>(`/api/analytics/confidence?days=${days}`).then(setConfidence);
    apiGet<CategoryBreakdown[]>(`/api/analytics/categories?days=${days}`).then(setCategories);
    apiGet<ContentGrowthPoint[]>(`/api/analytics/content-growth?days=${days}`).then(setContentGrowth);
  }, [days]);

  const answeredTotals = chatTrend?.reduce(
    (acc, d) => ({ answered: acc.answered + d.answered, unanswered: acc.unanswered + d.unanswered }),
    { answered: 0, unanswered: 0 }
  );

  const sequential = isDark ? SEQUENTIAL_DARK : SEQUENTIAL_LIGHT;
  const answerHealth = overview?.answered_rate_7d ?? 0;
  const hasAttention = (overview?.unanswered_pending ?? 0) > 0;

  return (
    <div>
      <PageHeader
        icon="fa-solid fa-chart-line"
        title="Analytics"
        description="Chat volume, answer rate, and AI usage over time."
        actions={<RangeTabs value={days} onChange={setDays} />}
      />

      <div className="mb-5 grid grid-cols-1 gap-3 lg:grid-cols-[1.35fr_1fr_1fr]">
        <div className="relative overflow-hidden rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 dark:border-blue-400/20 dark:bg-blue-500/10">
          <div className="absolute right-4 top-3 text-blue-200 dark:text-blue-300/15" aria-hidden>
            <Sparkles size={46} strokeWidth={1.4} />
          </div>
          <p className="text-xs font-semibold uppercase tracking-wide text-blue-700 dark:text-blue-300">Analytics snapshot</p>
          <p className="mt-1 pr-12 text-sm font-medium text-slate-800 dark:text-slate-100">
            {overview ? `${overview.chats_today.toLocaleString()} chats today across ${overview.unique_sessions_7d.toLocaleString()} active 7-day sessions.` : "Preparing your latest conversation snapshot..."}
          </p>
        </div>
        <div className="flex items-center gap-3 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 dark:border-emerald-400/20 dark:bg-emerald-500/10">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300"><BadgeCheck size={19} /></span>
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-wide text-emerald-700 dark:text-emerald-300">Answer health</p>
            <p className="mt-0.5 text-sm font-medium text-slate-800 dark:text-slate-100">{overview ? `${answerHealth}% answered in the last 7 days` : "Loading answer quality..."}</p>
          </div>
        </div>
        <div className={`flex items-center gap-3 rounded-lg border px-4 py-3 ${hasAttention ? "border-amber-200 bg-amber-50 dark:border-amber-400/20 dark:bg-amber-500/10" : "border-slate-200 bg-slate-50 dark:border-white/10 dark:bg-white/5"}`}>
          <span className={`grid h-9 w-9 shrink-0 place-items-center rounded-lg ${hasAttention ? "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300" : "bg-slate-200 text-slate-600 dark:bg-white/10 dark:text-slate-300"}`}><CircleHelp size={19} /></span>
          <div className="min-w-0">
            <p className={`text-xs font-semibold uppercase tracking-wide ${hasAttention ? "text-amber-700 dark:text-amber-300" : "text-slate-600 dark:text-slate-300"}`}>Needs review</p>
            <p className="mt-0.5 text-sm font-medium text-slate-800 dark:text-slate-100">{overview ? `${overview.unanswered_pending.toLocaleString()} unanswered questions pending` : "Checking your queue..."}</p>
          </div>
        </div>
      </div>

      {/* Core metrics */}
      <div className="mb-4 grid grid-cols-2 gap-4 md:grid-cols-5">
        <MetricCard
          label="Chats (7d)"
          hint="How many questions people asked the assistant in the last 7 days. Higher means the chat is getting more use."
          value={overview ? overview.chats_7d.toLocaleString() : "..."}
          icon={<MessagesSquare size={17} />}
          tone="blue"
          subtitle={overview ? `${overview.chats_today} today · ${formatDelta(overview.chats_7d_delta_pct)}` : undefined}
        />
        <MetricCard
          label="Answered Rate (7d)"
          hint="Out of every 100 questions asked, how many the assistant answered using your own approved content. Higher is better, because it means fewer people leave without an answer."
          value={overview ? `${overview.answered_rate_7d}%` : "..."}
          icon={<BadgeCheck size={17} />}
          tone="emerald"
          subtitle={overview ? `${formatDelta(overview.answered_rate_delta_7d_points, " pts")} · matched real content` : "Matched real FAQ/Library content"}
        />
        <MetricCard label="Unanswered Pending" hint="Questions the assistant could not answer, still waiting for someone on your team to write an answer. Clearing these is the fastest way to improve the chat." value={overview ? overview.unanswered_pending.toLocaleString() : "..."} subtitle="Awaiting agent review" icon={<CircleHelp size={17} />} tone="amber" />
        <MetricCard label="Unique Sessions (7d)" hint="How many separate people used the chat in the last 7 days. One person asking five questions counts once here, so compare it with Chats to see how much each visitor asks." value={overview ? overview.unique_sessions_7d.toLocaleString() : "..."} subtitle="Distinct visitors" icon={<Users size={17} />} tone="violet" />
        <MetricCard
          label="Satisfaction (7d)"
          hint="Out of the people who bothered to rate an answer with a thumbs up or down in the last 7 days, how many rated it helpful. Only counts messages that got a rating, so a low count of ratings means this number isn't fully reliable yet."
          value={overview ? (overview.satisfaction_rate_7d !== null ? `${overview.satisfaction_rate_7d}%` : "—") : "..."}
          icon={<ThumbsUp size={17} />}
          tone="brand"
          subtitle={
            overview
              ? overview.rated_total_7d > 0
                ? `${formatDelta(overview.satisfaction_rate_delta_7d_points, " pts")} · ${overview.rated_total_7d} rated`
                : "No feedback rated yet"
              : undefined
          }
        />
      </div>

      {/* AI engine metrics */}
      <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
        <MetricCard
          label="Active Model"
          hint="The AI model currently answering your visitors. Different models cost different amounts and vary in speed and quality; you can change it in Settings."
          value={
            overview ? (
              <span className="flex items-center gap-1.5 truncate text-base" title={overview.active_model}>
                {overview.active_model && <ModelIcon id={overview.active_model} size={18} />}
                {overview.active_model || "—"}
              </span>
            ) : (
              "..."
            )
          }
          subtitle={overview ? (overview.active_model_is_free ? "Free tier" : "Paid") : undefined}
          icon={<Bot size={17} />}
          tone="violet"
        />
        <MetricCard label="AI Cost Today" hint="What the AI has cost you so far today, in US dollars. It keeps climbing until midnight, then starts again at zero." value={overview ? formatCost(overview.ai_cost_today_usd) : "..."} subtitle="Live spend" icon={<WalletCards size={17} />} tone="blue" />
        <MetricCard
          label="AI Cost (7d)"
          hint="What the AI cost over the last 7 days, and whether that is up or down compared with the 7 days before it."
          value={overview ? formatCost(overview.ai_cost_7d_usd) : "..."}
          subtitle={overview ? <span className={`rounded px-1.5 py-0.5 font-medium ${deltaClass(overview.ai_cost_7d_delta_pct, true)}`}>{formatDelta(overview.ai_cost_7d_delta_pct)}</span> : undefined}
          icon={<Activity size={17} />}
          tone="rose"
        />
        <MetricCard
          label="Cost / Answer"
          hint="The average price of one answer over the last 7 days. A few cents is normal. A cheaper model or a better knowledge base brings it down."
          value={overview && overview.cost_per_answer_7d_usd !== null ? formatCost(overview.cost_per_answer_7d_usd) : overview ? "N/A" : "..."}
          subtitle="Last 7 days"
          icon={<WalletCards size={17} />}
          tone="emerald"
        />
        <MetricCard
          label="AI Latency P95"
          hint="How long people wait for a reply, measured at the slower end: 95 out of 100 answers arrive faster than this. Lower feels snappier."
          value={overview && overview.p95_latency_7d_ms !== null ? fmtMs(overview.p95_latency_7d_ms) : overview ? "N/A" : "..."}
          subtitle={overview && overview.avg_latency_7d_ms !== null ? `${fmtMs(overview.avg_latency_7d_ms)} average` : "Last 7 days"}
          icon={<Clock3 size={17} />}
          tone="amber"
        />
        <MetricCard label="FAQ Entries" hint="All the questions and answers stored in your knowledge base, with how many are live for visitors. Drafts are counted in the total but are not used in replies." value={overview ? overview.faq_total.toLocaleString() : "..."} subtitle={overview ? `${overview.faq_published} published` : undefined} icon={<BookOpen size={17} />} tone="brand" />
        <MetricCard
          label="OpenRouter Balance"
          hint="The prepaid credit left in your OpenRouter account, which pays for the AI. When it runs out the chat stops answering, so top it up before it hits zero."
          value={
            !orBalance
              ? "..."
              : !orBalance.configured
                ? "Not set up"
                : orBalance.error
                  ? "Error"
                  : formatCost(orBalance.balance)
          }
          subtitle={
            !orBalance ? undefined : !orBalance.configured ? (
              <a href="/admin/settings" className="inline-flex items-center gap-0.5 text-sawo-dark hover:underline dark:text-sawo-light">
                Add a management key
                <ChevronRight size={13} aria-hidden />
              </a>
            ) : orBalance.error ? (
              orBalance.error
            ) : (
              `${formatCost(orBalance.total_usage)} used of ${formatCost(orBalance.total_credits)}`
            )
          }
          icon={<Gauge size={17} />}
          tone="blue"
        />
      </div>

      {/* Chat volume trend */}
      <Card
        title="Chat Volume"
        hint="Day-by-day view of how busy the chat is: total questions asked, and how many different people asked them."
      >
        {chatTrend ? (
          <TrendChart
            data={chatTrend.map((d) => ({ day: d.day, values: { messages: d.messages, sessions: d.sessions } }))}
            series={[
              { key: "messages", label: "Messages", color: CATEGORICAL.brand },
              { key: "sessions", label: "Unique Sessions", color: CATEGORICAL.blue },
            ]}
          />
        ) : (
          <p className="py-10 text-center text-sm text-slate-400 dark:text-slate-500">Loading...</p>
        )}
      </Card>

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Answer quality */}
        <Card
          title="Answer Quality"
          hint="How well the assistant is doing. The top split shows answered versus not answered; below it, confidence is how sure the assistant was. Lots of low-confidence answers means your knowledge base needs more detail."
        >
          <div className="mb-3">
            <BreakdownList
              items={[
                {
                  key: "answered",
                  label: "Answered",
                  value: answeredTotals?.answered ?? 0,
                  color: pick(STATUS.good, isDark),
                },
                {
                  key: "unanswered",
                  label: "Unanswered / fallback",
                  value: answeredTotals?.unanswered ?? 0,
                  color: pick(STATUS.attention, isDark),
                },
              ]}
            />
          </div>
          <p className="mb-2 text-xs font-medium text-slate-500 dark:text-slate-400">Confidence distribution</p>
          {confidence ? (
            <BreakdownList
              items={confidence.map((c, i) => ({
                key: c.bucket,
                label: c.bucket,
                value: c.count,
                color: sequential[i] ?? sequential[sequential.length - 1],
              }))}
            />
          ) : (
            <p className="py-6 text-center text-sm text-slate-400 dark:text-slate-500">Loading...</p>
          )}
        </Card>

        {/* Unanswered by category */}
        <Card
          title="Unanswered Questions by Category"
          hint="Which topics people ask about that you have no answer for. The longest bars point to the biggest gaps in your knowledge base."
        >
          {categories ? (
            <BreakdownList
              items={categories.slice(0, 8).map((c) => ({
                key: String(c.category_id ?? "uncategorized"),
                label: c.category_name,
                value: c.count,
                color: pick(CATEGORICAL.brand, isDark),
              }))}
              emptyLabel="No unanswered questions in this range"
            />
          ) : (
            <p className="py-6 text-center text-sm text-slate-400 dark:text-slate-500">Loading...</p>
          )}
        </Card>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Content growth */}
        <Card
          title="Content Growth"
          hint="How many knowledge base entries were added each day, coloured by where they came from: typed in by hand, imported, or generated from unanswered questions."
        >
          {contentGrowth ? (
            <StackedBarChart
              data={contentGrowth.map((d) => ({ day: d.day, total: d.total, values: d.by_source }))}
              keys={FAQ_SOURCE_ORDER.map((key) => ({ key, label: sourceLabel(key), color: sourceColor(key) }))}
            />
          ) : (
            <p className="py-10 text-center text-sm text-slate-400 dark:text-slate-500">Loading...</p>
          )}
        </Card>

        {/* FAQ sources */}
        <Card
          title="FAQ Entries by Source"
          hint="Where your knowledge base content came from overall, so you can see how much was written by your team versus imported or AI-assisted."
        >
          {faqSources ? (
            <BreakdownList
              items={faqSources.map((s) => ({
                key: s.source,
                label: sourceLabel(s.source),
                value: s.count,
                color: pick(sourceColor(s.source), isDark),
              }))}
            />
          ) : (
            <p className="py-6 text-center text-sm text-slate-400 dark:text-slate-500">Loading...</p>
          )}
        </Card>
      </div>

      {/* AI engine usage */}
      <div className="mt-4">
        <Card
          title="AI Engine Usage by Model"
          hint="A per-model bill: how many times each AI model was used and what it cost, both today and since the start. Useful for spotting an expensive model."
          action={
            <a href="/admin/settings" className="flex shrink-0 items-center gap-0.5 text-xs font-medium text-sawo-dark hover:underline dark:text-sawo-light">
              API key &amp; model settings
              <ChevronRight size={14} aria-hidden />
            </a>
          }
        >
          <div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-white/10">
            <table className="w-full min-w-[720px] text-sm">
              <thead className="bg-slate-50 text-left text-slate-500 dark:bg-white/5 dark:text-slate-400">
                <tr>
                  <th className="px-4 py-2" rowSpan={2}>
                    Model
                  </th>
                  <th className="border-l border-slate-200 px-4 py-1 text-center dark:border-white/10" colSpan={2}>
                    Today
                  </th>
                  <th className="border-l border-slate-200 px-4 py-1 text-center dark:border-white/10" colSpan={3}>
                    All time
                  </th>
                </tr>
                <tr className="text-xs">
                  <th className="border-l border-slate-200 px-4 py-1 font-normal dark:border-white/10">Requests</th>
                  <th className="px-4 py-1 font-normal">Tokens</th>
                  <th className="border-l border-slate-200 px-4 py-1 font-normal dark:border-white/10">Requests</th>
                  <th className="px-4 py-1 font-normal">Tokens</th>
                  <th className="px-4 py-1 font-normal">Cost</th>
                </tr>
              </thead>
              <tbody>
                {(modelUsage ?? []).map((m) => (
                  <Fragment key={m.model}>
                    <tr
                      onClick={() => toggleModel(m.model)}
                      className="cursor-pointer border-t border-slate-100 hover:bg-slate-50 dark:border-white/10 dark:hover:bg-white/5"
                    >
                      <td className="px-4 py-2">
                        <div className="flex min-w-0 items-center gap-2">
                          <span className="shrink-0 text-slate-400 dark:text-slate-500">{expandedModel === m.model ? "▾" : "▸"}</span>
                          <ModelIcon id={m.model} />
                          <span className="truncate font-medium text-slate-800 dark:text-slate-100" title={m.model}>
                            {m.model}
                          </span>
                          <span
                            className={`shrink-0 rounded px-2 py-0.5 text-xs font-medium ${
                              m.is_free
                                ? "bg-green-50 text-green-700 dark:bg-green-500/15 dark:text-green-300"
                                : "bg-slate-100 text-slate-600 dark:bg-white/10 dark:text-slate-300"
                            }`}
                          >
                            {m.is_free ? "Free" : "Paid"}
                          </span>
                        </div>
                      </td>
                      <td className="border-l border-slate-100 px-4 py-2 dark:border-white/10">{m.requests_today}</td>
                      <td className="px-4 py-2">{m.tokens_today.toLocaleString()}</td>
                      <td className="border-l border-slate-100 px-4 py-2 dark:border-white/10">{m.requests_total}</td>
                      <td className="px-4 py-2">{m.tokens_total.toLocaleString()}</td>
                      <td className="px-4 py-2">{formatCost(m.cost_total_usd)}</td>
                    </tr>
                    {expandedModel === m.model && (
                      <tr key={`${m.model}-detail`} className="border-t border-slate-100 bg-slate-50 dark:border-white/10 dark:bg-white/5">
                        <td colSpan={6} className="px-4 py-3">
                          {m.is_free && (
                            <p className="mb-3 text-xs text-slate-400 dark:text-slate-500">
                              Free OpenRouter models are rate-limited (typically 20 requests/min,
                              200-1000/day) rather than billed — cost is always $0 for this model; token
                              counts below are for tracking that quota.
                            </p>
                          )}
                          {dailyModelLoading && <p className="text-xs text-slate-400 dark:text-slate-500">Loading daily breakdown...</p>}
                          {!dailyModelLoading && dailyModelUsage && dailyModelUsage.length === 0 && (
                            <p className="text-xs text-slate-400 dark:text-slate-500">No usage recorded yet.</p>
                          )}
                          {!dailyModelLoading && dailyModelUsage && dailyModelUsage.length > 0 && (
                            <table className="w-full max-w-md text-xs">
                              <thead className="text-left text-slate-500 dark:text-slate-400">
                                <tr>
                                  <th className="py-1 pr-4 font-normal">Day</th>
                                  <th className="py-1 pr-4 font-normal">Requests</th>
                                  <th className="py-1 pr-4 font-normal">Tokens</th>
                                  <th className="py-1 pr-4 font-normal">Cost</th>
                                </tr>
                              </thead>
                              <tbody>
                                {dailyModelUsage.map((d) => (
                                  <tr key={d.day} className="border-t border-slate-200 dark:border-white/10">
                                    <td className="py-1 pr-4">{d.day}</td>
                                    <td className="py-1 pr-4">{d.requests}</td>
                                    <td className="py-1 pr-4">{d.tokens.toLocaleString()}</td>
                                    <td className="py-1 pr-4">{formatCost(d.cost_usd)}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          )}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
                {modelUsage && modelUsage.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-4 py-6 text-center text-slate-400 dark:text-slate-500">
                      No AI usage recorded yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      {/* Token flow (input vs. output), account-wide by model */}
      <div className="mt-4">
        <Card
          title="Token Flow (Input vs. Output)"
          hint="Tokens are the small pieces of text the AI is billed on. Input is what gets sent to the AI (the question plus your matching content); output is the reply it writes back. Long inputs are the usual reason costs creep up."
        >
          {modelUsage && modelUsage.length > 0 ? (
            <div className="flex flex-col gap-1.5">
              {modelUsage.map((m) => {
                const maxTokens = Math.max(...modelUsage.map((mm) => mm.tokens_total), 1);
                const widthPct = Math.round((m.tokens_total / maxTokens) * 100);
                const inPct = m.tokens_total ? Math.round((m.prompt_tokens_total / m.tokens_total) * 100) : 0;
                return (
                  <div key={m.model} className="flex items-center gap-2">
                    <div className="flex w-40 shrink-0 items-center gap-1.5 truncate text-xs font-medium text-slate-600 dark:text-slate-300" title={m.model}>
                      <ModelIcon id={m.model} size={14} />
                      <span className="truncate">{m.model}</span>
                    </div>
                    <div className="h-4 flex-1 overflow-hidden rounded bg-slate-100 dark:bg-white/10">
                      <div className="flex h-full" style={{ width: `${widthPct}%` }}>
                        <div className="h-full bg-[#2a78d6]" style={{ width: `${inPct}%` }} />
                        <div className="h-full bg-sawo dark:bg-sawo-dark" style={{ width: `${100 - inPct}%` }} />
                      </div>
                    </div>
                    <div className="w-16 shrink-0 text-right text-xs tabular-nums text-slate-500 dark:text-slate-400">
                      {m.tokens_total.toLocaleString()}
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
          ) : (
            <p className="py-6 text-center text-sm text-slate-400 dark:text-slate-500">
              {modelUsage ? "No AI usage recorded yet." : "Loading..."}
            </p>
          )}
        </Card>
      </div>

      {/* Per-call detail, account-wide */}
      <div className="mt-4">
        <Card
          title="Per-Call Detail"
          hint="A line-by-line log of every request sent to the AI, with the time, model, speed and cost. Mostly for digging into one specific slow or expensive answer."
          action={
            <select
              value={callsModelFilter}
              onChange={(e) => {
                setCallsPage(1);
                setCallsModelFilter(e.target.value);
              }}
              className="rounded border border-slate-300 px-2 py-1 text-xs dark:border-white/15 dark:bg-white/5 dark:text-slate-100"
            >
              <option value="">All models</option>
              {(modelUsage ?? []).map((m) => (
                <option key={m.model} value={m.model}>
                  {m.model}
                </option>
              ))}
            </select>
          }
        >
          <div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-white/10">
            <table className="w-full min-w-[760px] text-sm">
              <thead className="bg-slate-50 text-left text-[11px] uppercase tracking-wide text-slate-500 dark:bg-white/5 dark:text-slate-400">
                <tr>
                  <th className="px-3 py-2">Time</th>
                  <th className="px-3 py-2">Model</th>
                  <th className="px-3 py-2">Process</th>
                  <th className="px-3 py-2">Provider</th>
                  <th className="px-3 py-2 text-right">Input</th>
                  <th className="px-3 py-2 text-right">Output</th>
                  <th className="px-3 py-2 text-right">Total</th>
                  <th className="px-3 py-2 text-right">Latency</th>
                  <th className="px-3 py-2">Finish</th>
                  <th className="px-3 py-2 text-right">Cost</th>
                </tr>
              </thead>
              <tbody>
                {(calls?.items ?? []).map((c) => (
                  <tr key={c.id} className="border-t border-slate-100 dark:border-white/10">
                    <td className="px-3 py-2 text-xs text-slate-500 dark:text-slate-400">{formatTime(c.created_at)}</td>
                    <td className="px-3 py-2">
                      <span className="inline-flex items-center gap-1.5 font-medium text-slate-800 dark:text-slate-100">
                        <ModelIcon id={c.model} size={14} /> {c.model}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-xs text-slate-500 dark:text-slate-400">
                      {c.feature ? featureLabel(c.feature) : "—"}
                    </td>
                    <td className="px-3 py-2 text-xs text-slate-500 dark:text-slate-400">{c.provider || "—"}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{c.prompt_tokens.toLocaleString()}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{c.completion_tokens.toLocaleString()}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{c.total_tokens.toLocaleString()}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{fmtMs(c.latency_ms)}</td>
                    <td className="px-3 py-2 text-xs text-slate-500 dark:text-slate-400">{c.finish_reason || "—"}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{formatCost(c.cost_usd)}</td>
                  </tr>
                ))}
                {calls && calls.items.length === 0 && (
                  <tr>
                    <td colSpan={10} className="px-4 py-6 text-center text-slate-400 dark:text-slate-500">
                      No AI calls recorded yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
            {calls && (
              <Pagination page={callsPage} pageSize={callsPageSize} total={calls.total} onPageChange={setCallsPage} />
            )}
          </div>
        </Card>
      </div>

      {/* AI usage by process */}
      <div className="mt-4">
        <Card
          title="AI Usage by Process"
          hint="Which parts of the system are spending your AI budget: answering chats, suggesting answers, tagging content, and so on."
        >
          {featureUsage ? (
            <BreakdownList
              items={featureUsage.map((f) => ({
                key: f.feature,
                label: featureLabel(f.feature),
                value: f.requests_total,
                displayValue: `${f.requests_total.toLocaleString()} req · ${formatCost(f.cost_total_usd)}`,
                color: pick(CATEGORICAL.brand, isDark),
              }))}
              emptyLabel="No AI usage recorded yet"
            />
          ) : (
            <p className="py-6 text-center text-sm text-slate-400 dark:text-slate-500">Loading...</p>
          )}
          <p className="mt-3 text-xs text-slate-400 dark:text-slate-500">
            Cost and requests broken down by which process made the call — crawling/ingestion, live
            chat, FAQ duplicate checks, reindexing, and search.
          </p>
        </Card>
      </div>
    </div>
  );
}
