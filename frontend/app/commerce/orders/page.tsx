"use client";
import { useEffect, useState } from "react";
import { AdminShell } from "@/components/admin/AdminShell";
import { EmptyState } from "@/components/admin/EmptyState";
import { api } from "@/lib/api";

type Order = {
  order_number: string;
  tracking_number: string;
  status: string;
  currency: string;
  subtotal: string;
  item_count: number;
  customer_name: string;
  customer_email?: string | null;
  placed_at: string;
};

type OrderDetail = Order & {
  customer_phone?: string | null;
  shipping_address?: string | null;
  items: { sku: string; name: string; image: string | null; quantity: number; unit_amount: string | null; line_total: string }[];
  stages: { status: string; label: string; at: string; done: boolean }[];
};

const LABEL: Record<string, string> = {
  placed: "Recibido",
  confirmed: "Confirmado",
  preparing: "En preparación",
  shipped: "Enviado",
  delivered: "Entregado",
};

export default function Page() {
  const [orders, setOrders] = useState<Order[]>([]);
  const [detail, setDetail] = useState<OrderDetail | null>(null);
  const [openNumber, setOpenNumber] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");

  async function load() {
    setLoading(true);
    try {
      setOrders(await api("/admin/storefront/orders"));
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Error");
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    load();
  }, []);

  async function toggle(orderNumber: string) {
    if (openNumber === orderNumber) {
      setOpenNumber("");
      return;
    }
    setOpenNumber(orderNumber);
    setDetail(null);
    try {
      setDetail(await api(`/admin/storefront/orders/${orderNumber}`));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Error");
    }
  }

  async function advance(orderNumber: string) {
    setBusy(orderNumber);
    setError("");
    try {
      await api(`/admin/storefront/orders/${orderNumber}/advance`, { method: "POST" });
      await load();
      if (openNumber === orderNumber) setDetail(await api(`/admin/storefront/orders/${orderNumber}`));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Error");
    } finally {
      setBusy("");
    }
  }

  return (
    <AdminShell title="Pedidos" description="Pedidos del storefront. Al avanzar el estado, el seguimiento del cliente se actualiza en vivo.">
      {loading ? (
        <p>Cargando…</p>
      ) : orders.length === 0 ? (
        <EmptyState title="Sin pedidos todavía" description="Cuando alguien compre en la tienda pública, el pedido aparecerá aquí." />
      ) : (
        orders.map((order) => (
          <div className="tile" key={order.order_number}>
            <div className="row">
              <span>
                <strong>{order.order_number}</strong> · {LABEL[order.status] ?? order.status}
                <br />
                {order.customer_name}
                {order.customer_email ? ` · ${order.customer_email}` : ""} · {order.item_count} art. · {order.currency} {order.subtotal}
                <br />
                {order.tracking_number} · {new Date(order.placed_at).toLocaleString()}
              </span>
              <span className="nav">
                <button type="button" style={{ width: "auto" }} onClick={() => toggle(order.order_number)}>
                  {openNumber === order.order_number ? "Ocultar" : "Ver detalle"}
                </button>
                {order.status !== "delivered" && (
                  <button style={{ width: "auto" }} disabled={busy === order.order_number} onClick={() => advance(order.order_number)}>
                    {busy === order.order_number ? "…" : "Avanzar estado"}
                  </button>
                )}
              </span>
            </div>

            {openNumber === order.order_number && (
              <div className="order-detail">
                {!detail ? (
                  <p>Cargando detalle…</p>
                ) : (
                  <>
                    <div className="order-steps">
                      {detail.stages.map((stage) => (
                        <span key={stage.status} className={`order-step${stage.done ? " done" : ""}`}>
                          {stage.done ? "●" : "○"} {stage.label}
                        </span>
                      ))}
                    </div>
                    {detail.shipping_address && <p className="order-ship">Envío a: {detail.shipping_address}</p>}
                    {detail.items.map((item) => (
                      <div className="order-item" key={item.sku}>
                        <span className="order-thumb">
                          {item.image ? (
                            // eslint-disable-next-line @next/next/no-img-element
                            <img src={item.image} alt="" />
                          ) : null}
                        </span>
                        <span className="order-item-name">
                          {item.name}
                          <br />
                          <small>
                            {item.sku} · x{item.quantity}
                          </small>
                        </span>
                        <strong>
                          {detail.currency} {item.line_total}
                        </strong>
                      </div>
                    ))}
                  </>
                )}
              </div>
            )}
          </div>
        ))
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </AdminShell>
  );
}
