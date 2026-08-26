"use client";
import { useEffect, useState } from "react";
import { AdminShell } from "@/components/admin/AdminShell";
import { Button, LinkButton } from "@/components/admin/Button";
import { DataTable, type Column } from "@/components/admin/DataTable";
import { StatCard } from "@/components/admin/StatCard";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { api } from "@/lib/api";
import { technicalError } from "@/lib/catalog";

type RecentOrder = { order_number: string; customer_name: string; status: string; total: string; created_at: string };
type LowStock = { name: string; sku: string; available: number; reserved: number; incoming: number };
type Metrics = {
  orders: number;
  today: { orders: number; revenue: string };
  by_status: Record<string, number>;
  recent_orders: RecentOrder[];
  inventory: { available: number; reserved: number; incoming: number; out_of_stock: number; low_stock: number };
  low_stock_items: LowStock[];
  transfers_in_transit: number;
};

const money = (v: string | number) => `$${Number(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const units = (v: number) => v.toLocaleString("es-EC");

const ATT_TONE: Record<string, string> = {
  warn: "border-amber-500/40 hover:border-amber-400",
  bad: "border-red-500/40 hover:border-red-400",
  info: "border-sky-500/40 hover:border-sky-400",
};

export default function Page() {
  const [m, setM] = useState<Metrics | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api("/admin/storefront/metrics")
      .then((raw: Partial<Metrics>) =>
        setM({
          orders: raw.orders ?? 0,
          today: raw.today ?? { orders: 0, revenue: "0" },
          by_status: raw.by_status ?? {},
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
        m.inventory.out_of_stock > 0 && { n: m.inventory.out_of_stock, label: "productos sin stock", href: "/commerce/inventory?status=out_of_stock", tone: "bad", icon: "🚫" },
        m.inventory.low_stock > 0 && { n: m.inventory.low_stock, label: "productos con stock bajo", href: "/commerce/inventory?status=low_stock", tone: "warn", icon: "📉" },
        m.transfers_in_transit > 0 && { n: m.transfers_in_transit, label: "transferencias en tránsito", href: "/commerce/transfers", tone: "info", icon: "🚚" },
      ].filter(Boolean) as { n: number; label: string; href: string; tone: string; icon: string }[])
    : [];
  const alertsTotal = attention.reduce((s, a) => s + a.n, 0);
  const critical = m ? m.inventory.out_of_stock : 0;

  const recentCols: Column<RecentOrder>[] = [
    { key: "order_number", header: "Pedido", render: (o) => <span className="font-medium text-text">#{o.order_number}</span> },
    { key: "customer_name", header: "Cliente", render: (o) => <span className="text-muted">{o.customer_name}</span>, hideOnMobile: true },
    { key: "total", header: "Total", align: "right", render: (o) => money(o.total) },
    { key: "status", header: "Estado", render: (o) => <StatusBadge status={o.status} /> },
  ];
  const lowCols: Column<LowStock>[] = [
    { key: "name", header: "Producto", render: (r) => <span className="text-text">{r.name}</span> },
    { key: "sku", header: "SKU", render: (r) => <span className="text-muted">{r.sku}</span>, hideOnMobile: true },
    { key: "available", header: "Disponible", align: "right", render: (r) => <span className={r.available <= 0 ? "text-red-300" : "text-amber-300"}>{r.available}</span> },
    { key: "reserved", header: "Reservado", align: "right", render: (r) => <span className="text-muted">{r.reserved}</span>, hideOnMobile: true },
  ];

  const actions = (
    <>
      <LinkButton href="/tienda" external variant="primary">
        Ver tienda ↗
      </LinkButton>
      <LinkButton href="/commerce/orders">Gestionar pedidos</LinkButton>
    </>
  );

  return (
    <AdminShell title="Inicio" description={`Resumen operativo · Todas las tiendas · Hoy, ${fecha}`} actions={actions}>
      {loading ? (
        <p className="text-muted">Cargando…</p>
      ) : error ? (
        <p className="text-sm text-red-300" role="alert">
          {error}
        </p>
      ) : m ? (
        <>
          {/* KPIs */}
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatCard label="Ventas hoy" value={money(m.today.revenue)} hint={`${m.today.orders} ${m.today.orders === 1 ? "pedido" : "pedidos"} hoy`} icon="💰" tone="brand" />
            <StatCard label="Pedidos pendientes" value={pending} hint={`${m.orders} en total`} icon="📦" tone={pending > 0 ? "warn" : "good"} href="/commerce/orders" />
            <StatCard label="Inventario disponible" value={`${units(m.inventory.available)} uds`} hint={`${units(m.inventory.reserved)} reservadas`} icon="📥" href="/commerce/inventory" />
            <StatCard label="Alertas" value={alertsTotal} hint={critical > 0 ? `${critical} crítica${critical === 1 ? "" : "s"}` : "Sin alertas críticas"} icon="⚠️" tone={critical > 0 ? "bad" : alertsTotal > 0 ? "warn" : "good"} />
          </div>

          {/* Requiere atención */}
          <h2 className="mt-8 mb-3 text-lg font-semibold text-text">Requiere atención</h2>
          {attention.length === 0 ? (
            <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-4 text-sm text-emerald-300">✓ Todo en orden: sin pedidos pendientes ni problemas de stock.</div>
          ) : (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {attention.map((a) => (
                <a key={a.label} href={a.href} className={`flex items-center gap-3 rounded-xl border bg-panel-2 p-4 transition ${ATT_TONE[a.tone]}`}>
                  <span aria-hidden className="text-2xl leading-none">
                    {a.icon}
                  </span>
                  <span>
                    <span className="block text-xl font-semibold text-text">{a.n}</span>
                    <span className="block text-sm text-muted">{a.label}</span>
                  </span>
                </a>
              ))}
            </div>
          )}

          {/* Pedidos recientes | Inventario */}
          <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="text-lg font-semibold text-text">Pedidos recientes</h2>
                <a href="/commerce/orders" className="text-sm text-brand hover:underline">
                  Ver todos →
                </a>
              </div>
              <DataTable columns={recentCols} rows={m.recent_orders} keyField={(o) => o.order_number} empty={<div className="rounded-xl border border-line p-6 text-sm text-muted">Aún no hay pedidos.</div>} />
            </div>
            <div>
              <h2 className="mb-3 text-lg font-semibold text-text">Inventario</h2>
              <div className="grid grid-cols-2 gap-3">
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
              <div className="mt-3">
                <Button size="sm" onClick={() => (window.location.href = "/commerce/inventory")}>
                  Ver inventario →
                </Button>
              </div>
            </div>
          </div>

          {/* Productos con stock bajo */}
          <div className="mt-8 mb-3 flex items-center justify-between">
            <h2 className="text-lg font-semibold text-text">Productos con stock bajo</h2>
            <a href="/commerce/inventory" className="text-sm text-brand hover:underline">
              Ver inventario →
            </a>
          </div>
          <DataTable columns={lowCols} rows={m.low_stock_items} keyField={(r) => r.sku} empty={<div className="rounded-xl border border-line p-6 text-sm text-muted">Ningún producto está por agotarse. 👍</div>} />
        </>
      ) : null}
    </AdminShell>
  );
}
