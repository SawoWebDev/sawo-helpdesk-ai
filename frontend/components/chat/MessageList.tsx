"use client";

import { useEffect, useRef } from "react";
import MessageBubble, { ChatMessage } from "./MessageBubble";
import WelcomeCards from "./WelcomeCards";
import BotAvatar from "./BotAvatar";

export default function MessageList({
  messages,
  loading,
  onSelectSuggestion,
  onCopyMessage,
}: {
  messages: ChatMessage[];
  loading: boolean;
  onSelectSuggestion: (text: string) => void;
  onCopyMessage?: (text: string) => void;
}) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  return (
    <div className="relative z-10 flex flex-1 flex-col overflow-y-auto bg-sawo-bg dark:bg-transparent">
      <div className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-3 px-4 py-6">
        {messages.length === 0 && (
          <div className="m-auto">
            <WelcomeCards onSelect={onSelectSuggestion} disabled={loading} />
          </div>
        )}

        {messages.map((message, idx) => (
          <MessageBubble key={idx} message={message} onCopy={onCopyMessage} />
        ))}

        {loading && (
          <div className="flex items-start gap-2">
            <BotAvatar />
            <div
              role="status"
              aria-label="Assistant is typing"
              className="glass glass-soft glass-edge glass-edge-soft relative flex h-10 items-center gap-1.5 rounded-2xl rounded-tl-[4px] border border-transparent bg-white px-4 pt-2 shadow-sm"
            >
              {[0, 160, 320].map((delay) => (
                <span
                  key={delay}
                  style={{ animationDelay: `${delay}ms` }}
                  className="typing-dot h-2 w-2 rounded-full bg-sawo-dark dark:bg-white/90 dark:shadow-[0_0_8px_rgba(255,255,255,0.45)]"
                />
              ))}
            </div>
          </div>
        )}

        <div ref={endRef} />
      </div>
    </div>
  );
}
