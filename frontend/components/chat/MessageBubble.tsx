"use client";

import { useState } from "react";
import { Check, Copy, ThumbsDown, ThumbsUp } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { markdownLinkComponent } from "@/lib/markdownLink";
import BotAvatar from "./BotAvatar";

export interface ChatMessage {
  role: "user" | "assistant";
  text: string;
  isFallback?: boolean;
  imageUrls?: string[];
  referenceUrls?: string[];
  time?: string;
  chatLogId?: number;
  rating?: "up" | "down";
  lowConfidence?: boolean;
}

export default function MessageBubble({
  message,
  onCopy,
  onFeedback,
}: {
  message: ChatMessage;
  onCopy?: (text: string) => void;
  onFeedback?: (chatLogId: number, rating: "up" | "down") => void;
}) {
  const isUser = message.role === "user";
  const [copied, setCopied] = useState(false);

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

  return (
    <div className={`flex items-start gap-2 ${isUser ? "flex-row-reverse" : "flex-row"}`}>
      {isUser ? (
        <div className="glass glass-3d glass-edge relative flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-transparent bg-gradient-to-br from-sawo-light to-sawo-dark text-[10px] font-bold text-white">
          You
        </div>
      ) : (
        <BotAvatar />
      )}

      <div className={`flex max-w-[80%] flex-col ${isUser ? "items-end" : "items-start"}`}>
        <div
          className={`rounded-2xl px-3.5 py-2.5 text-[13px] leading-relaxed shadow-sm ${
            isUser
              ? "glass glass-user glass-soft glass-edge glass-edge-soft relative rounded-tr-[4px] border border-transparent bg-gradient-to-br from-sawo-light to-sawo-dark font-medium text-white"
              : message.isFallback
                ? "rounded-tl-[4px] border border-amber-200 bg-amber-50 font-medium text-amber-900 dark:border-amber-300/25 dark:bg-amber-400/10 dark:text-amber-100 dark:backdrop-blur-xl"
                : "glass glass-soft glass-edge glass-edge-soft relative rounded-tl-[4px] border border-transparent bg-white font-medium text-[#2a2420] dark:text-slate-100"
          }`}
        >
          <div className="prose prose-sm max-w-none text-inherit [&_*:not(a)]:text-inherit prose-p:my-1 prose-table:my-2 prose-th:px-2 prose-th:py-1 prose-th:text-left prose-td:px-2 prose-td:py-1">
            {/* Spec/technical-data tables come back from the model as GFM pipe
                tables — react-markdown only speaks CommonMark by default, so
                without remark-gfm these rendered as one long run of literal
                "|" text instead of an actual table. The overflow wrapper lets
                a wide spec table scroll horizontally instead of blowing out
                the chat bubble's width. */}
            <div className="overflow-x-auto">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  a: markdownLinkComponent(
                    `font-semibold underline underline-offset-2 ${
                      isUser ? "text-white" : "text-sawo-dark dark:text-sawo-light"
                    }`
                  ),
                }}
              >
                {message.text}
              </ReactMarkdown>
            </div>
          </div>

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
              This answer may be incomplete — rate it below if it wasn&apos;t quite right.
            </p>
          )}

          {message.referenceUrls && message.referenceUrls.length > 0 && (
            <div className="mt-2 flex flex-col gap-1">
              {message.referenceUrls.map((url) => (
                <a
                  key={url}
                  href={url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={`break-all text-xs font-semibold underline underline-offset-2 ${
                    isUser ? "text-white" : "text-sawo dark:text-sawo-light"
                  }`}
                >
                  {url}
                </a>
              ))}
            </div>
          )}
        </div>
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
                  onClick={() => onFeedback?.(message.chatLogId!, "up")}
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
                  onClick={() => onFeedback?.(message.chatLogId!, "down")}
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
              </>
            )}
          </span>
        )}
      </div>
    </div>
  );
}
