"use client";
import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";

type UIContextValue = {
  toastMessage: string;
  showToast: (message: string) => void;
  quickViewSlug: string | null;
  openQuickView: (slug: string) => void;
  closeQuickView: () => void;
};

const UIContext = createContext<UIContextValue | null>(null);

export function UIProvider({ children }: { children: ReactNode }) {
  const [toastMessage, setToastMessage] = useState("");
  const [quickViewSlug, setQuickViewSlug] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showToast = useCallback((message: string) => {
    setToastMessage(message);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setToastMessage(""), 2600);
  }, []);
  const openQuickView = useCallback((slug: string) => setQuickViewSlug(slug), []);
  const closeQuickView = useCallback(() => setQuickViewSlug(null), []);

  return (
    <UIContext.Provider value={{ toastMessage, showToast, quickViewSlug, openQuickView, closeQuickView }}>{children}</UIContext.Provider>
  );
}

export function useUI() {
  const context = useContext(UIContext);
  if (!context) throw new Error("useUI debe usarse dentro de <UIProvider>");
  return context;
}

export function Toast() {
  const { toastMessage } = useUI();
  return (
    <div className={`sf-toast${toastMessage ? " show" : ""}`} role="status" aria-live="polite">
      {toastMessage}
    </div>
  );
}
