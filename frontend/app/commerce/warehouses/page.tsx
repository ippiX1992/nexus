"use client";
import { inputCls } from "@/components/admin/forms";
import { type FormEvent, useEffect, useState } from "react";
import { AdminShell } from "@/components/admin/AdminShell";
import { Button, LinkButton } from "@/components/admin/Button";
import { DataTable, type Column } from "@/components/admin/DataTable";
import { EmptyState } from "@/components/admin/EmptyState";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { api } from "@/lib/api";
import { type Warehouse, inventoryCommand, inventoryCreate, inventoryPage, technicalError } from "@/lib/inventory";


export default function Page() {
  const [items, setItems] = useState<Warehouse[]>([]);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const canManage = permissions.includes("inventory.warehouse.create");
  const canArchive = permissions.includes("inventory.warehouse.archive");

  async function load() {
    setLoading(true);
    try {
      const [page, ctx] = await Promise.all([inventoryPage<Warehouse>("/warehouses"), api("/me/context")]);
      setItems(page.items);
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

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const el = event.currentTarget;
    const form = new FormData(el);
    try {
      await inventoryCreate("/warehouses", { code: form.get("code"), name: form.get("name"), country_code: form.get("country_code") || null });
      el.reset();
      setShowForm(false);
      await load();
    } catch (e) {
      setError(technicalError(e));
    }
  }
  async function archive(item: Warehouse) {
    try {
      await inventoryCommand(`/warehouses/${item.id}/archive`, item.version);
      await load();
    } catch (e) {
      setError(technicalError(e));
    }
  }

  const columns: Column<Warehouse>[] = [
    { key: "name", header: "Nombre", render: (w) => <span className="font-medium text-text">{w.name}</span> },
    { key: "code", header: "Código", render: (w) => <span className="text-muted">{w.code}</span> },
    { key: "country_code", header: "País", render: (w) => <span className="text-muted">{w.country_code ?? "—"}</span>, hideOnMobile: true },
    { key: "status", header: "Estado", render: (w) => <StatusBadge status={w.status} /> },
  ];

  return (
    <AdminShell
      title="Bodegas"
      description="Centros físicos o lógicos que guardan stock. Cada bodega agrupa ubicaciones y sirve a una o más tiendas."
      actions={canManage && <Button variant="primary" onClick={() => setShowForm((v) => !v)}>{showForm ? "Cerrar" : "Nueva bodega"}</Button>}
    >
      {showForm && canManage && (
        <form onSubmit={submit} className="mb-5 grid gap-3 rounded-xl border border-line bg-panel p-4 sm:grid-cols-2 lg:grid-cols-3">
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">Código</span><input name="code" required className={inputCls} /></label>
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">Nombre</span><input name="name" required className={inputCls} /></label>
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">País (ISO, opcional)</span><input name="country_code" maxLength={2} className={inputCls} /></label>
          <div className="flex items-end"><Button variant="primary" type="submit">Crear bodega</Button></div>
        </form>
      )}
      <DataTable
        columns={columns}
        rows={items}
        keyField={(w) => w.id}
        loading={loading}
        onRowClick={(w) => { window.location.href = `/commerce/warehouses/${w.id}`; }}
        empty={<EmptyState title="Sin bodegas todavía" description="Crea la primera para empezar a registrar stock." action={canManage ? <Button variant="primary" onClick={() => setShowForm(true)}>Nueva bodega</Button> : undefined} />}
        rowActions={(w) => (
          <>
            <LinkButton href={`/commerce/warehouses/${w.id}`} size="sm" variant="ghost">Ubicaciones</LinkButton>
            {canArchive && w.status !== "archived" && <Button size="sm" variant="danger" onClick={() => archive(w)}>Archivar</Button>}
          </>
        )}
      />
      {error && <p className="mt-3 text-sm text-red-300" role="alert">{error}</p>}
    </AdminShell>
  );
}
