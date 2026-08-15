"use client";
import { useState } from "react";
import { formatPrice } from "@/lib/storefront";
import { useCart } from "./cart";

export function CartDrawer() {
  const { items, open, setOpen, setQty, remove, clear, subtotal, count } = useCart();
  const [done, setDone] = useState(false);
  const currency = items[0]?.currency ?? "USD";

  return (
    <>
      <div className={`sf-scrim ${open ? "open" : ""}`} onClick={() => setOpen(false)} aria-hidden="true" />
      <aside className={`sf-drawer ${open ? "open" : ""}`} aria-label="Carrito de compras" aria-hidden={!open}>
        <div className="sf-drawer-head">
          <strong>Tu carrito{count > 0 ? ` (${count})` : ""}</strong>
          <button className="sf-icon-btn" onClick={() => setOpen(false)} aria-label="Cerrar carrito">
            ✕
          </button>
        </div>

        {done ? (
          <div className="sf-drawer-done">
            <div className="sf-done-check">✓</div>
            <h3>¡Pedido confirmado!</h3>
            <p>Gracias por tu compra en la tienda demo de ClickHome.</p>
            <button
              className="sf-checkout"
              onClick={() => {
                clear();
                setDone(false);
                setOpen(false);
              }}
            >
              Cerrar
            </button>
          </div>
        ) : items.length === 0 ? (
          <div className="sf-drawer-empty">
            <p>Tu carrito está vacío.</p>
            <button className="sf-checkout" onClick={() => setOpen(false)}>
              Seguir comprando
            </button>
          </div>
        ) : (
          <>
            <div className="sf-drawer-items">
              {items.map((line) => (
                <div className="sf-line" key={line.slug}>
                  <div className="sf-line-info">
                    <span className="sf-line-name">{line.name}</span>
                    <span className="sf-line-sku">{line.sku}</span>
                  </div>
                  <div className="sf-line-ctrl">
                    <div className="sf-stepper">
                      <button onClick={() => setQty(line.slug, line.qty - 1)} aria-label="Quitar uno">
                        −
                      </button>
                      <span>{line.qty}</span>
                      <button onClick={() => setQty(line.slug, line.qty + 1)} disabled={line.qty >= line.available} aria-label="Agregar uno">
                        +
                      </button>
                    </div>
                    <span className="sf-line-price">{formatPrice(line.price * line.qty, line.currency)}</span>
                    <button className="sf-line-del" onClick={() => remove(line.slug)} aria-label={`Quitar ${line.name}`}>
                      🗑
                    </button>
                  </div>
                </div>
              ))}
            </div>
            <div className="sf-drawer-foot">
              <div className="sf-subtotal">
                <span>Subtotal</span>
                <strong>{formatPrice(subtotal, currency)}</strong>
              </div>
              <button className="sf-checkout" onClick={() => setDone(true)}>
                Finalizar compra
              </button>
              <button className="sf-clear" onClick={clear}>
                Vaciar carrito
              </button>
            </div>
          </>
        )}
      </aside>
    </>
  );
}
