"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiGet } from "@/lib/api";
import { CATEGORICAL } from "@/components/admin/analytics/colors";
import { Card, MetricCard } from "@/components/admin/analytics/StatPrimitives";
import TrendChart from "@/components/admin/analytics/TrendChart";
import { ModelIcon } from "@/lib/modelProviders";

interface Paginated<T = unknown> {
  items: T[];
  total: number;
}

interface HourlyActivity {
  hour: string; // "00".."23", UTC
  messages: number;
  cost_usd: number;
}

interface DailyUsage {
  day: string;
  requests: number;
  tokens: number;
  cost_usd: number;
}

interface OverviewStats {
  chats_today: number;
  answered_rate_7d: number;
  active_model: string;
  active_model_is_free: boolean;
}

interface UnansweredQuestion {
  id: number;
  question_text: string;
  confidence_score: number | null;
  created_at: string;
}

// "2026-09-17T10:32:00Z" -> "2h ago" / "3d ago", so the recent-questions list
// reads at a glance without admins needing to parse a timestamp.
function timeAgo(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diffMs / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function formatCost(usd: number): string {
  if (usd === 0) return "$0.00";
  if (usd < 0.0001) return "<$0.0001";
  if (usd < 0.01) return `$${usd.toFixed(4)}`;
  return `$${usd.toFixed(2)}`;
}

// "00".."23" (UTC) -> "12 AM".."11 PM", matching the hour buckets the
// hourly-activity endpoint returns.
function formatHourLabel(hour: string): string {
  const h = Number(hour);
  const period = h < 12 ? "AM" : "PM";
  const h12 = h % 12 === 0 ? 12 : h % 12;
  return `${h12} ${period}`;
}

function ViewAnalyticsLink() {
  return (
    <Link href="/admin/analytics" className="text-xs font-medium text-sawo-dark hover:underline dark:text-sawo-light">
      View full analytics →
    </Link>
  );
}

export default function DashboardPage() {
  const [faqCount, setFaqCount] = useState<number | null>(null);
  const [pendingCount, setPendingCount] = useState<number | null>(null);
  const [hourly, setHourly] = useState<HourlyActivity[] | null>(null);
  const [dailySpend, setDailySpend] = useState<DailyUsage[] | null>(null);
  const [overview, setOverview] = useState<OverviewStats | null>(null);
  const [recentUnanswered, setRecentUnanswered] = useState<UnansweredQuestion[] | null>(null);

  useEffect(() => {
    apiGet<Paginated>("/api/faqs?page=1&page_size=1").then((r) => setFaqCount(r.total));
    apiGet<Paginated>("/api/unanswered?page=1&page_size=1&status=pending").then((r) =>
      setPendingCount(r.total)
    );
    apiGet<HourlyActivity[]>("/api/analytics/hourly-activity?days=30").then(setHourly);
    apiGet<DailyUsage[]>("/api/analytics/daily-spend?days=30").then(setDailySpend);
    apiGet<OverviewStats>("/api/analytics/overview").then(setOverview);
    apiGet<Paginated<UnansweredQuestion>>("/api/unanswered?page=1&page_size=5&status=pending").then((r) =>
      setRecentUnanswered(r.items)
    );
  }, []);

  const totalSpend30d = dailySpend?.reduce((sum, d) => sum + d.cost_usd, 0) ?? 0;
  const peakHour = hourly?.length ? hourly.reduce((a, b) => (b.messages > a.messages ? b : a)) : null;

  return (
    <div>
      <h1 className="mb-6 text-xl font-semibold text-slate-800 dark:text-slate-100">Dashboard</h1>

      <div className="mb-4 grid grid-cols-2 gap-4">
        <Link
          href="/admin/faqs"
          className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm hover:border-sawo/40 dark:border-white/10 dark:bg-night-surface dark:hover:border-sawo-light/50"
        >
          <p className="text-sm text-slate-500 dark:text-slate-400">Knowledge Base Entries</p>
          <p className="mt-1 text-3xl font-semibold text-slate-800 dark:text-slate-100">{faqCount ?? "..."}</p>
        </Link>
        <Link
          href="/admin/unanswered"
          className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm hover:border-sawo/40 dark:border-white/10 dark:bg-night-surface dark:hover:border-sawo-light/50"
        >
          <p className="text-sm text-slate-500 dark:text-slate-400">Pending Unanswered Questions</p>
          <p className="mt-1 text-3xl font-semibold text-slate-800 dark:text-slate-100">{pendingCount ?? "..."}</p>
        </Link>
      </div>

      <div className="mb-4 grid grid-cols-2 gap-4 md:grid-cols-3">
        <MetricCard label="Chats Today" value={overview ? overview.chats_today.toLocaleString() : "..."} />
        <MetricCard
          label="Answered Rate (7d)"
          value={overview ? `${overview.answered_rate_7d}%` : "..."}
          subtitle="Matched real FAQ/Library content"
        />
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
      </div>

      <div className="mb-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card
          title="Peak Hours"
          action={<ViewAnalyticsLink />}
        >
          {hourly ? (
            <>
              <TrendChart
                data={hourly.map((h) => ({ day: h.hour, values: { messages: h.messages } }))}
                series={[{ key: "messages", label: "Messages", color: CATEGORICAL.brand }]}
                formatX={formatHourLabel}
              />
              {peakHour && peakHour.messages > 0 && (
                <p className="mt-2 text-xs text-slate-400 dark:text-slate-500">
                  Busiest hour (last 30 days, UTC): <b className="text-slate-600 dark:text-slate-300">{formatHourLabel(peakHour.hour)}</b> with{" "}
                  {peakHour.messages.toLocaleString()} messages.
                </p>
              )}
            </>
          ) : (
            <p className="py-10 text-center text-sm text-slate-400 dark:text-slate-500">Loading...</p>
          )}
        </Card>

        <Card
          title="Daily AI Spend"
          action={<ViewAnalyticsLink />}
        >
          {dailySpend ? (
            <>
              <TrendChart
                data={dailySpend.map((d) => ({ day: d.day, values: { cost: d.cost_usd } }))}
                series={[{ key: "cost", label: "Cost", color: CATEGORICAL.blue }]}
                formatValue={formatCost}
              />
              <p className="mt-2 text-xs text-slate-400 dark:text-slate-500">
                Total spend, last 30 days: <b className="text-slate-600 dark:text-slate-300">{formatCost(totalSpend30d)}</b>.
              </p>
            </>
          ) : (
            <p className="py-10 text-center text-sm text-slate-400 dark:text-slate-500">Loading...</p>
          )}
        </Card>
      </div>

      <div className="mt-4">
        <Card
          title="Recent Unanswered Questions"
          action={
            <Link href="/admin/unanswered" className="text-xs font-medium text-sawo-dark hover:underline dark:text-sawo-light">
              Review all →
            </Link>
          }
        >
          {recentUnanswered ? (
            recentUnanswered.length > 0 ? (
              <ul className="divide-y divide-slate-100 dark:divide-white/10">
                {recentUnanswered.map((q) => (
                  <li key={q.id} className="flex items-start justify-between gap-3 py-2 text-sm">
                    <span className="min-w-0 truncate text-slate-700 dark:text-slate-200">{q.question_text}</span>
                    <span className="shrink-0 text-xs text-slate-400 dark:text-slate-500">{timeAgo(q.created_at)}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="py-6 text-center text-sm text-slate-400 dark:text-slate-500">
                No pending unanswered questions.
              </p>
            )
          ) : (
            <p className="py-6 text-center text-sm text-slate-400 dark:text-slate-500">Loading...</p>
          )}
        </Card>
      </div>
    </div>
  );
}
