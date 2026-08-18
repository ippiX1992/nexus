"use client";
import { useEffect, useState } from "react";
import { AdminShell } from "@/components/admin/AdminShell";
import { Button } from "@/components/admin/Button";
import { ConfirmDialog } from "@/components/admin/ConfirmDialog";
import { DataTable, type Column } from "@/components/admin/DataTable";
import { EmptyState } from "@/components/admin/EmptyState";
import { FilterBar, Select } from "@/components/admin/FilterBar";
import { SearchInput } from "@/components/admin/SearchInput";
import { StatusBadge } from "@/components/admin/StatusBadge";
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
  shipping_province?: string | null;
  shipping_city?: string | null;
  shipping_method?: string | null;
  shipping_amount?: string;
  discount_amount?: string;
  coupon_code?: string | null;
  total?: string;
  items: { sku: string; name: string; image: string | null; quantity: number; unit_amount: string | null; line_total: string }[];
  stages: { status: string; label: string; at: string; done: boolean }[];
};

const money = (v: string | number) => `$${Number(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const fecha = (s: string) => new Date(s).toLocaleDateString("es-EC", { day: "2-digit", month: "short", year: "numeric" });

export default function Page() {
  const [orders, setOrders] = useState<Order[]>([]);
  const [detail, setDetail] = useState<OrderDetail | null>(null);
  const [openNumber, setOpenNumber] = useState("");
  const [status, setStatus] = useState("");
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [confirmCancel, setConfirmCancel] = useState("");

  async function load() {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (status) params.set("status", status);
      if (query.trim()) params.set("q", query.trim());
      const qs = params.toString();
      setOrders(await api(`/admin/storefront/orders${qs ? `?${qs}` : ""}`));
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Error");
    } finally {
      setLoading(false);
    }
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    load();
  }, [status]);

  async function toggle(orderNumber: string) {
    if (openNumber === orderNumber) return setOpenNumber("");
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

  async function cancel(orderNumber: string) {
    setBusy(orderNumber);
    setError("");
    try {
      await api(`/admin/storefront/orders/${orderNumber}/cancel`, { method: "POST" });
      setConfirmCancel("");
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Error");
    } finally {
      setBusy("");
    }
  }

  function exportCsv() {
    const header = ["Pedido", "Estado", "Cliente", "Correo", "Articulos", "Total", "Rastreo", "Fecha"];
    const body = orders.map((o) => [o.order_number, o.status, o.customer_name, o.customer_email ?? "", o.item_count, `${o.currency} ${o.subtotal}`, o.tracking_number, new Date(o.placed_at).toLocaleString()]);
    const csv = [header, ...body].map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(",")).join("\n");
    const url = URL.createObjectURL(new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `pedidos-${new Date().toISOString().slice(0, 10)}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }

  const columns: Column<Order>[] = [
    { key: "order_number", header: "Pedido", render: (o) => <span className="font-medium text-text">#{o.order_number}</span> },
    { key: "customer_name", header: "Cliente", render: (o) => o.customer_name },
    { key: "subtotal", header: "Total", align: "right", render: (o) => money(o.subtotal) },
    { key: "status", header: "Estado", render: (o) => <StatusBadge status={o.status} /> },
    { key: "placed_at", header: "Fecha", hideOnMobile: true, render: (o) => <span className="text-muted">{fecha(o.placed_at)}</span> },
  ];

  return (
    <AdminShell
      title="Pedidos"
      description="Compras de la tienda. Al avanzar el estado, el cliente ve el seguimiento en vivo."
      actions={
        <Button variant="secondary" onClick={exportCsv} disabled={orders.length === 0}>
          Exportar CSV
        </Button>
      }
    >
      <FilterBar>
        <SearchInput value={query} onChange={setQuery} onSubmit={load} placeholder="Buscar por cliente o número" className="w-full sm:w-72" />
        <Select value={status} onChange={setStatus} label="Estado">
          <option value="">Todos los estados</option>
          <option value="placed">Recibido</option>
          <option value="confirmed">Confirmado</option>
          <option value="preparing">En preparación</option>
          <option value="shipped">Enviado</option>
          <option value="delivered">Entregado</option>
          <option value="cancelled">Cancelado</option>
        </Select>
      </FilterBar>

      <DataTable
        columns={columns}
        rows={orders}
        keyField={(o) => o.order_number}
        loading={loading}
        onRowClick={(o) => toggle(o.order_number)}
        empty={<EmptyState title="Sin pedidos todavía" description="Cuando alguien compre en la tienda, el pedido aparecerá aquí." />}
        rowActions={(o) => (
          <>
            <Button size="sm" variant="ghost" onClick={() => toggle(o.order_number)}>
              {openNumber === o.order_number ? "Ocultar" : "Ver"}
            </Button>
            {o.status !== "delivered" && o.status !== "cancelled" && (
              <Button size="sm" variant="secondary" disabled={busy === o.order_number} onClick={() => advance(o.order_number)}>
                {busy === o.order_number ? "…" : "Avanzar"}
              </Button>
            )}
            {o.status !== "cancelled" && o.status !== "delivered" && (
              <Button size="sm" variant="danger" onClick={() => setConfirmCancel(o.order_number)}>
                Cancelar
              </Button>
            )}
          </>
        )}
      />

      {openNumber && (
        <div className="mt-4 rounded-xl border border-line bg-panel p-5">
          <div className="mb-5 flex items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <strong className="text-text">Pedido #{openNumber}</strong>
              {detail && <StatusBadge status={detail.status} />}
            </div>
            <Button size="sm" variant="ghost" onClick={() => setOpenNumber("")}>
              Cerrar
            </Button>
          </div>
          {!detail ? (
            <p className="text-sm text-muted">Cargando detalle…</p>
          ) : (
            <div className="grid gap-x-8 gap-y-6 lg:grid-cols-2">
              <section>
                <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Cliente</h4>
                <div className="space-y-0.5 text-sm">
                  <p className="text-text">{detail.customer_name}</p>
                  {detail.customer_email && <p className="text-muted">{detail.customer_email}</p>}
                  {detail.customer_phone && <p className="text-muted">{detail.customer_phone}</p>}
                </div>
              </section>

              <section>
                <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Envío</h4>
                <div className="space-y-0.5 text-sm">
                  <p className="text-text">{detail.shipping_address ?? "Sin dirección"}</p>
                  {(detail.shipping_city || detail.shipping_province) && (
                    <p className="text-muted">{[detail.shipping_city, detail.shipping_province].filter(Boolean).join(", ")}</p>
                  )}
                  {detail.shipping_method && <p className="text-muted">{detail.shipping_method === "galapagos" ? "Galápagos" : "Ecuador continental"}</p>}
                  <p className="text-muted">Rastreo: {detail.tracking_number}</p>
                </div>
              </section>

              <section className="lg:col-span-2">
                <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Productos</h4>
                <div className="divide-y divide-line/60 overflow-hidden rounded-lg border border-line">
                  {detail.items.map((item) => (
                    <div key={item.sku} className="flex items-center gap-3 p-2.5">
                      <span className="grid h-11 w-11 shrink-0 place-items-center overflow-hidden rounded-md bg-white">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        {item.image ? <img src={item.image} alt="" className="h-full w-full object-contain" /> : null}
                      </span>
                      <span className="flex-1 text-sm">
                        <span className="text-text">{item.name}</span>
                        <br />
                        <span className="text-xs text-muted">{item.sku} · x{item.quantity}</span>
                      </span>
                      <strong className="text-text tabular-nums">{money(item.line_total)}</strong>
                    </div>
                  ))}
                </div>
              </section>

              <section>
                <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Totales</h4>
                <dl className="space-y-1 text-sm">
                  <div className="flex justify-between"><dt className="text-muted">Artículos</dt><dd className="text-text tabular-nums">{detail.item_count}</dd></div>
                  <div className="flex justify-between"><dt className="text-muted">Subtotal</dt><dd className="text-text tabular-nums">{money(detail.subtotal)}</dd></div>
                  <div className="flex justify-between"><dt className="text-muted">Envío</dt><dd className="text-text tabular-nums">{money(detail.shipping_amount ?? 0)}</dd></div>
                  {Number(detail.discount_amount ?? 0) > 0 && (
                    <div className="flex justify-between"><dt className="text-muted">Descuento{detail.coupon_code ? ` (${detail.coupon_code})` : ""}</dt><dd className="text-emerald-300 tabular-nums">−{money(detail.discount_amount ?? 0)}</dd></div>
                  )}
                  <div className="flex justify-between border-t border-line pt-1.5"><dt className="font-medium text-text">Total</dt><dd className="font-semibold text-text tabular-nums">{money(detail.total ?? detail.subtotal)}</dd></div>
                </dl>
              </section>

              <section>
                <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Historial</h4>
                <ol className="space-y-2">
                  {detail.stages.map((s) => (
                    <li key={s.status} className="flex items-center gap-2 text-sm">
                      <span className={`h-2 w-2 shrink-0 rounded-full ${s.done ? "bg-emerald-400" : "bg-white/15"}`} />
                      <span className={s.done ? "text-text" : "text-muted"}>{s.label}</span>
                      <span className="ml-auto text-xs text-muted tabular-nums">{new Date(s.at).toLocaleDateString("es-EC", { day: "2-digit", month: "short" })}</span>
                    </li>
                  ))}
                </ol>
              </section>
            </div>
          )}
        </div>
      )}

      {error && (
        <p className="mt-3 text-sm text-red-300" role="alert">
          {error}
        </p>
      )}

      <ConfirmDialog
        open={!!confirmCancel}
        title="Cancelar pedido"
        description={`Se cancelará el pedido #${confirmCancel}. Si no se ha despachado, el stock reservado se libera; si ya se despachó, se restituye.`}
        confirmLabel="Cancelar pedido"
        cancelLabel="Volver"
        busy={busy === confirmCancel}
        onConfirm={() => cancel(confirmCancel)}
        onClose={() => setConfirmCancel("")}
      />
    </AdminShell>
  );
}
