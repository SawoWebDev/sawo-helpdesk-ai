"use client";

import { useEffect, useRef, useState } from "react";
import ChatInput from "@/components/chat/ChatInput";
import ConversationSidebar from "@/components/chat/ConversationSidebar";
import MessageList from "@/components/chat/MessageList";
import ThemeToggle from "@/components/chat/ThemeToggle";
import DarkBackdrop from "@/components/chat/DarkBackdrop";
import Toast from "@/components/chat/Toast";
import { ChatMessage } from "@/components/chat/MessageBubble";
import { ApiError, apiPost } from "@/lib/api";
import {
  ACTIVE_CONVERSATION_KEY,
  ConversationDetail,
  ConversationSummary,
  getConversation,
  listConversations,
} from "@/lib/conversations";
import { getOrCreateSessionId } from "@/lib/session";

interface ChatResponse {
  answer: string;
  is_fallback: boolean;
  confidence_score: number | null;
  matched_faq_ids: number[];
  image_urls: string[];
  reference_urls: string[];
  chat_log_id: number | null;
  low_confidence: boolean;
  conversation_id: number | null;
  conversation_title: string | null;
}

// A persisted ChatLog has no column for isFallback/lowConfidence/imageUrls/
// referenceUrls (same gap the admin Chat Logs viewer has), so reloaded
// history renders text and prior feedback state only.
function toChatMessages(detail: ConversationDetail): ChatMessage[] {
  const result: ChatMessage[] = [];
  for (const message of detail.messages) {
    const time = new Date(message.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    result.push({ role: "user", text: message.question_text, time });
    result.push({
      role: "assistant",
      text: message.answer_text,
      chatLogId: message.id,
      rating: message.rating ?? undefined,
      feedbackReason: message.feedback_reason ?? undefined,
      time,
    });
  }
  return result;
}

const ONLINE_DOT_CLICK_TARGET = 5;
const ONLINE_DOT_CLICK_RESET_MS = 2000;

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const onlineDotClicks = useRef(0);
  const onlineDotResetTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<number | null>(null);
  // Guards against a message being sent into a conversation that hasn't
  // finished restoring yet (mount-time list fetch + active-conversation load).
  const [isInitializing, setIsInitializing] = useState(true);

  function refreshConversations() {
    listConversations()
      .then(setConversations)
      .catch(() => {
        // Sidebar is a convenience, not the source of truth — a failed
        // refresh just leaves the list stale until the next successful one.
      });
  }

  useEffect(() => {
    refreshConversations();

    const storedId = localStorage.getItem(ACTIVE_CONVERSATION_KEY);
    if (!storedId) {
      setIsInitializing(false);
      return;
    }
    getConversation(Number(storedId))
      .then((detail) => {
        setActiveConversationId(detail.id);
        setMessages(toChatMessages(detail));
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 404) {
          localStorage.removeItem(ACTIVE_CONVERSATION_KEY);
        }
      })
      .finally(() => setIsInitializing(false));
    // Mount-only: this restores whatever was active when the page last
    // loaded, not something that should re-run as state changes afterward.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleNewChat() {
    setMessages([]);
    setActiveConversationId(null);
    localStorage.removeItem(ACTIVE_CONVERSATION_KEY);
  }

  async function handleSelectConversation(id: number) {
    if (id === activeConversationId) return;
    try {
      const detail = await getConversation(id);
      setActiveConversationId(detail.id);
      setMessages(toChatMessages(detail));
      localStorage.setItem(ACTIVE_CONVERSATION_KEY, String(detail.id));
    } catch {
      showToast("Couldn't load that conversation, please try again");
    }
  }

  function showToast(text: string) {
    if (toastTimer.current) clearTimeout(toastTimer.current);
    setToast(text);
    toastTimer.current = setTimeout(() => setToast(null), 2000);
  }

  function handleOnlineDotClick() {
    onlineDotClicks.current += 1;
    if (onlineDotResetTimer.current) clearTimeout(onlineDotResetTimer.current);

    if (onlineDotClicks.current >= ONLINE_DOT_CLICK_TARGET) {
      onlineDotClicks.current = 0;
      window.open("/admin/dashboard", "_blank", "noopener,noreferrer");
      return;
    }

    onlineDotResetTimer.current = setTimeout(() => {
      onlineDotClicks.current = 0;
    }, ONLINE_DOT_CLICK_RESET_MS);
  }

  function getTime() {
    return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  async function handleFeedback(chatLogId: number, rating: "up" | "down", reason?: string) {
    // Optimistic: the vast majority of feedback submissions succeed, and
    // waiting on the round-trip before showing the selected state would make
    // the button feel unresponsive for no real benefit.
    const previous = messages.find((m) => m.chatLogId === chatLogId);
    setMessages((prev) =>
      prev.map((m) => (m.chatLogId === chatLogId ? { ...m, rating, feedbackReason: rating === "down" ? reason : undefined } : m))
    );
    try {
      await apiPost("/api/chat/feedback", {
        chat_log_id: chatLogId,
        session_id: getOrCreateSessionId(),
        rating,
        reason,
      });
      showToast("Thanks for your feedback");
    } catch {
      setMessages((prev) =>
        prev.map((m) =>
          m.chatLogId === chatLogId
            ? { ...m, rating: previous?.rating, feedbackReason: previous?.feedbackReason }
            : m
        )
      );
      showToast("Couldn't send feedback, please try again");
    }
  }

  async function handleReport(
    chatLogId: number,
    reason: string | undefined,
    comment: string | undefined
  ): Promise<boolean> {
    const index = messages.findIndex((m) => m.chatLogId === chatLogId);
    if (index === -1) return false;
    const message = messages[index];
    const question = [...messages.slice(0, index)].reverse().find((m) => m.role === "user");
    try {
      await apiPost("/api/chat/report", {
        chat_log_id: chatLogId,
        session_id: getOrCreateSessionId(),
        question_text: question?.text ?? "",
        answer_text: message.text,
        reference_urls: message.referenceUrls ?? [],
        reason,
        comment,
      });
      return true;
    } catch {
      return false;
    }
  }

  async function handleSend(text: string) {
    setMessages((prev) => [...prev, { role: "user", text, time: getTime() }]);
    setLoading(true);
    try {
      const res = await apiPost<ChatResponse>("/api/chat", {
        question: text,
        session_id: getOrCreateSessionId(),
        conversation_id: activeConversationId,
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
          chatLogId: res.chat_log_id ?? undefined,
          lowConfidence: res.low_confidence,
        },
      ]);
      if (res.conversation_id !== null && res.conversation_id !== activeConversationId) {
        setActiveConversationId(res.conversation_id);
        localStorage.setItem(ACTIVE_CONVERSATION_KEY, String(res.conversation_id));
      }
      if (res.conversation_id !== null) refreshConversations();
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
    <div className="flex h-screen w-full flex-col overflow-hidden bg-white dark:bg-night-bg dark:text-slate-100">
      {/* Dark mode: translucent black glass (not the lighter, neutral `.glass`
          frost used elsewhere), with a single border on the bar's one true
          edge — its bottom — rather than a glow ring all around. */}
      <header className="relative z-10 flex w-full shrink-0 items-center gap-3 border-b border-sawo-border/50 bg-gradient-to-br from-sawo-light to-sawo-dark px-5 py-4 dark:border-white/10 dark:bg-none dark:bg-black/40 dark:backdrop-blur-2xl">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/sawo-logo.png" alt="SAWO" className="h-10 w-10 rounded-lg object-contain" />
        <div className="flex-1">
          <h1 className="text-[15px] font-bold tracking-tight text-white">SAWO Helpdesk Assistant</h1>
          <span className="flex items-center gap-1.5 text-[11px] text-white/80">
            <span
              onClick={handleOnlineDotClick}
              className="h-1.5 w-1.5 cursor-pointer rounded-full bg-[#25d366] dark:shadow-[0_0_6px_2px_rgba(37,211,102,0.55)]"
            />
            Online
          </span>
        </div>
        <ThemeToggle />
        {/* A glare confined to the one edge that actually borders something —
            the bottom — instead of a ring around the whole bar. */}
        <span
          aria-hidden
          className="pointer-events-none absolute inset-x-0 bottom-0 h-px dark:bg-gradient-to-r dark:from-white/50 dark:via-white/10 dark:to-transparent dark:shadow-[0_0_8px_1px_rgba(255,255,255,0.2)]"
        />
      </header>

      <div className="flex flex-1 overflow-hidden">
        <ConversationSidebar
          conversations={conversations}
          activeId={activeConversationId}
          onSelect={handleSelectConversation}
          onNewChat={handleNewChat}
        />
        <main className="chat-root relative flex h-full flex-1 flex-col overflow-hidden bg-sawo-border dark:bg-night-bg dark:text-slate-100">
          <DarkBackdrop />

          <MessageList
            messages={messages}
            loading={loading}
            onSelectSuggestion={handleSend}
            onCopyMessage={() => showToast("Response copied")}
            onFeedback={handleFeedback}
            onReport={handleReport}
          />
          <ChatInput onSend={handleSend} disabled={loading || isInitializing} />
          <Toast message={toast} />
        </main>
      </div>
    </div>
  );
}
