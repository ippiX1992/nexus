"use client";
import { inputCls } from "@/components/admin/forms";
import { type FormEvent, useEffect, useState } from "react";
import { AdminShell } from "@/components/admin/AdminShell";
import { Button } from "@/components/admin/Button";
import { DataTable, type Column } from "@/components/admin/DataTable";
import { EmptyState } from "@/components/admin/EmptyState";
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

      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted">Niveles de stock</h2>
      <DataTable
        columns={stockCols}
        rows={levels}
        keyField={(s) => s.id}
        loading={loading}
        empty={<EmptyState title="Sin stock todavía" description="Registra una recepción para crear el primer nivel de stock." />}
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
