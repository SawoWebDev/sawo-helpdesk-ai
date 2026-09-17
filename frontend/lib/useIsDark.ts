"use client";

import { useEffect, useState } from "react";

/** Tracks the `dark` class on <html>, which ThemeToggle flips at runtime
 * (no route change / remount), so chart colors need a live subscription
 * rather than a read-once check. */
export function useIsDark(): boolean {
  const [isDark, setIsDark] = useState(false);

  useEffect(() => {
    const root = document.documentElement;
    setIsDark(root.classList.contains("dark"));
    const observer = new MutationObserver(() => setIsDark(root.classList.contains("dark")));
    observer.observe(root, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, []);

  return isDark;
}
