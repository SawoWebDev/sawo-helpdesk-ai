const SESSION_KEY = "helpdesk_session_id";

export function getOrCreateSessionId(): string {
  if (typeof window === "undefined") return "";
  let sessionId = localStorage.getItem(SESSION_KEY);
  if (!sessionId) {
    sessionId = crypto.randomUUID();
    localStorage.setItem(SESSION_KEY, sessionId);
  }
  return sessionId;
}
