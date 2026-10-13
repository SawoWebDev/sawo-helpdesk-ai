// One conversation = one page load of the chat. The chat UI keeps its
// messages in React state only, so a reload already starts a visually fresh
// conversation; giving it a fresh session id too keeps Chat Logs (and the
// backend's same-session conversation history) in step with what the person
// actually saw, instead of merging every chat a browser ever had into one
// endless "session".
let conversationId: string | null = null;

// crypto.randomUUID only exists in secure contexts (HTTPS or localhost), so
// it is undefined when staff open the app over plain http://<LAN IP>.
// crypto.getRandomValues works everywhere; build a v4 UUID from it instead.
function randomUUID(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export function getOrCreateSessionId(): string {
  if (typeof window === "undefined") return "";
  if (!conversationId) conversationId = randomUUID();
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
