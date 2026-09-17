"use client";

import { useCallback, useEffect, useState } from "react";

// Mirrors sawo-chatbot's client-only "unread" model: no server column at
// all. A localStorage map records the `last_at` that was on-screen when the
// admin last opened a session; a session reads unread whenever its current
// last_at is strictly newer than that stored value — so a new message makes
// an already-opened conversation unread again. Marking read/unread is just
// writing/deleting this map, no server round trip.
const STORAGE_KEY = "sawo-helpdesk-logs-seen-v1";

function readMap(): Record<string, string> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function writeMap(map: Record<string, string>) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(map));
  } catch {
    // storage may be unavailable (private mode); unread tracking just won't persist
  }
}

export function useUnreadSessions() {
  const [seenMap, setSeenMap] = useState<Record<string, string>>({});

  useEffect(() => {
    setSeenMap(readMap());
  }, []);

  const isUnread = useCallback(
    (sessionId: string, lastAt: string) => {
      const seenAt = seenMap[sessionId];
      if (!seenAt) return true;
      return new Date(lastAt).getTime() > new Date(seenAt).getTime();
    },
    [seenMap]
  );

  const markRead = useCallback((sessionId: string, lastAt: string) => {
    setSeenMap((prev) => {
      const next = { ...prev, [sessionId]: lastAt };
      writeMap(next);
      return next;
    });
  }, []);

  const markUnread = useCallback((sessionId: string) => {
    setSeenMap((prev) => {
      const next = { ...prev };
      delete next[sessionId];
      writeMap(next);
      return next;
    });
  }, []);

  return { isUnread, markRead, markUnread };
}
