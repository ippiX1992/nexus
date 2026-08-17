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
  today: { orders: number; revenue: string };
  products: number;
  inventory_value: string;
  inventory_units: number;
  by_status: Record<string, number>;
  top_products: { name: string; qty: number; revenue: string }[];
  recent_orders: { order_number: string; customer_name: string; status: string; total: string; created_at: string }[];
  inventory: { available: number; reserved: number; incoming: number; out_of_stock: number; low_stock: number };
  low_stock_items: { name: string; sku: string; available: number; reserved: number; incoming: number }[];
  transfers_in_transit: number;
};

const money = (v: string | number) => `$${Number(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const units = (v: number) => v.toLocaleString("es-EC");

const STATUS: Record<string, { label: string; cls: string }> = {
  placed: { label: "Recibido", cls: "bg-amber-500/15 text-amber-300" },
  confirmed: { label: "Confirmado", cls: "bg-sky-500/15 text-sky-300" },
  preparing: { label: "En preparación", cls: "bg-indigo-500/15 text-indigo-300" },
  shipped: { label: "Enviado", cls: "bg-violet-500/15 text-violet-300" },
  delivered: { label: "Entregado", cls: "bg-emerald-500/15 text-emerald-300" },
};
const STATUS_ORDER = ["placed", "confirmed", "preparing", "shipped", "delivered"];

// Ayuda breve, plegada al final, para quien todavía no conoce el panel.
const GUIDE = [
  { icon: "🛍️", title: "Tienda", desc: "Tu tienda pública: catálogo, carrito y checkout que ven los clientes." },
  { icon: "📦", title: "Ventas → Pedidos", desc: "Revisa las compras y avanza su estado; el cliente ve el seguimiento en vivo." },
  { icon: "🏷️", title: "Catálogo", desc: "Tus productos, categorías y marcas." },
  { icon: "📥", title: "Inventario", desc: "Stock por bodega, transferencias y recepciones." },
  { icon: "💲", title: "Precios", desc: "Listas de precios y reglas de descuento por tienda o canal." },
  { icon: "🏬", title: "Canales", desc: "Tiendas y mercados donde vendes." },
];

const ATT_TONE: Record<string, string> = {
  warn: "border-amber-500/40 hover:border-amber-400",
  bad: "border-red-500/40 hover:border-red-400",
  info: "border-sky-500/40 hover:border-sky-400",
};

function Badge({ status }: { status: string }) {
  const s = STATUS[status] ?? { label: status, cls: "bg-white/10 text-muted" };
  return <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${s.cls}`}>{s.label}</span>;
}

const act = "inline-flex items-center gap-1 rounded-lg border border-line bg-panel-2 px-3 py-2 text-sm text-text transition hover:border-brand/60 hover:bg-white/5";
const actPrimary = "inline-flex items-center gap-1 rounded-lg bg-brand px-3 py-2 text-sm font-medium text-white transition hover:bg-brand/90";
const h2 = "mt-8 mb-3 text-lg font-semibold text-text";

