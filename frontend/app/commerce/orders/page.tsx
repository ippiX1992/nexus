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

const LABEL: Record<string, string> = {
  placed: "Recibido",
  confirmed: "Confirmado",
  preparing: "En preparación",
  shipped: "Enviado",
  delivered: "Entregado",
};

export default function Page() {
  const [orders, setOrders] = useState<Order[]>([]);
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

  async function advance(orderNumber: string) {
    setBusy(orderNumber);
    setError("");
    try {
      await api(`/admin/storefront/orders/${orderNumber}/advance`, { method: "POST" });
      await load();
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
          <div className="row" key={order.order_number}>
            <span>
              <strong>{order.order_number}</strong> · {LABEL[order.status] ?? order.status}
              <br />
              {order.customer_name}
              {order.customer_email ? ` · ${order.customer_email}` : ""} · {order.item_count} art. · {order.currency} {order.subtotal}
              <br />
              {order.tracking_number} · {new Date(order.placed_at).toLocaleString()}
            </span>
            {order.status !== "delivered" && (
              <button className="compact" disabled={busy === order.order_number} onClick={() => advance(order.order_number)}>
                {busy === order.order_number ? "…" : "Avanzar estado"}
              </button>
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
