"use client";
import Link from "next/link";
import { Suspense, type ReactNode } from "react";
import { CartProvider } from "./cart";
import { CartDrawer } from "./CartDrawer";
import { StoreHeader } from "./StoreHeader";
import { WishlistProvider } from "./wishlist";

const BENEFITS = [
  { icon: "🚚", text: "Envío a todo el Ecuador" },
  { icon: "🔒", text: "Pago 100% seguro" },
  { icon: "🛡️", text: "Garantía de 12 meses" },
  { icon: "↩️", text: "Devoluciones en 7 días" },
];

export function StoreChrome({ storeName, children }: { storeName: string; children: ReactNode }) {
  return (
    <WishlistProvider>
      <CartProvider>
        <div className="sf-root">
          <StoreHeader storeName={storeName} />
          <div className="sf-benefits">
            <div className="sf-benefits-inner">
              {BENEFITS.map((benefit) => (
                <span key={benefit.text}>
                  <b aria-hidden="true">{benefit.icon}</b> {benefit.text}
                </span>
              ))}
            </div>
          </div>
          <main className="sf-main">
            <Suspense fallback={<div className="sf-grid-wrap"><p className="sf-muted">Cargando…</p></div>}>{children}</Suspense>
          </main>
          <footer className="sf-footer">
            <div className="sf-footer-cols">
              <div>
                <h4>Comprar</h4>
                <Link href="/tienda">Catálogo</Link>
                <Link href="/tienda?category=electromenores">Electromenores</Link>
                <Link href="/tienda?category=tecnologia">Tecnología</Link>
                <Link href="/tienda/favoritos">Favoritos</Link>
              </div>
              <div>
                <h4>Ayuda</h4>
                <Link href="/tienda/rastrear">Rastrea tu pedido</Link>
                <span>Preguntas frecuentes</span>
                <span>Cambios y devoluciones</span>
                <span>Contáctanos</span>
              </div>
              <div>
                <h4>{storeName}</h4>
                <span>Sobre nosotros</span>
                <span>Trabaja con nosotros</span>
                <span>Términos y condiciones</span>
              </div>
              <div>
                <h4>Pago seguro</h4>
                <div className="sf-pay">
                  <span>VISA</span>
                  <span>Mastercard</span>
                  <span>Diners</span>
                  <span>Transferencia</span>
                </div>
                <p className="sf-footer-note">Compra protegida y datos cifrados.</p>
              </div>
            </div>
            <div className="sf-footer-bottom">
              © {new Date().getFullYear()} {storeName} · Tienda demo sobre Nexus · Precios y stock en vivo
            </div>
          </footer>
          <CartDrawer />
        </div>
      </CartProvider>
    </WishlistProvider>
  );
}
