"use client";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { StoreProduct } from "@/lib/storefront";

type WishlistContextValue = {
  items: StoreProduct[];
  has: (slug: string) => boolean;
  toggle: (product: StoreProduct) => void;
  remove: (slug: string) => void;
  count: number;
};

const WishlistContext = createContext<WishlistContextValue | null>(null);
const STORAGE_KEY = "clickhome_wishlist_v1";

export function WishlistProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<StoreProduct[]>([]);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) setItems(JSON.parse(raw));
    } catch {
      /* ignore */
    }
    setReady(true);
  }, []);

  useEffect(() => {
    if (!ready) return;
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
    } catch {
      /* storage unavailable */
    }
  }, [items, ready]);

  const has = useCallback((slug: string) => items.some((item) => item.slug === slug), [items]);
  const toggle = useCallback(
    (product: StoreProduct) =>
      setItems((prev) => (prev.some((item) => item.slug === product.slug) ? prev.filter((item) => item.slug !== product.slug) : [...prev, product])),
    [],
  );
  const remove = useCallback((slug: string) => setItems((prev) => prev.filter((item) => item.slug !== slug)), []);

  const value = useMemo(() => ({ items, has, toggle, remove, count: items.length }), [items, has, toggle, remove]);
  return <WishlistContext.Provider value={value}>{children}</WishlistContext.Provider>;
}

export function useWishlist() {
  const context = useContext(WishlistContext);
  if (!context) throw new Error("useWishlist debe usarse dentro de <WishlistProvider>");
  return context;
}
