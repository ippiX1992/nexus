"use client";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type CartItem = { slug: string; name: string; price: number; sku: string; currency: string; available: number; qty: number };

type CartContextValue = {
  items: CartItem[];
  count: number;
  subtotal: number;
  add: (item: Omit<CartItem, "qty">, qty?: number) => void;
  setQty: (slug: string, qty: number) => void;
  remove: (slug: string) => void;
  clear: () => void;
  open: boolean;
  setOpen: (value: boolean) => void;
};

const CartContext = createContext<CartContextValue | null>(null);
const STORAGE_KEY = "clickhome_cart_v1";

export function CartProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<CartItem[]>([]);
  const [open, setOpen] = useState(false);
  const [ready, setReady] = useState(false);

  // Load once on mount (client-only) so SSR and first render both start empty.
  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) setItems(JSON.parse(raw));
    } catch {
      /* ignore corrupt cart */
    }
    setReady(true);
  }, []);

  useEffect(() => {
    if (!ready) return;
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
    } catch {
      /* storage full or unavailable */
    }
  }, [items, ready]);

  const add = useCallback((item: Omit<CartItem, "qty">, qty = 1) => {
    setItems((prev) => {
      const max = item.available || 99;
      const existing = prev.find((line) => line.slug === item.slug);
      if (existing) return prev.map((line) => (line.slug === item.slug ? { ...line, qty: Math.min(max, line.qty + qty) } : line));
      return [...prev, { ...item, qty: Math.min(max, Math.max(1, qty)) }];
    });
    // Feedback is a toast (see UIProvider), not a forced drawer open.
  }, []);

  const setQty = useCallback((slug: string, qty: number) => {
    setItems((prev) => prev.flatMap((line) => (line.slug === slug ? (qty <= 0 ? [] : [{ ...line, qty: Math.min(line.available || 99, qty) }]) : [line])));
  }, []);

  const remove = useCallback((slug: string) => setItems((prev) => prev.filter((line) => line.slug !== slug)), []);
  const clear = useCallback(() => setItems([]), []);

  const count = useMemo(() => items.reduce((sum, line) => sum + line.qty, 0), [items]);
  const subtotal = useMemo(() => items.reduce((sum, line) => sum + line.price * line.qty, 0), [items]);

  const value = useMemo(
    () => ({ items, count, subtotal, add, setQty, remove, clear, open, setOpen }),
    [items, count, subtotal, add, setQty, remove, clear, open],
  );
  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
}

export function useCart() {
  const context = useContext(CartContext);
  if (!context) throw new Error("useCart debe usarse dentro de <CartProvider>");
  return context;
}
