"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { AdminShell } from "@/components/admin/AdminShell";
import { StatCard } from "@/components/admin/StatCard";
import { api } from "@/lib/api";
import { technicalError } from "@/lib/catalog";

type Metrics = {
  orders: number;
  revenue: string;
  products: number;
  inventory_value: string;
  inventory_units: number;
  by_status: Record<string, number>;
  top_products: { name: string; qty: number; revenue: string }[];
};

const money = (value: string | number) => `$${Number(value).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const STATUS_LABEL: Record<string, string> = {
  placed: "Recibidos",
  confirmed: "Confirmados",
  preparing: "En preparación",
  shipped: "Enviados",
  delivered: "Entregados",
};

// Plain-language guide to what each area of the panel does — the fix for
// "no entiendo cómo funciona el panel".
const GUIDE = [
  { icon: "🛍️", title: "Tienda", desc: "Tu tienda pública: catálogo, carrito y checkout que ven los clientes.", href: "/tienda", external: true, cta: "Abrir tienda" },
  { icon: "📦", title: "Pedidos", desc: "Revisa las compras y avanza su estado; el cliente ve el seguimiento en vivo.", href: "/commerce/orders", cta: "Ver pedidos" },
  { icon: "🏷️", title: "Catálogo", desc: "Tus productos, marcas y categorías (taxonomías).", href: "/catalog/products", cta: "Ver productos" },
  { icon: "💲", title: "Precios", desc: "Listas de precios y reglas de descuento por tienda o canal.", href: "/commerce/price-lists", cta: "Ver precios" },
  { icon: "📥", title: "Inventario", desc: "Stock por bodega y ubicación; recepciones, ajustes y transferencias.", href: "/commerce/inventory", cta: "Ver inventario" },
  { icon: "🏬", title: "Plataforma", desc: "Tiendas, canales, mercados y ambientes (configuración avanzada).", href: "/platform/stores", cta: "Ver plataforma" },
];

export default function Page() {
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api("/admin/storefront/metrics")
      .then(setMetrics)
      .catch((caught) => setError(technicalError(caught)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <AdminShell title="Inicio" description="Resumen de tu tienda y guía rápida del panel.">
      {loading ? (
        <p>Cargando…</p>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatCard label="Ventas" value={metrics ? money(metrics.revenue) : "—"} hint="Total de pedidos" />
            <StatCard label="Pedidos" value={metrics ? metrics.orders : "—"} />
            <StatCard label="Productos activos" value={metrics ? metrics.products : "—"} />
            <StatCard label="Valor de inventario" value={metrics ? money(metrics.inventory_value) : "—"} hint={metrics ? `${metrics.inventory_units.toLocaleString("es-EC")} unidades` : undefined} />
          </div>

          {metrics && Object.keys(metrics.by_status).length > 0 && (
            <>
              <h2>Pedidos por estado</h2>
              <div className="status-chips">
                {["placed", "confirmed", "preparing", "shipped", "delivered"]
                  .filter((status) => metrics.by_status[status])
                  .map((status) => (
                    <span className="status-chip" key={status}>
                      {STATUS_LABEL[status]}: <strong>{metrics.by_status[status]}</strong>
                    </span>
                  ))}
              </div>
            </>
          )}

          <h2>Guía del panel</h2>
          <p className="dashboard-hint">Para qué sirve cada sección del menú de la izquierda:</p>
          <div className="guide-grid">
            {GUIDE.map((item) => (
              <div className="guide-card" key={item.title}>
                <div className="guide-icon" aria-hidden="true">
                  {item.icon}
                </div>
                <strong>{item.title}</strong>
                <p>{item.desc}</p>
                {item.external ? (
                  <a className="button compact" href={item.href} target="_blank" rel="noreferrer">
                    {item.cta} ↗
                  </a>
                ) : (
                  <Link className="button compact" href={item.href}>
                    {item.cta}
                  </Link>
                )}
              </div>
            ))}
          </div>

          {metrics && metrics.top_products.length > 0 && (
            <>
              <h2>Productos más vendidos</h2>
              {metrics.top_products.map((product) => (
                <div className="row" key={product.name}>
                  <span>{product.name}</span>
                  <span>
                    {product.qty} uds · {money(product.revenue)}
                  </span>
                </div>
              ))}
            </>
          )}

          <h2>Accesos rápidos</h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <a className="button compact" href="/tienda" target="_blank" rel="noreferrer">
              Ver tienda ↗
            </a>
            <Link className="button compact" href="/commerce/orders">
              Gestionar pedidos
            </Link>
            <Link className="button compact" href="/commerce/inventory">
              Ver inventario
            </Link>
            <Link className="button compact" href="/catalog/products">
              Ver productos
            </Link>
          </div>
        </>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </AdminShell>
  );
}