export default function Page() {
  const [m, setM] = useState<Metrics | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api("/admin/storefront/metrics")
      // Normaliza para tolerar un backend que aún no expone los campos nuevos
      // (evita que el panel se rompa; simplemente muestra ceros hasta reiniciar).
      .then((raw: Partial<Metrics>) =>
        setM({
          orders: raw.orders ?? 0,
          revenue: raw.revenue ?? "0",
          today: raw.today ?? { orders: 0, revenue: "0" },
          products: raw.products ?? 0,
          inventory_value: raw.inventory_value ?? "0",
          inventory_units: raw.inventory_units ?? 0,
          by_status: raw.by_status ?? {},
          top_products: raw.top_products ?? [],
          recent_orders: raw.recent_orders ?? [],
          inventory: raw.inventory ?? { available: 0, reserved: 0, incoming: 0, out_of_stock: 0, low_stock: 0 },
          low_stock_items: raw.low_stock_items ?? [],
          transfers_in_transit: raw.transfers_in_transit ?? 0,
        }),
      )
      .catch((caught) => setError(technicalError(caught)))
      .finally(() => setLoading(false));
  }, []);

  const fecha = new Date().toLocaleDateString("es-EC", { weekday: "long", day: "numeric", month: "long" });

  const pending = m ? (m.by_status.placed ?? 0) + (m.by_status.confirmed ?? 0) + (m.by_status.preparing ?? 0) : 0;
  const attention = m
    ? ([
        pending > 0 && { n: pending, label: pending === 1 ? "pedido pendiente" : "pedidos pendientes", href: "/commerce/orders", tone: "warn", icon: "📦" },
        m.inventory.out_of_stock > 0 && { n: m.inventory.out_of_stock, label: "productos sin stock", href: "/commerce/inventory", tone: "bad", icon: "🚫" },
        m.inventory.low_stock > 0 && { n: m.inventory.low_stock, label: "productos con stock bajo", href: "/commerce/inventory", tone: "warn", icon: "📉" },
        m.transfers_in_transit > 0 && { n: m.transfers_in_transit, label: "transferencias en tránsito", href: "/commerce/transfers", tone: "info", icon: "🚚" },
      ].filter(Boolean) as { n: number; label: string; href: string; tone: string; icon: string }[])
    : [];
  const alertsTotal = attention.reduce((sum, a) => sum + a.n, 0);
  const critical = m ? m.inventory.out_of_stock : 0;

  return (
    <AdminShell title="Inicio" description={`Resumen operativo · Todas las tiendas · Hoy, ${fecha}`}>
      {/* Acciones rápidas del encabezado */}
      <div className="mb-5 flex flex-wrap gap-2">
        <a className={actPrimary} href="/tienda" target="_blank" rel="noreferrer">
          Ver tienda ↗
        </a>
        <Link className={act} href="/commerce/orders">
          Gestionar pedidos
        </Link>
        <Link className={act} href="/catalog/products/new">
          + Nuevo producto
        </Link>
        <Link className={act} href="/commerce/transfers">
          + Transferencia
        </Link>
      </div>

      {loading ? (
        <p className="text-muted">Cargando…</p>
      ) : error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : m ? (
        <>
          {/* Fila 1 — estado del negocio */}
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatCard label="Ventas hoy" value={money(m.today.revenue)} hint={`${m.today.orders} ${m.today.orders === 1 ? "pedido" : "pedidos"} hoy`} icon="💰" tone="brand" />
            <StatCard label="Pedidos pendientes" value={pending} hint={`${m.orders} en total`} icon="📦" tone={pending > 0 ? "warn" : "good"} href="/commerce/orders" />
            <StatCard label="Inventario disponible" value={`${units(m.inventory.available)} uds`} hint={`${units(m.inventory.reserved)} reservadas · ${units(m.inventory.incoming)} en camino`} icon="📥" tone="default" href="/commerce/inventory" />
            <StatCard label="Alertas" value={alertsTotal} hint={critical > 0 ? `${critical} crítica${critical === 1 ? "" : "s"} (sin stock)` : "Sin alertas críticas"} icon="⚠️" tone={critical > 0 ? "bad" : alertsTotal > 0 ? "warn" : "good"} />
          </div>

          {/* Requiere atención */}
          <h2 className={h2}>Requiere atención</h2>
          {attention.length === 0 ? (
            <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-4 text-sm text-emerald-300">
              ✓ Todo en orden: no hay pedidos pendientes ni problemas de stock.
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {attention.map((a) => (
                <Link key={a.label} href={a.href} className={`flex items-center gap-3 rounded-xl border bg-panel-2 p-4 transition ${ATT_TONE[a.tone]}`}>
                  <span aria-hidden className="text-2xl leading-none">
                    {a.icon}
                  </span>
                  <span>
                    <span className="block text-xl font-semibold text-text">{a.n}</span>
                    <span className="block text-sm text-muted">{a.label}</span>
                  </span>
                </Link>
              ))}
            </div>
          )}

          {/* Pedidos por estado + Inventario */}
          <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-2">
            <div>
              <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted">Pedidos por estado</h3>
              {Object.keys(m.by_status).length === 0 ? (
                <p className="text-sm text-muted">Aún no hay pedidos.</p>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {STATUS_ORDER.filter((s) => m.by_status[s]).map((s) => (
                    <span key={s} className={`inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-sm ${STATUS[s].cls}`}>
                      {STATUS[s].label} <strong>{m.by_status[s]}</strong>
                    </span>
                  ))}
                </div>
              )}
            </div>
            <div>
              <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted">Inventario</h3>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                {[
                  { k: "Disponible", v: units(m.inventory.available), c: "text-emerald-300" },
                  { k: "Reservado", v: units(m.inventory.reserved), c: "text-amber-300" },
                  { k: "En camino", v: units(m.inventory.incoming), c: "text-sky-300" },
                  { k: "Sin stock", v: `${m.inventory.out_of_stock} SKU`, c: m.inventory.out_of_stock > 0 ? "text-red-300" : "text-muted" },
                ].map((cell) => (
                  <div key={cell.k} className="rounded-lg border border-line bg-panel-2 p-3">
                    <p className={`text-lg font-semibold ${cell.c}`}>{cell.v}</p>
                    <p className="text-xs text-muted">{cell.k}</p>
                  </div>
                ))}
              </div>
              <Link href="/commerce/inventory" className="mt-3 inline-block text-sm text-brand hover:underline">
                Ver inventario →
              </Link>
            </div>
          </div>

          {/* Productos con menor stock */}
          <h2 className={h2}>Productos con menor stock</h2>
          {m.low_stock_items.length === 0 ? (
            <p className="text-sm text-muted">Ningún producto está por agotarse. 👍</p>
          ) : (
            <div className="overflow-x-auto rounded-xl border border-line">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-muted">
                    <th className="px-3 py-2 font-medium">Producto</th>
                    <th className="px-3 py-2 font-medium">SKU</th>
                    <th className="px-3 py-2 text-right font-medium">Disponible</th>
                    <th className="px-3 py-2 text-right font-medium">Reservado</th>
                    <th className="px-3 py-2 text-right font-medium">En camino</th>
                  </tr>
                </thead>
                <tbody>
                  {m.low_stock_items.map((it) => (
                    <tr key={it.sku} className="border-b border-line/50 last:border-0">
                      <td className="px-3 py-2 text-text">{it.name}</td>
                      <td className="px-3 py-2 text-muted">{it.sku}</td>
                      <td className={`px-3 py-2 text-right font-medium ${it.available <= 0 ? "text-red-300" : "text-amber-300"}`}>{it.available}</td>
                      <td className="px-3 py-2 text-right text-muted">{it.reserved}</td>
                      <td className="px-3 py-2 text-right text-muted">{it.incoming}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Pedidos recientes */}
          <h2 className={h2}>Pedidos recientes</h2>
          {m.recent_orders.length === 0 ? (
            <p className="text-sm text-muted">Cuando alguien compre en la tienda, el pedido aparecerá aquí.</p>
          ) : (
            <div className="overflow-x-auto rounded-xl border border-line">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-muted">
                    <th className="px-3 py-2 font-medium">Pedido</th>
                    <th className="px-3 py-2 font-medium">Cliente</th>
                    <th className="px-3 py-2 text-right font-medium">Total</th>
                    <th className="px-3 py-2 font-medium">Estado</th>
                    <th className="px-3 py-2 font-medium">Fecha</th>
                  </tr>
                </thead>
                <tbody>
                  {m.recent_orders.map((o) => (
                    <tr key={o.order_number} className="border-b border-line/50 last:border-0">
                      <td className="px-3 py-2 font-medium text-text">#{o.order_number}</td>
                      <td className="px-3 py-2 text-muted">{o.customer_name}</td>
                      <td className="px-3 py-2 text-right text-text">{money(o.total)}</td>
                      <td className="px-3 py-2">
                        <Badge status={o.status} />
                      </td>
                      <td className="px-3 py-2 text-muted">{new Date(o.created_at).toLocaleDateString("es-EC", { day: "2-digit", month: "short" })}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="border-t border-line px-3 py-2">
                <Link href="/commerce/orders" className="text-sm text-brand hover:underline">
                  Ver todos los pedidos →
                </Link>
              </div>
            </div>
          )}

          {/* Productos más vendidos */}
          {m.top_products.length > 0 && (
            <>
              <h2 className={h2}>Productos más vendidos</h2>
              <div className="overflow-x-auto rounded-xl border border-line">
                <table className="w-full text-sm">
                  <tbody>
                    {m.top_products.map((p) => (
                      <tr key={p.name} className="border-b border-line/50 last:border-0">
                        <td className="px-3 py-2 text-text">{p.name}</td>
                        <td className="px-3 py-2 text-right text-muted">{p.qty} uds</td>
                        <td className="px-3 py-2 text-right text-text">{money(p.revenue)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {/* Guía plegable */}
          <details className="mt-8 rounded-xl border border-line bg-panel-2 p-4">
            <summary className="cursor-pointer text-sm font-semibold text-text">¿Cómo funciona el panel? (guía rápida)</summary>
            <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {GUIDE.map((item) => (
                <div key={item.title} className="rounded-lg border border-line p-3">
                  <div className="flex items-center gap-2">
                    <span aria-hidden className="text-lg">
                      {item.icon}
                    </span>
                    <strong className="text-sm text-text">{item.title}</strong>
                  </div>
                  <p className="mt-1 text-xs text-muted">{item.desc}</p>
                </div>
              ))}
            </div>
          </details>
        </>
      ) : null}
    </AdminShell>
  );
}
