"use client";
import { inputCls } from "@/components/admin/forms";
import { type FormEvent, useEffect, useState } from "react";
import { AdminShell } from "@/components/admin/AdminShell";
import { Button } from "@/components/admin/Button";
import { DataTable, type Column } from "@/components/admin/DataTable";
import { EmptyState } from "@/components/admin/EmptyState";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { api } from "@/lib/api";
import { type Location, type Transfer, type Warehouse, inventoryCommand, inventoryCreate, inventoryPage, technicalError } from "@/lib/inventory";


export default function Page() {
  const [items, setItems] = useState<Transfer[]>([]);
  const [locations, setLocations] = useState<Location[]>([]);
  const [warehouses, setWarehouses] = useState<Warehouse[]>([]);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const canManage = permissions.includes("inventory.transfer.manage");

  async function load() {
    setLoading(true);
    try {
      const [transferPage, locationPage, warehousePage, ctx] = await Promise.all([
        inventoryPage<Transfer>("/transfers"),
        inventoryPage<Location>("/locations"),
        inventoryPage<Warehouse>("/warehouses"),
        api("/me/context"),
      ]);
      setItems(transferPage.items);
      setLocations(locationPage.items);
      setWarehouses(warehousePage.items);
      setPermissions(ctx.permissions);
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

  const locationLabel = (id: string) => {
    const loc = locations.find((l) => l.id === id);
    const wh = loc && warehouses.find((w) => w.id === loc.warehouse_id);
    return loc ? `${wh ? `${wh.code} / ` : ""}${loc.name}` : "—";
  };

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const el = event.currentTarget;
    const form = new FormData(el);
    try {
      await inventoryCreate("/transfers", {
        from_location_id: form.get("from_location_id"),
        to_location_id: form.get("to_location_id"),
        variant_id: form.get("variant_id"),
        quantity: Number(form.get("quantity")),
        reason: form.get("reason") || undefined,
      });
      el.reset();
      setShowForm(false);
      await load();
    } catch (e) {
      setError(technicalError(e));
    }
  }
  async function act(item: Transfer, kind: "complete" | "cancel") {
    setBusy(item.id);
    try {
      await inventoryCommand(`/transfers/${item.id}/${kind}`, item.version);
      await load();
    } catch (e) {
      setError(technicalError(e));
    } finally {
      setBusy("");
    }
  }

  const activeLocations = locations.filter((l) => l.status !== "archived");
  const columns: Column<Transfer>[] = [
    { key: "from", header: "Origen", render: (t) => <span className="font-medium text-text">{locationLabel(t.from_location_id)}</span> },
    { key: "to", header: "Destino", render: (t) => <span className="text-muted">{locationLabel(t.to_location_id)}</span> },
    { key: "quantity", header: "Unidades", align: "right", render: (t) => t.quantity },
    { key: "status", header: "Estado", render: (t) => <StatusBadge status={t.status} /> },
    { key: "created_at", header: "Fecha", hideOnMobile: true, render: (t) => <span className="text-muted">{new Date(t.created_at).toLocaleDateString("es-EC", { day: "2-digit", month: "short", year: "numeric" })}</span> },
  ];

  return (
    <AdminShell
      title="Transferencias"
      description="Mueve stock entre ubicaciones. En tránsito sale del origen y llega como “en camino” al destino; al completar aterriza en stock."
      actions={canManage && <Button variant="primary" onClick={() => setShowForm((v) => !v)}>{showForm ? "Cerrar" : "Nueva transferencia"}</Button>}
    >
      {showForm && canManage && (
        <form onSubmit={submit} className="mb-5 grid gap-3 rounded-xl border border-line bg-panel p-4 sm:grid-cols-2 lg:grid-cols-3">
          <label className="grid gap-1.5 text-sm">
            <span className="font-medium text-text">Origen</span>
            <select name="from_location_id" required className={inputCls}>
              <option value="">Selecciona…</option>
              {activeLocations.map((l) => <option key={l.id} value={l.id}>{locationLabel(l.id)}</option>)}
            </select>
          </label>
          <label className="grid gap-1.5 text-sm">
            <span className="font-medium text-text">Destino</span>
            <select name="to_location_id" required className={inputCls}>
              <option value="">Selecciona…</option>
              {activeLocations.map((l) => <option key={l.id} value={l.id}>{locationLabel(l.id)}</option>)}
            </select>
          </label>
          <label className="grid gap-1.5 text-sm">
            <span className="font-medium text-text">ID del producto (variant)</span>
            <input name="variant_id" placeholder="uuid del variant" required className={inputCls} />
          </label>
          <label className="grid gap-1.5 text-sm">
            <span className="font-medium text-text">Cantidad</span>
            <input name="quantity" type="number" min={1} required className={inputCls} />
          </label>
          <label className="grid gap-1.5 text-sm">
            <span className="font-medium text-text">Motivo</span>
            <input name="reason" maxLength={500} className={inputCls} />
          </label>
          <div className="flex items-end">
            <Button variant="primary" type="submit">Crear transferencia</Button>
          </div>
        </form>
      )}

      <DataTable
        columns={columns}
        rows={items}
        keyField={(t) => t.id}
        loading={loading}
        empty={<EmptyState title="Sin transferencias" description="Crea una para mover stock entre ubicaciones." action={canManage ? <Button variant="primary" onClick={() => setShowForm(true)}>Nueva transferencia</Button> : undefined} />}
        rowActions={(t) =>
          canManage && t.status === "in_transit" ? (
            <>
              <Button size="sm" variant="secondary" disabled={busy === t.id} onClick={() => act(t, "complete")}>
                Completar
              </Button>
              <Button size="sm" variant="danger" disabled={busy === t.id} onClick={() => act(t, "cancel")}>
                Cancelar
              </Button>
            </>
          ) : null
        }
      />
      {error && (
        <p className="mt-3 text-sm text-red-300" role="alert">
          {error}
        </p>
      )}
    </AdminShell>
  );
}
