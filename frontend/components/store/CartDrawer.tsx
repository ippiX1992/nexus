"use client";
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { createOrder, formatPrice, type StoreOrder } from "@/lib/storefront";
import { useCart } from "./cart";

type Stage = "cart" | "form" | "done";

export function CartDrawer() {
  const { items, open, setOpen, setQty, remove, clear, subtotal, count } = useCart();
  const [stage, setStage] = useState<Stage>("cart");
  const [placing, setPlacing] = useState(false);
  const [error, setError] = useState("");
  const [order, setOrder] = useState<StoreOrder | null>(null);
  const currency = items[0]?.currency ?? "USD";

  function close() {
    setOpen(false);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setPlacing(true);
    setError("");
    try {
      const placed = await createOrder({
        customer_name: String(form.get("name") || ""),
        customer_email: String(form.get("email") || "") || undefined,
        customer_phone: String(form.get("phone") || "") || undefined,
        shipping_address: String(form.get("address") || "") || undefined,
        items: items.map((line) => ({ slug: line.slug, quantity: line.qty })),
      });
      setOrder(placed);
      clear();
      setStage("done");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "No se pudo crear el pedido");
    } finally {
      setPlacing(false);
    }
  }

  function reset() {
    setStage("cart");
    setOrder(null);
    setError("");
    setOpen(false);
  }

  return (
    <>
      <div className={`sf-scrim ${open ? "open" : ""}`} onClick={close} aria-hidden="true" />
      <aside className={`sf-drawer ${open ? "open" : ""}`} aria-label="Carrito de compras" aria-hidden={!open}>
        <div className="sf-drawer-head">
          <strong>
            {stage === "form" ? "Datos de envío" : stage === "done" ? "¡Pedido confirmado!" : `Tu carrito${count > 0 ? ` (${count})` : ""}`}
          </strong>
          <button className="sf-icon-btn" onClick={close} aria-label="Cerrar carrito">
            ✕
          </button>
        </div>

        {stage === "done" && order ? (
          <div className="sf-drawer-done">
            <div className="sf-done-check">✓</div>
            <h3>Gracias, {order.customer_name.split(" ")[0]}</h3>
            <p>
              Pedido <strong>{order.order_number}</strong>
              <br />
              Total {formatPrice(order.subtotal, order.currency)} · {order.item_count} artículos
            </p>
            <p className="sf-muted">Rastreo: {order.tracking_number}</p>
            <Link className="sf-checkout" href={`/tienda/pedido/${order.order_number}`} onClick={reset}>
              Ver seguimiento
            </Link>
            <button className="sf-clear" onClick={reset}>
              Seguir comprando
            </button>
          </div>
        ) : stage === "form" ? (
          <form className="sf-checkout-form" onSubmit={submit}>
            <div className="sf-order-summary">
              {items.map((line) => (
                <div className="sf-sum-line" key={line.slug}>
                  <span>
                    {line.name} × {line.qty}
                  </span>
                  <span>{formatPrice(line.price * line.qty, line.currency)}</span>
                </div>
              ))}
              <div className="sf-sum-row">
                <span>Subtotal</span>
                <span>{formatPrice(subtotal, currency)}</span>
              </div>
              <div className="sf-sum-row">
                <span>Envío</span>
                <span className="sf-free">Gratis</span>
              </div>
              <div className="sf-sum-row sf-sum-total">
                <span>Total</span>
                <strong>{formatPrice(subtotal, currency)}</strong>
              </div>
              <p className="sf-sum-eta">🚚 Entrega estimada: 2–4 días · Envío a todo el Ecuador</p>
            </div>
            <label>
              Nombre completo
              <input name="name" required minLength={2} autoComplete="name" />
            </label>
            <label>
              Correo (opcional)
              <input name="email" type="email" autoComplete="email" />
            </label>
            <label>
              Teléfono (opcional)
              <input name="phone" autoComplete="tel" />
            </label>
            <label>
              Dirección de envío (opcional)
              <textarea name="address" rows={2} autoComplete="street-address" />
            </label>
            {error && <p className="sf-error" role="alert">{error}</p>}
            <button className="sf-checkout" disabled={placing}>
              {placing ? "Procesando…" : "Confirmar pedido"}
            </button>
            <button type="button" className="sf-clear" onClick={() => setStage("cart")}>
              ← Volver al carrito
            </button>
          </form>
        ) : items.length === 0 ? (
          <div className="sf-drawer-empty">
            <p>Tu carrito está vacío.</p>
            <button className="sf-checkout" onClick={close}>
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
              <button className="sf-checkout" onClick={() => setStage("form")}>
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
