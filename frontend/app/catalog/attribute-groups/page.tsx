"use client";
import { type FormEvent, useEffect, useState } from "react";
import { AdminShell } from "@/components/admin/AdminShell";
import { Button } from "@/components/admin/Button";
import { DataTable, type Column } from "@/components/admin/DataTable";
import { EmptyState } from "@/components/admin/EmptyState";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { type AttributeGroup, catalogCommand, catalogContext, catalogCreate, catalogPage, technicalError } from "@/lib/catalog";

const inputCls = "rounded-lg border border-line bg-bg px-3 py-2 text-sm text-text focus:border-brand focus:outline-none";

export default function Page() {
  const [items, setItems] = useState<AttributeGroup[]>([]);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const canManage = permissions.includes("catalog.attribute_group.create") || permissions.includes("catalog.attribute_group.update");
  const canArchive = permissions.includes("catalog.attribute_group.archive");

  async function load() {
    setLoading(true);
    try {
      const [page, ctx] = await Promise.all([catalogPage<AttributeGroup>("/attribute-groups"), catalogContext()]);
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
      await catalogCreate("/attribute-groups", { code: form.get("code"), name: form.get("name") });
      el.reset();
      setShowForm(false);
      await load();
    } catch (e) {
      setError(technicalError(e));
    }
  }
  async function command(item: AttributeGroup, kind: "archive" | "restore") {
    try {
      await catalogCommand(`/attribute-groups/${item.id}/${kind}`, item.version);
      await load();
    } catch (e) {
      setError(technicalError(e));
    }
  }

  const columns: Column<AttributeGroup>[] = [
    { key: "name", header: "Nombre", render: (g) => <span className="font-medium text-text">{g.name}</span> },
    { key: "code", header: "Código", render: (g) => <span className="text-muted">{g.code}</span> },
    { key: "status", header: "Estado", render: (g) => <StatusBadge status={g.status} /> },
  ];

  return (
    <AdminShell
      title="Grupos de atributos"
      description="Agrupan especificaciones relacionadas (Dimensiones, Eléctrico, Garantía)."
      actions={canManage && <Button variant="primary" onClick={() => setShowForm((v) => !v)}>{showForm ? "Cerrar" : "Nuevo grupo"}</Button>}
    >
      {showForm && canManage && (
        <form onSubmit={submit} className="mb-5 grid gap-3 rounded-xl border border-line bg-panel p-4 sm:grid-cols-2 lg:grid-cols-3">
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">Código</span><input name="code" required className={inputCls} /></label>
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">Nombre</span><input name="name" required className={inputCls} /></label>
          <div className="flex items-end"><Button variant="primary" type="submit">Crear grupo</Button></div>
        </form>
      )}
      <DataTable
        columns={columns}
        rows={items}
        keyField={(g) => g.id}
        loading={loading}
        empty={<EmptyState title="Sin grupos de atributos" description="Crea el primero para organizar las especificaciones." action={canManage ? <Button variant="primary" onClick={() => setShowForm(true)}>Nuevo grupo</Button> : undefined} />}
        rowActions={(g) => (
          <>
            {canArchive && g.status !== "archived" && <Button size="sm" variant="danger" onClick={() => command(g, "archive")}>Archivar</Button>}
            {canArchive && g.status === "archived" && <Button size="sm" variant="secondary" onClick={() => command(g, "restore")}>Restaurar</Button>}
          </>
        )}
      />
      {error && <p className="mt-3 text-sm text-red-300" role="alert">{error}</p>}
    </AdminShell>
  );
}
