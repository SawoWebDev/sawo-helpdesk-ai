"use client";

import { useState } from "react";
import { Check, Copy, ExternalLink, ThumbsDown, ThumbsUp } from "lucide-react";
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
  lowConfidence?: boolean;
}

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
}: {
  message: ChatMessage;
  onCopy?: (text: string) => void;
  onFeedback?: (chatLogId: number, rating: "up" | "down") => void;
}) {
  const isUser = message.role === "user";
  const [copied, setCopied] = useState(false);

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
