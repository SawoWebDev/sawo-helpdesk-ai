"use client";

import { useEffect, useState } from "react";
import { apiGet } from "@/lib/api";
import { useIsDark } from "@/lib/useIsDark";
import { CATEGORICAL, SEQUENTIAL_DARK, SEQUENTIAL_LIGHT, STATUS, pick, sourceColor, sourceLabel } from "@/components/admin/analytics/colors";
import { BreakdownList, Card, MetricCard, RangeTabs } from "@/components/admin/analytics/StatPrimitives";
import TrendChart from "@/components/admin/analytics/TrendChart";
import StackedBarChart from "@/components/admin/analytics/StackedBarChart";

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

function formatCost(usd: number): string {
  if (usd === 0) return "$0.00";
  if (usd < 0.0001) return "<$0.0001";
  if (usd < 0.01) return `$${usd.toFixed(4)}`;
  return `$${usd.toFixed(2)}`;
}

const FAQ_SOURCE_ORDER = ["manual", "chat_log", "chat_auto", "import"];

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

  useEffect(() => {
    apiGet<OverviewStats>("/api/analytics/overview").then(setOverview);
    apiGet<SourceBreakdown[]>("/api/analytics/faq-sources").then(setFaqSources);
    apiGet<ModelUsage[]>("/api/usage/models").then(setModelUsage);
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
          value={overview ? <span className="truncate text-base" title={overview.active_model}>{overview.active_model || "—"}</span> : "..."}
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
        <Card title="AI Engine Usage by Model">
          {modelUsage ? (
            <BreakdownList
              items={modelUsage.map((m) => ({
                key: m.model,
                label: m.model,
                value: m.requests_total,
                displayValue: `${m.requests_total.toLocaleString()} req · ${formatCost(m.cost_total_usd)}`,
                color: pick(CATEGORICAL.brand, isDark),
              }))}
              emptyLabel="No AI usage recorded yet"
            />
          ) : (
            <p className="py-6 text-center text-sm text-slate-400 dark:text-slate-500">Loading...</p>
          )}
          <p className="mt-3 text-xs text-slate-400 dark:text-slate-500">
            Full per-model daily breakdown and API key management live in{" "}
            <a href="/admin/settings" className="font-medium text-sawo-dark hover:underline dark:text-sawo-light">
              Settings
            </a>
            .
          </p>
        </Card>
      </div>
    </div>
  );
}
