"use client";

import { useState } from "react";
import { Check, Copy } from "lucide-react";
import ReactMarkdown from "react-markdown";
import BotAvatar from "./BotAvatar";

export interface ChatMessage {
  role: "user" | "assistant";
  text: string;
  isFallback?: boolean;
  imageUrls?: string[];
  referenceUrls?: string[];
  time?: string;
}

export default function MessageBubble({ message, onCopy }: { message: ChatMessage; onCopy?: (text: string) => void }) {
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
          <div
            className={`prose prose-sm max-w-none prose-p:my-1 prose-a:font-semibold prose-a:no-underline prose-a:underline-offset-2 hover:prose-a:underline ${
              isUser ? "prose-invert prose-a:text-white" : "prose-a:text-sawo dark:prose-invert dark:prose-a:text-sawo-light"
            }`}
          >
            <ReactMarkdown>{message.text}</ReactMarkdown>
          </div>

          {message.imageUrls && message.imageUrls.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-2">
              {message.imageUrls.map((url) => (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  key={url}
                  src={url}
                  alt="Reference"
                  className="max-h-40 rounded-lg border border-slate-200 object-cover dark:border-white/15"
                />
              ))}
            </div>
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
          </span>
        )}
      </div>
    </div>
  );
}
