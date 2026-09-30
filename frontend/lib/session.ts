// One conversation = one page load of the chat. The chat UI keeps its
// messages in React state only, so a reload already starts a visually fresh
// conversation; giving it a fresh session id too keeps Chat Logs (and the
// backend's same-session conversation history) in step with what the person
// actually saw, instead of merging every chat a browser ever had into one
// endless "session".
let conversationId: string | null = null;

export function getOrCreateSessionId(): string {
  if (typeof window === "undefined") return "";
  if (!conversationId) conversationId = crypto.randomUUID();
  return conversationId;
}

// Reserved for later: per-browser grouping (one id kept across reloads and
// days). Not per-IP — IP-based grouping would be done server-side from
// ChatLog.ip_address instead.
//
// const SESSION_KEY = "helpdesk_session_id";
// export function getOrCreateBrowserSessionId(): string {
//   if (typeof window === "undefined") return "";
//   let sessionId = localStorage.getItem(SESSION_KEY);
//   if (!sessionId) {
//     sessionId = crypto.randomUUID();
//     localStorage.setItem(SESSION_KEY, sessionId);
//   }
//   return sessionId;
// }
