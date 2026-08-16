"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { formatPrice, getOrder, getTracking, type StoreOrder, type Tracking } from "@/lib/storefront";

export default function OrderPage() {
  const params = useParams();
  const number = String(params.number);
  const [order, setOrder] = useState<StoreOrder | null>(null);
  const [tracking, setTracking] = useState<Tracking | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoading(true);
    Promise.all([getOrder(number), getTracking(number)])
      .then(([placedOrder, trackingInfo]) => {
        setOrder(placedOrder);
        setTracking(trackingInfo);
      })
      .catch((caught) => setError(caught instanceof Error ? caught.message : "Error"))
      .finally(() => setLoading(false));
  }, [number]);

  if (loading) return <div className="sf-pad"><p className="sf-muted">Cargando pedido…</p></div>;
  if (error || !order || !tracking)
    return (
      <div className="sf-pad">
        <p className="sf-error">{error || "Pedido no encontrado"}</p>
        <Link className="sf-back" href="/tienda">← Volver a la tienda</Link>
      </div>
    );

  const fmtDate = (value: string) => new Date(value).toLocaleDateString("es-EC", { day: "2-digit", month: "long" });

  return (
    <div className="sf-pad sf-order">
      <Link className="sf-back" href="/tienda">← Volver a la tienda</Link>
      <div className="sf-order-grid">
        <section className="sf-order-card">
          <h1>Pedido {order.order_number}</h1>
          <p className="sf-muted">
            Rastreo {order.tracking_number} · {order.item_count} artículos · {formatPrice(order.subtotal, order.currency)}
          </p>
          <div className="sf-timeline">
            {tracking.stages.map((stage) => (
              <div key={stage.status} className={`sf-tl-step${stage.done ? " done" : ""}`}>
                <span className="sf-tl-dot" />
                <div className="sf-tl-body">
                  <strong>{stage.label}</strong>
                  <span className="sf-muted">{fmtDate(stage.at)}</span>
                </div>
              </div>
            ))}
          </div>
          <p className="sf-order-eta">
            Entrega estimada: <strong>{fmtDate(tracking.estimated_delivery)}</strong>
          </p>
        </section>
        <section className="sf-order-card">
          <h2>Productos</h2>
          {order.items.map((item) => (
            <div className="sf-order-line" key={item.sku}>
              <span>
                {item.name}
                <br />
                <span className="sf-muted">
                  {item.sku} · x{item.quantity}
                </span>
              </span>
              <strong>{formatPrice(item.line_total, order.currency)}</strong>
            </div>
          ))}
        </section>
      </div>
    </div>
  );
}
