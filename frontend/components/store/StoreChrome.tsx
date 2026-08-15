"use client";
import type { ReactNode } from "react";
import { CartProvider } from "./cart";
import { CartDrawer } from "./CartDrawer";
import { StoreHeader } from "./StoreHeader";

export function StoreChrome({ storeName, children }: { storeName: string; children: ReactNode }) {
  return (
    <CartProvider>
      <div className="sf-root">
        <StoreHeader storeName={storeName} />
        <main className="sf-main">{children}</main>
        <footer className="sf-footer">
          <span>{storeName} · Tienda demo sobre Nexus</span>
          <span>Precios y stock en vivo desde el catálogo</span>
        </footer>
        <CartDrawer />
      </div>
    </CartProvider>
  );
}
