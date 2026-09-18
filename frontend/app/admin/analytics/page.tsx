"use client";

import { Fragment, useEffect, useState } from "react";
import { apiGet } from "@/lib/api";
import { useIsDark } from "@/lib/useIsDark";
import { CATEGORICAL, SEQUENTIAL_DARK, SEQUENTIAL_LIGHT, STATUS, pick, sourceColor, sourceLabel } from "@/components/admin/analytics/colors";
import { BreakdownList, Card, MetricCard, RangeTabs } from "@/components/admin/analytics/StatPrimitives";
import TrendChart from "@/components/admin/analytics/TrendChart";
import StackedBarChart from "@/components/admin/analytics/StackedBarChart";
import { ModelIcon } from "@/lib/modelProviders";

interface OverviewStats {
  chats_today: number;
  chats_7d: number;
  chats_30d: number;
  unique_sessions_7d: number;
  answered_rate_7d: number;
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
  cost_total_usd: number;
  requests_today: number;
  tokens_today: number;
  cost_today_usd: number;
  last_used_at: string | null;
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

function formatCost(usd: number): string {
  if (usd === 0) return "$0.00";
  if (usd < 0.0001) return "<$0.0001";
  if (usd < 0.01) return `$${usd.toFixed(4)}`;
  return `$${usd.toFixed(2)}`;
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

  function loadModelUsage() {
    apiGet<ModelUsage[]>("/api/usage/models").then(setModelUsage);
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
    loadModelUsage();
    const interval = setInterval(loadModelUsage, 30000);
    return () => clearInterval(interval);
  }, []);

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

  return (
    <div>
      <div className="mb-6 flex items-center justify-between gap-3">
        <h1 className="text-xl font-semibold text-slate-800 dark:text-slate-100">Analytics</h1>
        <RangeTabs value={days} onChange={setDays} />
      </div>

      {/* Core metrics */}
      <div className="mb-4 grid grid-cols-2 gap-4 md:grid-cols-4">
        <MetricCard label="Chats (7d)" value={overview ? overview.chats_7d.toLocaleString() : "..."} subtitle={overview ? `${overview.chats_today} today` : undefined} />
        <MetricCard
          label="Answered Rate (7d)"
          value={overview ? `${overview.answered_rate_7d}%` : "..."}
          subtitle="Matched real FAQ/Library content"
        />
        <MetricCard label="Unanswered Pending" value={overview ? overview.unanswered_pending.toLocaleString() : "..."} subtitle="Awaiting agent review" />
        <MetricCard label="Unique Sessions (7d)" value={overview ? overview.unique_sessions_7d.toLocaleString() : "..."} />
      </div>

      {/* AI engine metrics */}
      <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
        <MetricCard
          label="Active Model"
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
        />
        <MetricCard label="AI Cost Today" value={overview ? formatCost(overview.ai_cost_today_usd) : "..."} />
        <MetricCard label="AI Cost (30d)" value={overview ? formatCost(overview.ai_cost_30d_usd) : "..."} />
        <MetricCard label="FAQ Entries" value={overview ? overview.faq_total.toLocaleString() : "..."} subtitle={overview ? `${overview.faq_published} published` : undefined} />
      </div>

      {/* Chat volume trend */}
      <Card title="Chat Volume">
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
        <Card title="Answer Quality">
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
        <Card title="Unanswered Questions by Category">
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
        <Card title="Content Growth">
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
        <Card title="FAQ Entries by Source">
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
          action={
            <a href="/admin/settings" className="text-xs font-medium text-sawo-dark hover:underline dark:text-sawo-light">
              API key &amp; model settings →
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

      {/* AI usage by process */}
      <div className="mt-4">
        <Card title="AI Usage by Process">
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
