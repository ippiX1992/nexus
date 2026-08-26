"use client";
import { inputCls } from "@/components/admin/forms";
import { type FormEvent, useEffect, useState } from "react";
import { AdminShell } from "@/components/admin/AdminShell";
import { Button } from "@/components/admin/Button";
import { DataTable, type Column } from "@/components/admin/DataTable";
import { EmptyState } from "@/components/admin/EmptyState";
import { FilterBar } from "@/components/admin/FilterBar";
import { SearchInput } from "@/components/admin/SearchInput";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { api } from "@/lib/api";
import { variantLabels } from "@/lib/catalog";
import { type LedgerEntry, type Location, type StockLevel, type Warehouse, inventoryAction, inventoryPage, technicalError } from "@/lib/inventory";


export default function Page() {
  const [warehouses, setWarehouses] = useState<Warehouse[]>([]);
  const [locations, setLocations] = useState<Location[]>([]);
  const [levels, setLevels] = useState<StockLevel[]>([]);
  const [ledger, setLedger] = useState<LedgerEntry[]>([]);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [names, setNames] = useState<Map<string, string>>(new Map());
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const canAdjust = permissions.includes("inventory.stock.adjust");
  const canRecount = permissions.includes("inventory.stock.recount");

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [warehouseFilter, setWarehouseFilter] = useState("");
  const [sortLow, setSortLow] = useState(false);

  useEffect(() => {
    const st = new URLSearchParams(window.location.search).get("status");
    if (st) setStatusFilter(st);
  }, []);

  async function load() {
    setLoading(true);
    try {
      const [levelPage, ledgerPage, warehousePage, locationPage, ctx, labels] = await Promise.all([
        inventoryPage<StockLevel>("/stock"),
        inventoryPage<LedgerEntry>("/ledger"),
        inventoryPage<Warehouse>("/warehouses"),
        inventoryPage<Location>("/locations"),
        api("/me/context"),
        variantLabels().catch(() => new Map<string, string>()),
      ]);
      setLevels(levelPage.items);
      setLedger(ledgerPage.items);
      setWarehouses(warehousePage.items);
      setLocations(locationPage.items);
      setPermissions(ctx.permissions);
      setNames(labels);
      setError("");
    } catch (e) {
      setError(technicalError(e));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    load();
  }, []);

  const label = (id: string) => names.get(id) ?? "";
  const productName = (id: string) => label(id).split(" · ")[0] || "—";
  const productSku = (id: string) => label(id).split(" · ").slice(1).join(" · ") || "—";
  const warehouseFor = (locationId: string) => {
    const loc = locations.find((l) => l.id === locationId);
    const wh = loc && warehouses.find((w) => w.id === loc.warehouse_id);
    return loc ? `${wh ? `${wh.code} · ` : ""}${loc.name}` : "—";
  };
  const stockStatus = (a: number) => (a <= 0 ? "out_of_stock" : a <= 5 ? "low_stock" : "in_stock");

  let visibleLevels = levels;
  if (search.trim()) {
    const term = search.trim().toLowerCase();
    visibleLevels = visibleLevels.filter((s) => `${productName(s.variant_id)} ${productSku(s.variant_id)}`.toLowerCase().includes(term));
  }
  if (statusFilter) visibleLevels = visibleLevels.filter((s) => stockStatus(s.available) === statusFilter);
  if (warehouseFilter) visibleLevels = visibleLevels.filter((s) => locations.find((l) => l.id === s.location_id)?.warehouse_id === warehouseFilter);
  if (sortLow) visibleLevels = [...visibleLevels].sort((a, b) => a.available - b.available);
  const hasStockFilters = !!(search || statusFilter || warehouseFilter);

  function exportStockCsv() {
    const header = ["Producto", "SKU", "Bodega", "Disponible", "Reservado", "Estado"];
    const body = visibleLevels.map((s) => [productName(s.variant_id), productSku(s.variant_id), warehouseFor(s.location_id), s.available, s.reserved, stockStatus(s.available)]);
    const csv = [header, ...body].map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(",")).join("\n");
    const url = URL.createObjectURL(new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `stock-${new Date().toISOString().slice(0, 10)}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }

  async function submitMovement(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const el = event.currentTarget;
    const form = new FormData(el);
    const kind = String(form.get("kind"));
    const loc = String(form.get("location_id"));
    const variant = String(form.get("variant_id"));
    const amount = Number(form.get("amount"));
    const reason = form.get("reason") || undefined;
    try {
      if (kind === "receive") await inventoryAction(`/locations/${loc}/variants/${variant}/receive`, { quantity: amount, reason });
      else if (kind === "adjust") await inventoryAction(`/locations/${loc}/variants/${variant}/adjust`, { delta: amount, reason });
      else await inventoryAction(`/locations/${loc}/variants/${variant}/recount`, { counted: amount, reason });
      el.reset();
      setShowForm(false);
      await load();
    } catch (e) {
      setError(technicalError(e));
    }
  }

  const stockCols: Column<StockLevel>[] = [
    { key: "name", header: "Producto", render: (s) => <span className="font-medium text-text">{productName(s.variant_id)}</span> },
    { key: "sku", header: "SKU", render: (s) => <span className="text-muted">{productSku(s.variant_id)}</span>, hideOnMobile: true },
    { key: "warehouse", header: "Bodega", render: (s) => <span className="text-muted">{warehouseFor(s.location_id)}</span>, hideOnMobile: true },
    { key: "available", header: "Disponible", align: "right", render: (s) => <span className={s.available <= 0 ? "text-red-300" : s.available <= 5 ? "text-amber-300" : "text-text"}>{s.available}</span> },
    { key: "reserved", header: "Reservado", align: "right", render: (s) => <span className="text-muted">{s.reserved}</span> },
    { key: "estado", header: "Estado", render: (s) => <StatusBadge status={stockStatus(s.available)} /> },
  ];
  const ledgerCols: Column<LedgerEntry>[] = [
    { key: "entry_type", header: "Movimiento", render: (e) => <span className="text-text">{e.entry_type}</span> },
    { key: "delta", header: "Cantidad", align: "right", render: (e) => (e.quantity_delta >= 0 ? `+${e.quantity_delta}` : e.quantity_delta) },
    { key: "on_hand_after", header: "Stock final", align: "right", render: (e) => e.on_hand_after, hideOnMobile: true },
    { key: "location", header: "Ubicación", render: (e) => <span className="text-muted">{warehouseFor(e.location_id)}</span>, hideOnMobile: true },
    { key: "created_at", header: "Fecha", render: (e) => <span className="text-muted">{new Date(e.created_at).toLocaleDateString("es-EC", { day: "2-digit", month: "short" })}</span>, hideOnMobile: true },
  ];

  return (
    <AdminShell
      title="Stock"
      description="Stock disponible por producto y bodega. Disponible = en mano − reservado."
      actions={(canAdjust || canRecount) && <Button variant="primary" onClick={() => setShowForm((v) => !v)}>{showForm ? "Cerrar" : "Registrar movimiento"}</Button>}
    >
      {showForm && (canAdjust || canRecount) && (
        <form onSubmit={submitMovement} className="mb-5 grid gap-3 rounded-xl border border-line bg-panel p-4 sm:grid-cols-2 lg:grid-cols-3">
          <label className="grid gap-1.5 text-sm">
            <span className="font-medium text-text">Tipo</span>
            <select name="kind" defaultValue="receive" className={inputCls}>
              <option value="receive">Recepción (+)</option>
              <option value="adjust">Ajuste (±)</option>
              <option value="recount">Recuento (=)</option>
            </select>
          </label>
          <label className="grid gap-1.5 text-sm">
            <span className="font-medium text-text">Ubicación</span>
            <select name="location_id" required className={inputCls}>
              <option value="">Selecciona…</option>
              {locations.filter((l) => l.status !== "archived").map((l) => {
                const wh = warehouses.find((w) => w.id === l.warehouse_id);
                return (
                  <option key={l.id} value={l.id}>
                    {wh ? `${wh.code} / ` : ""}
                    {l.name}
                  </option>
                );
              })}
            </select>
          </label>
          <label className="grid gap-1.5 text-sm">
            <span className="font-medium text-text">ID del producto (variant)</span>
            <input name="variant_id" placeholder="uuid del variant" required className={inputCls} />
          </label>
          <label className="grid gap-1.5 text-sm">
            <span className="font-medium text-text">Cantidad</span>
            <input name="amount" type="number" required className={inputCls} />
          </label>
          <label className="grid gap-1.5 text-sm">
            <span className="font-medium text-text">Motivo</span>
            <input name="reason" maxLength={500} className={inputCls} />
          </label>
          <div className="flex items-end">
            <Button variant="primary" type="submit">Aplicar movimiento</Button>
          </div>
        </form>
      )}

      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Niveles de stock</h2>
        <button type="button" onClick={exportStockCsv} className="w-fit shrink-0 rounded-lg border border-line px-3 py-1.5 text-xs font-semibold text-text hover:bg-panel-2">
          Exportar CSV
        </button>
      </div>
      <FilterBar>
        <SearchInput value={search} onChange={setSearch} onSubmit={() => {}} placeholder="Buscar producto o SKU" className="w-full sm:w-64" />
        <select aria-label="Estado" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className={inputCls}>
          <option value="">Todos los estados</option>
          <option value="in_stock">En stock</option>
          <option value="low_stock">Stock bajo</option>
          <option value="out_of_stock">Sin stock</option>
        </select>
        <select aria-label="Bodega" value={warehouseFilter} onChange={(e) => setWarehouseFilter(e.target.value)} className={inputCls}>
          <option value="">Todas las bodegas</option>
          {warehouses.filter((w) => w.status !== "archived").map((w) => (
            <option key={w.id} value={w.id}>
              {w.code ? `${w.code} · ${w.name}` : w.name}
            </option>
          ))}
        </select>
        <label className="flex items-center gap-2 text-sm text-muted">
          <input type="checkbox" checked={sortLow} onChange={(e) => setSortLow(e.target.checked)} />
          Menor stock primero
        </label>
      </FilterBar>
      <DataTable
        columns={stockCols}
        rows={visibleLevels}
        keyField={(s) => s.id}
        loading={loading}
        stickyHeader
        empty={
          <EmptyState
            title={hasStockFilters ? "Sin resultados" : "Sin stock todavía"}
            description={hasStockFilters ? "Ningún producto coincide con los filtros." : "Registra una recepción para crear el primer nivel de stock."}
          />
        }
      />

      <h2 className="mb-3 mt-8 text-sm font-semibold uppercase tracking-wide text-muted">Movimientos recientes</h2>
      <DataTable
        columns={ledgerCols}
        rows={ledger}
        keyField={(e) => e.id}
        empty={<EmptyState title="Sin movimientos" description="Cada recepción, ajuste, recuento, transferencia o reserva aparecerá aquí." />}
      />

      {error && (
        <p className="mt-3 text-sm text-red-300" role="alert">
          {error}
        </p>
      )}
    </AdminShell>
  );
}
