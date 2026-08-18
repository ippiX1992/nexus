"use client";
import { inputCls } from "@/components/admin/forms";
import { type FormEvent, useEffect, useState } from "react";
import { AdminShell } from "@/components/admin/AdminShell";
import { Button } from "@/components/admin/Button";
import { DataTable, type Column } from "@/components/admin/DataTable";
import { EmptyState } from "@/components/admin/EmptyState";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { type Brand, catalogCommand, catalogContext, catalogCreate, catalogPage, technicalError } from "@/lib/catalog";


export default function Page() {
  const [items, setItems] = useState<Brand[]>([]);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const canManage = permissions.includes("catalog.brand.manage");

  async function load() {
    setLoading(true);
    try {
      const [page, ctx] = await Promise.all([catalogPage<Brand>("/brands"), catalogContext()]);
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
      await catalogCreate("/brands", { code: form.get("code"), name: form.get("name"), slug: form.get("slug") });
      el.reset();
      setShowForm(false);
      await load();
    } catch (e) {
      setError(technicalError(e));
    }
  }
  async function archive(item: Brand) {
    try {
      await catalogCommand(`/brands/${item.id}/archive`, item.version);
      await load();
    } catch (e) {
      setError(technicalError(e));
    }
  }

  const columns: Column<Brand>[] = [
    { key: "name", header: "Nombre", render: (b) => <span className="font-medium text-text">{b.name}</span> },
    { key: "code", header: "Código", render: (b) => <span className="text-muted">{b.code}</span> },
    { key: "status", header: "Estado", render: (b) => <StatusBadge status={b.status} /> },
  ];

  return (
    <AdminShell
      title="Marcas"
      description="Marcas de tu catálogo."
      actions={canManage && <Button variant="primary" onClick={() => setShowForm((v) => !v)}>{showForm ? "Cerrar" : "Nueva marca"}</Button>}
    >
      {showForm && canManage && (
        <form onSubmit={submit} className="mb-5 grid gap-3 rounded-xl border border-line bg-panel p-4 sm:grid-cols-2 lg:grid-cols-3">
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">Código</span><input name="code" required className={inputCls} /></label>
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">Nombre</span><input name="name" required className={inputCls} /></label>
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">Slug</span><input name="slug" required className={inputCls} /></label>
          <div className="flex items-end"><Button variant="primary" type="submit">Crear marca</Button></div>
        </form>
      )}
      <DataTable
        columns={columns}
        rows={items}
        keyField={(b) => b.id}
        loading={loading}
        empty={<EmptyState title="Sin marcas todavía" description="Crea la primera marca de tu catálogo." action={canManage ? <Button variant="primary" onClick={() => setShowForm(true)}>Nueva marca</Button> : undefined} />}
        rowActions={(b) => canManage && b.status !== "archived" ? <Button size="sm" variant="danger" onClick={() => archive(b)}>Archivar</Button> : null}
      />
      {error && <p className="mt-3 text-sm text-red-300" role="alert">{error}</p>}
    </AdminShell>
  );
}
