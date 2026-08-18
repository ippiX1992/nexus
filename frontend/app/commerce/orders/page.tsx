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
        <div className="mt-4 rounded-xl border border-line bg-panel p-4">
          <div className="mb-3 flex items-center justify-between">
            <strong className="text-text">Detalle · #{openNumber}</strong>
            <Button size="sm" variant="ghost" onClick={() => setOpenNumber("")}>
              Cerrar
            </Button>
          </div>
          {!detail ? (
            <p className="text-sm text-muted">Cargando detalle…</p>
          ) : (
            <>
              <div className="mb-3 flex flex-wrap gap-2">
                {detail.stages.map((s) => (
                  <StatusBadge key={s.status} status={s.status} tone={s.done ? undefined : "neutral"} />
                ))}
              </div>
              {detail.shipping_address && <p className="mb-3 text-sm text-muted">Envío a: {detail.shipping_address}</p>}
              <div className="divide-y divide-line/60">
                {detail.items.map((item) => (
                  <div key={item.sku} className="flex items-center gap-3 py-2">
                    <span className="grid h-11 w-11 shrink-0 place-items-center overflow-hidden rounded-md bg-white">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      {item.image ? <img src={item.image} alt="" className="h-full w-full object-contain" /> : null}
                    </span>
                    <span className="flex-1 text-sm">
                      <span className="text-text">{item.name}</span>
                      <br />
                      <span className="text-xs text-muted">
                        {item.sku} · x{item.quantity}
                      </span>
                    </span>
                    <strong className="text-text">
                      {detail.currency} {item.line_total}
                    </strong>
                  </div>
                ))}
              </div>
            </>
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
