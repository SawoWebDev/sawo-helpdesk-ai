"use client";

import { useState } from "react";
import { Check, Copy, ExternalLink, Flag, ThumbsDown, ThumbsUp } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { markdownLinkComponent } from "@/lib/markdownLink";
import { splitMarkdownTables } from "@/lib/splitMarkdownTables";
import { humanizeSourceUrl } from "@/lib/urlLabel";
import BotAvatar from "./BotAvatar";
import ChatTable from "./ChatTable";

export interface ChatMessage {
  role: "user" | "assistant";
  text: string;
  isFallback?: boolean;
  imageUrls?: string[];
  referenceUrls?: string[];
  time?: string;
  chatLogId?: number;
  rating?: "up" | "down";
  feedbackReason?: string;
  lowConfidence?: boolean;
}

export const FEEDBACK_REASONS: { value: string; label: string }[] = [
  { value: "incorrect_information", label: "Incorrect information" },
  { value: "outdated_information", label: "Outdated information" },
  { value: "did_not_answer", label: "Did not answer my question" },
  { value: "wrong_product_or_model", label: "Wrong product or model" },
  { value: "other", label: "Other" },
];

/** Markdown for one text block of a message, rendered inside a bubble.
 *  Tables are handled separately by ChatTable; the prose-table rules here are
 *  only a fallback for a table the splitter deliberately leaves in place,
 *  such as one inside a fenced code block. */
function MessageMarkdown({ text, isUser }: { text: string; isUser: boolean }) {
  return (
    <div className="prose prose-sm max-w-none text-inherit [&_*:not(a)]:text-inherit prose-p:my-1 prose-table:my-2 prose-th:px-3 prose-th:py-1 prose-td:px-3 prose-td:py-1">
      {/* Spec/technical-data tables come back from the model as GFM pipe
          tables, which react-markdown only understands with remark-gfm;
          without it they rendered as one long run of literal "|" text. */}
      <div className="overflow-x-auto">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            a: markdownLinkComponent(
              `font-semibold underline underline-offset-2 ${isUser ? "text-white" : "text-sawo-dark dark:text-sawo-light"}`
            ),
          }}
        >
          {text}
        </ReactMarkdown>
      </div>
    </div>
  );
}

