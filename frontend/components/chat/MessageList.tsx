"use client";

import { useEffect, useRef } from "react";
import MessageBubble, { ChatMessage } from "./MessageBubble";

export default function MessageList({ messages, loading }: { messages: ChatMessage[]; loading: boolean }) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  return (
    <div className="flex flex-1 flex-col gap-3 overflow-y-auto px-4 py-6">
      {messages.length === 0 && (
        <div className="m-auto text-center text-slate-400">
          <p className="text-lg font-medium">How can we help you today?</p>
          <p className="text-sm">Ask a question and we&apos;ll find the answer from our knowledge base.</p>
        </div>
      )}

      {messages.map((message, idx) => (
        <MessageBubble key={idx} message={message} />
      ))}

      {loading && (
        <div className="flex justify-start">
          <div className="flex items-center gap-1 rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
            <span className="h-2 w-2 animate-bounce rounded-full bg-slate-400 [animation-delay:-0.3s]" />
            <span className="h-2 w-2 animate-bounce rounded-full bg-slate-400 [animation-delay:-0.15s]" />
            <span className="h-2 w-2 animate-bounce rounded-full bg-slate-400" />
          </div>
        </div>
      )}

      <div ref={endRef} />
    </div>
  );
}
