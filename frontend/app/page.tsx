"use client";

import { useState } from "react";
import ChatInput from "@/components/chat/ChatInput";
import MessageList from "@/components/chat/MessageList";
import ThemeToggle from "@/components/chat/ThemeToggle";
import DarkBackdrop from "@/components/chat/DarkBackdrop";
import { ChatMessage } from "@/components/chat/MessageBubble";
import { apiPost } from "@/lib/api";
import { getOrCreateSessionId } from "@/lib/session";

interface ChatResponse {
  answer: string;
  is_fallback: boolean;
  confidence_score: number | null;
  matched_faq_ids: number[];
  image_urls: string[];
  reference_urls: string[];
}

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);

  function getTime() {
    return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  async function handleSend(text: string) {
    setMessages((prev) => [...prev, { role: "user", text, time: getTime() }]);
    setLoading(true);
    try {
      const res = await apiPost<ChatResponse>("/api/chat", {
        question: text,
        session_id: getOrCreateSessionId(),
      });
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: res.answer,
          isFallback: res.is_fallback,
          imageUrls: res.image_urls,
          referenceUrls: res.reference_urls,
          time: getTime(),
        },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: "Something went wrong reaching the helpdesk. Please try again shortly.",
          isFallback: true,
          time: getTime(),
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="chat-root relative flex h-screen w-full flex-col overflow-hidden bg-white dark:bg-night-bg dark:text-slate-100">
      <DarkBackdrop />

      <header className="relative z-10 flex w-full shrink-0 items-center gap-3 bg-gradient-to-br from-sawo-light to-sawo-dark px-5 py-4 dark:border-b dark:border-white/10 dark:bg-white/[0.04] dark:bg-none dark:shadow-[inset_0_1px_0_rgba(255,255,255,0.18)] dark:backdrop-blur-xl">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/sawo-logo.png" alt="SAWO" className="h-10 w-10 rounded-lg object-contain" />
        <div className="flex-1">
          <h1 className="text-[15px] font-bold tracking-tight text-white">SAWO Helpdesk Assistant</h1>
          <span className="flex items-center gap-1.5 text-[11px] text-white/80">
            <span className="h-1.5 w-1.5 rounded-full bg-[#25d366] dark:shadow-[0_0_6px_2px_rgba(37,211,102,0.55)]" />
            Online now
          </span>
        </div>
        <ThemeToggle />
      </header>
      <MessageList messages={messages} loading={loading} onSelectSuggestion={handleSend} />
      <ChatInput onSend={handleSend} disabled={loading} />
    </main>
  );
}