export default function MessageBubble({
  message,
  onCopy,
  onFeedback,
  onReport,
}: {
  message: ChatMessage;
  onCopy?: (text: string) => void;
  onFeedback?: (chatLogId: number, rating: "up" | "down", reason?: string) => void;
  onReport?: (chatLogId: number, reason: string | undefined, comment: string | undefined) => Promise<boolean>;
}) {
  const isUser = message.role === "user";
  const [copied, setCopied] = useState(false);
  // Shown right after picking "Not helpful", so a reason is easy to add but
  // never required. Dismissed once a reason is chosen, or manually skipped.
  const [reasonPickerOpen, setReasonPickerOpen] = useState(false);
  const [reportOpen, setReportOpen] = useState(false);
  const [reportReason, setReportReason] = useState<string | undefined>(undefined);
  const [reportComment, setReportComment] = useState("");
  const [reportState, setReportState] = useState<"idle" | "sending" | "sent" | "error">("idle");

  // Tables are lifted out of the bubble and rendered as their own full-width
  // card, in place. User messages are left alone — they are plain text.
  const blocks = isUser ? null : splitMarkdownTables(message.text);
  const hasTable = !!blocks?.some((b) => b.type === "table");

  const bubbleTone = isUser
    ? "glass glass-user glass-soft glass-edge glass-edge-soft relative border border-transparent bg-gradient-to-br from-sawo-light to-sawo-dark font-medium text-white"
    : message.isFallback
      ? "border border-amber-200 bg-amber-50 font-medium text-amber-900 dark:border-amber-300/25 dark:bg-amber-400/10 dark:text-amber-100 dark:backdrop-blur-xl"
      : // Light mode: white on the #faf8f5 page is too close to see, so the bubble
        // gets a warm border + shadow. Dark mode keeps the transparent glass edge.
        "glass glass-soft glass-edge glass-edge-soft relative border border-sawo-border bg-white font-medium text-[#2a2420] shadow-[0_2px_8px_rgba(139,105,71,0.10)] dark:border-transparent dark:text-slate-100 dark:shadow-sm";

  // Only the first bubble of a message gets the pointed tail corner, so a
  // reply split around a table still reads as one message.
  function bubbleClass(withTail: boolean) {
    const tail = withTail ? (isUser ? "rounded-tr-[4px]" : "rounded-tl-[4px]") : "";
    return `rounded-2xl ${tail} px-3.5 py-2.5 text-[13px] leading-relaxed ${isUser || message.isFallback ? "shadow-sm" : ""} ${bubbleTone}`;
  }

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(message.text);
    } catch {
      return;
    }
    setCopied(true);
    onCopy?.(message.text);
    setTimeout(() => setCopied(false), 1500);
  }

  function handleThumb(rating: "up" | "down") {
    if (message.chatLogId == null) return;
    if (rating === "down") {
      setReasonPickerOpen(true);
      onFeedback?.(message.chatLogId, rating);
    } else {
      setReasonPickerOpen(false);
      onFeedback?.(message.chatLogId, rating);
    }
  }

  function handlePickReason(reason: string) {
    if (message.chatLogId == null) return;
    onFeedback?.(message.chatLogId, "down", reason);
    setReasonPickerOpen(false);
  }

  async function handleSubmitReport() {
    if (message.chatLogId == null || !onReport) return;
    setReportState("sending");
    const ok = await onReport(message.chatLogId, reportReason, reportComment.trim() || undefined);
    setReportState(ok ? "sent" : "error");
    if (ok) {
      setTimeout(() => {
        setReportOpen(false);
        setReportState("idle");
        setReportReason(undefined);
        setReportComment("");
      }, 1200);
    }
  }

  return (
    <div className={`flex items-start gap-2 ${isUser ? "flex-row-reverse" : "flex-row"}`}>
      {isUser ? (
        <div className="glass glass-3d glass-edge relative flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-transparent bg-gradient-to-br from-sawo-light to-sawo-dark text-[10px] font-bold text-white">
          You
        </div>
      ) : (
        <BotAvatar />
      )}

      <div className={`flex min-w-0 flex-col ${hasTable ? "w-full" : "max-w-[80%]"} ${isUser ? "items-end" : "items-start"}`}>
        {(() => {
          // Images, the low-confidence note and reference links always belong
          // to the end of the reply, so they ride in the last bubble.
          const extras = (
            <>
              {message.imageUrls && message.imageUrls.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-2">
                  {message.imageUrls.map((url) => (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      key={url}
                      src={url}
                      alt="Reference"
                      className="max-h-40 max-w-full rounded-lg border border-slate-200 object-contain dark:border-white/15"
                    />
                  ))}
                </div>
              )}

              {message.lowConfidence && !message.isFallback && (
                <p className="mt-2 text-[11px] italic text-slate-400 dark:text-slate-500">
                  This answer may be incomplete, so rate it below if it wasn&apos;t quite right.
                </p>
              )}

              {message.referenceUrls && message.referenceUrls.length > 0 && (
                <div className="mt-2 flex flex-col gap-1 border-t border-black/5 pt-2 dark:border-white/10">
                  <p
                    className={`text-[10px] font-semibold uppercase tracking-wide ${
                      isUser ? "text-white/70" : "text-slate-400 dark:text-slate-500"
                    }`}
                  >
                    Sources
                  </p>
                  {message.referenceUrls.map((url) => (
                    <a
                      key={url}
                      href={url}
                      target="_blank"
                      rel="noopener noreferrer"
                      title={url}
                      className={`flex min-w-0 items-center gap-1 text-xs font-semibold underline underline-offset-2 ${
                        isUser ? "text-white" : "text-sawo dark:text-sawo-light"
                      }`}
                    >
                      <ExternalLink size={11} className="shrink-0" strokeWidth={2.25} aria-hidden />
                      <span className="truncate">{humanizeSourceUrl(url)}</span>
                    </a>
                  ))}
                </div>
              )}
            </>
          );

          const hasExtras =
            (message.imageUrls?.length ?? 0) > 0 ||
            (message.referenceUrls?.length ?? 0) > 0 ||
            (!!message.lowConfidence && !message.isFallback);

          if (!hasTable || !blocks) {
            return (
              <div className={bubbleClass(true)}>
                <MessageMarkdown text={message.text} isUser={isUser} />
                {extras}
              </div>
            );
          }

          // A reply containing a table becomes a column of bubbles with the
          // table cards sitting between them at the full width of the thread.
          const lastTextIndex = blocks.map((b) => b.type).lastIndexOf("text");
          return (
            <div className="flex w-full flex-col items-start gap-2">
              {blocks.map((block, i) =>
                block.type === "table" ? (
                  <ChatTable key={i} markdown={block.content} />
                ) : (
                  <div key={i} className={`max-w-[80%] ${bubbleClass(i === 0)}`}>
                    <MessageMarkdown text={block.content} isUser={isUser} />
                    {i === lastTextIndex && extras}
                  </div>
                )
              )}
              {lastTextIndex === -1 && hasExtras && <div className={`max-w-[80%] ${bubbleClass(false)}`}>{extras}</div>}
            </div>
          );
        })()}
        {(message.time || !isUser) && (
          <span className="mt-1 flex items-center gap-1.5 px-1">
            {message.time && <span className="text-[10px] text-slate-400 dark:text-slate-500">{message.time}</span>}
            {!isUser && (
              <button
                type="button"
                onClick={handleCopy}
                aria-label="Copy response"
                title="Copy response"
                className="flex h-4 w-4 items-center justify-center text-slate-400 transition-colors hover:text-sawo dark:text-slate-500 dark:hover:text-sawo-light"
              >
                {copied ? <Check size={12} strokeWidth={2.25} /> : <Copy size={12} strokeWidth={2.25} />}
              </button>
            )}
            {!isUser && message.chatLogId != null && (
              <>
                <button
                  type="button"
                  onClick={() => handleThumb("up")}
                  aria-label="Helpful"
                  title="Helpful"
                  className={`flex h-4 w-4 items-center justify-center transition-colors ${
                    message.rating === "up"
                      ? "text-sawo dark:text-sawo-light"
                      : "text-slate-400 hover:text-sawo dark:text-slate-500 dark:hover:text-sawo-light"
                  }`}
                >
                  <ThumbsUp size={12} strokeWidth={2.25} fill={message.rating === "up" ? "currentColor" : "none"} />
                </button>
                <button
                  type="button"
                  onClick={() => handleThumb("down")}
                  aria-label="Not helpful"
                  title="Not helpful"
                  className={`flex h-4 w-4 items-center justify-center transition-colors ${
                    message.rating === "down"
                      ? "text-amber-600 dark:text-amber-400"
                      : "text-slate-400 hover:text-amber-600 dark:text-slate-500 dark:hover:text-amber-400"
                  }`}
                >
                  <ThumbsDown
                    size={12}
                    strokeWidth={2.25}
                    fill={message.rating === "down" ? "currentColor" : "none"}
                  />
                </button>
                {onReport && (
                  <button
                    type="button"
                    onClick={() => setReportOpen((v) => !v)}
                    aria-label="Report a problem with this answer"
                    title="Report a problem"
                    className={`flex h-4 w-4 items-center justify-center transition-colors ${
                      reportOpen
                        ? "text-red-500 dark:text-red-400"
                        : "text-slate-400 hover:text-red-500 dark:text-slate-500 dark:hover:text-red-400"
                    }`}
                  >
                    <Flag size={12} strokeWidth={2.25} />
                  </button>
                )}
              </>
            )}
          </span>
        )}

        {!isUser && reasonPickerOpen && message.rating === "down" && (
          <div className="mt-1.5 flex max-w-[80%] flex-wrap items-center gap-1.5 px-1">
            <span className="text-[10px] text-slate-400 dark:text-slate-500">What went wrong?</span>
            {FEEDBACK_REASONS.map((r) => (
              <button
                key={r.value}
                type="button"
                onClick={() => handlePickReason(r.value)}
                className={`rounded-full border px-2 py-0.5 text-[10px] font-medium transition-colors ${
                  message.feedbackReason === r.value
                    ? "border-amber-500 bg-amber-50 text-amber-700 dark:border-amber-400/50 dark:bg-amber-400/10 dark:text-amber-300"
                    : "border-slate-200 text-slate-500 hover:border-amber-400 hover:text-amber-600 dark:border-white/15 dark:text-slate-400 dark:hover:border-amber-400/50 dark:hover:text-amber-300"
                }`}
              >
                {r.label}
              </button>
            ))}
            <button
              type="button"
              onClick={() => setReasonPickerOpen(false)}
              className="text-[10px] text-slate-400 underline underline-offset-2 hover:text-slate-500 dark:text-slate-500"
            >
              Skip
            </button>
          </div>
        )}

        {!isUser && reportOpen && (
          <div className="mt-1.5 flex w-full max-w-[85%] flex-col gap-1.5 rounded-xl border border-slate-200 bg-white p-2.5 text-[11px] shadow-sm dark:border-white/10 dark:bg-white/[0.04]">
            {reportState === "sent" ? (
              <p className="text-emerald-600 dark:text-emerald-400">Thanks — your report was sent.</p>
            ) : (
              <>
                <p className="font-semibold text-slate-600 dark:text-slate-300">Report a problem with this answer</p>
                <select
                  value={reportReason ?? ""}
                  onChange={(e) => setReportReason(e.target.value || undefined)}
                  aria-label="Reason"
                  className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-[11px] text-slate-600 dark:border-white/15 dark:bg-transparent dark:text-slate-300"
                >
                  <option value="">Select a reason (optional)</option>
                  {FEEDBACK_REASONS.map((r) => (
                    <option key={r.value} value={r.value}>
                      {r.label}
                    </option>
                  ))}
                </select>
                <textarea
                  value={reportComment}
                  onChange={(e) => setReportComment(e.target.value)}
                  placeholder="Add any details that would help (optional)"
                  rows={2}
                  aria-label="Additional comment"
                  className="resize-none rounded-lg border border-slate-200 bg-white px-2 py-1 text-[11px] text-slate-600 placeholder:text-slate-400 dark:border-white/15 dark:bg-transparent dark:text-slate-300"
                />
                {reportState === "error" && (
                  <p className="text-red-500 dark:text-red-400">Couldn&apos;t send the report, please try again.</p>
                )}
                <div className="flex items-center justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => setReportOpen(false)}
                    className="text-slate-400 hover:text-slate-500 dark:text-slate-500"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={handleSubmitReport}
                    disabled={reportState === "sending"}
                    className="rounded-full bg-sawo px-3 py-1 font-semibold text-white disabled:opacity-60 dark:bg-sawo-light"
                  >
                    {reportState === "sending" ? "Sending…" : "Submit report"}
                  </button>
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
