"use client";
import { Suspense, type ReactNode } from "react";
import { CartProvider } from "./cart";
import { CartDrawer } from "./CartDrawer";
import { StoreHeader } from "./StoreHeader";
import { WishlistProvider } from "./wishlist";

export function StoreChrome({ storeName, children }: { storeName: string; children: ReactNode }) {
  return (
    <WishlistProvider>
      <CartProvider>
        <div className="sf-root">
        <StoreHeader storeName={storeName} />
        <main className="sf-main">
          <Suspense fallback={<div className="sf-grid-wrap"><p className="sf-muted">Cargando…</p></div>}>{children}</Suspense>
        </main>
        <footer className="sf-footer">
          <span>{storeName} · Tienda demo sobre Nexus</span>
          <span>Precios y stock en vivo desde el catálogo</span>
        </footer>
          <CartDrawer />
        </div>
      </CartProvider>
    </WishlistProvider>
  );
}
