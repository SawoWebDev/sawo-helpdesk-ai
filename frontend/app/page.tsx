"use client";

import { useState } from "react";
import ChatInput from "@/components/chat/ChatInput";
import MessageList from "@/components/chat/MessageList";
import { ChatMessage } from "@/components/chat/MessageBubble";
import { apiPost } from "@/lib/api";

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

  async function handleSend(text: string) {
    setMessages((prev) => [...prev, { role: "user", text }]);
    setLoading(true);
    try {
      const res = await apiPost<ChatResponse>("/api/chat", { question: text });
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: res.answer,
          isFallback: res.is_fallback,
          imageUrls: res.image_urls,
          referenceUrls: res.reference_urls,
        },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: "Something went wrong reaching the helpdesk. Please try again shortly.",
          isFallback: true,
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto flex h-screen max-w-2xl flex-col bg-slate-50">
      <header className="border-b border-slate-200 bg-white px-4 py-3">
        <h1 className="text-lg font-semibold text-slate-800">Helpdesk Assistant</h1>
        <p className="text-xs text-slate-500">Ask us anything — answers come from our knowledge base.</p>
      </header>
      <MessageList messages={messages} loading={loading} />
      <ChatInput onSend={handleSend} disabled={loading} />
    </main>
  );
}
