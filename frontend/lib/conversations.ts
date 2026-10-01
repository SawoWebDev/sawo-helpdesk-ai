import { apiGet } from "./api";

// Only the active conversation's id is kept client-side (not its content) —
// the server stays the source of truth; this just survives a page reload.
export const ACTIVE_CONVERSATION_KEY = "helpdesk_active_conversation";

export interface ConversationSummary {
  id: number;
  title: string;
  updated_at: string;
}

export interface ConversationMessage {
  id: number;
  question_text: string;
  answer_text: string;
  rating: "up" | "down" | null;
  feedback_reason: string | null;
  created_at: string;
}

export interface ConversationDetail extends ConversationSummary {
  messages: ConversationMessage[];
}

export function listConversations(): Promise<ConversationSummary[]> {
  return apiGet<ConversationSummary[]>("/api/conversations");
}

export function getConversation(id: number): Promise<ConversationDetail> {
  return apiGet<ConversationDetail>(`/api/conversations/${id}`);
}
