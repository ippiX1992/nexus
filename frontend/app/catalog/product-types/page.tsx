"use client";
import { type FormEvent, useEffect, useState } from "react";
import { AdminShell } from "@/components/admin/AdminShell";
import { Button } from "@/components/admin/Button";
import { DataTable, type Column } from "@/components/admin/DataTable";
import { EmptyState } from "@/components/admin/EmptyState";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { type Attribute, catalogCommand, catalogContext, catalogCreate, catalogGet, catalogPage, catalogUpdate, type ProductType, type ProductTypeAttribute, technicalError } from "@/lib/catalog";

const inputCls = "rounded-lg border border-line bg-bg px-3 py-2 text-sm text-text focus:border-brand focus:outline-none";

export default function Page() {
  const [items, setItems] = useState<ProductType[]>([]);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [attributes, setAttributes] = useState<Attribute[]>([]);
  const [expanded, setExpanded] = useState<ProductType | null>(null);
  const [assigned, setAssigned] = useState<ProductTypeAttribute[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const canManage = permissions.includes("catalog.product_type.manage");
  const canManageAttributes = permissions.includes("catalog.product_type_attribute.manage");

  async function load() {
    setLoading(true);
    try {
      const [page, ctx, attributePage] = await Promise.all([catalogPage<ProductType>("/product-types"), catalogContext(), catalogPage<Attribute>("/attributes")]);
      setItems(page.items);
      setPermissions(ctx.permissions);
      setAttributes(attributePage.items.filter((item) => item.status !== "archived"));
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
      await catalogCreate("/product-types", { code: form.get("code"), name: form.get("name"), description: form.get("description") || null });
      el.reset();
      setShowForm(false);
      await load();
    } catch (e) {
      setError(technicalError(e));
    }
  }
  async function archive(item: ProductType) {
    try {
      await catalogCommand(`/product-types/${item.id}/archive`, item.version);
      await load();
    } catch (e) {
      setError(technicalError(e));
    }
  }
  async function toggleAttributes(item: ProductType) {
    if (expanded?.id === item.id) return setExpanded(null);
    try {
      setAssigned(await catalogGet<ProductTypeAttribute[]>(`/product-types/${item.id}/attributes`));
      setExpanded(item);
    } catch (e) {
      setError(technicalError(e));
    }
  }
  async function saveAttributes(item: ProductType, next: { attribute_id: string; group_id?: string | null; position: number; required: boolean }[]) {
    try {
      await catalogUpdate(`/product-types/${item.id}/attributes`, { attributes: next }, item.version, "PUT");
      await load();
      setAssigned(await catalogGet<ProductTypeAttribute[]>(`/product-types/${item.id}/attributes`));
    } catch (e) {
      setError(technicalError(e));
    }
  }
  const asPayload = () => assigned.map((a) => ({ attribute_id: a.attribute_id, group_id: a.group_id, position: a.position, required: a.required }));

  const columns: Column<ProductType>[] = [
    { key: "name", header: "Nombre", render: (t) => <span className="font-medium text-text">{t.name}</span> },
    { key: "code", header: "Código", render: (t) => <span className="text-muted">{t.code}</span> },
    { key: "status", header: "Estado", render: (t) => <StatusBadge status={t.status} /> },
  ];

  return (
    <AdminShell
      title="Tipos de producto"
      description="Define qué atributos aplican a cada tipo de producto."
      actions={canManage && <Button variant="primary" onClick={() => setShowForm((v) => !v)}>{showForm ? "Cerrar" : "Nuevo tipo"}</Button>}
    >
      {showForm && canManage && (
        <form onSubmit={submit} className="mb-5 grid gap-3 rounded-xl border border-line bg-panel p-4 sm:grid-cols-2 lg:grid-cols-3">
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">Código</span><input name="code" required className={inputCls} /></label>
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">Nombre</span><input name="name" required className={inputCls} /></label>
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">Descripción</span><input name="description" className={inputCls} /></label>
          <div className="flex items-end"><Button variant="primary" type="submit">Crear tipo</Button></div>
        </form>
      )}
      <DataTable
        columns={columns}
        rows={items}
        keyField={(t) => t.id}
        loading={loading}
        empty={<EmptyState title="Sin tipos de producto" description="Crea el primero para empezar a definir productos." action={canManage ? <Button variant="primary" onClick={() => setShowForm(true)}>Nuevo tipo</Button> : undefined} />}
        rowActions={(t) => (
          <>
            <Button size="sm" variant="ghost" onClick={() => toggleAttributes(t)}>{expanded?.id === t.id ? "Ocultar" : "Atributos"}</Button>
            {canManage && t.status !== "archived" && <Button size="sm" variant="danger" onClick={() => archive(t)}>Archivar</Button>}
          </>
        )}
      />

      {expanded && (
        <div className="mt-4 rounded-xl border border-line bg-panel p-4">
          <div className="mb-3 flex items-center justify-between">
            <strong className="text-text">Atributos de {expanded.name}</strong>
            <Button size="sm" variant="ghost" onClick={() => setExpanded(null)}>Cerrar</Button>
          </div>
          {assigned.length === 0 ? (
            <p className="text-sm text-muted">Sin atributos asignados.</p>
          ) : (
            <div className="divide-y divide-line/60">
              {assigned.map((entry) => (
                <div key={entry.attribute_id} className="flex items-center justify-between gap-3 py-2 text-sm">
                  <span className="text-text">
                    {attributes.find((a) => a.id === entry.attribute_id)?.name ?? entry.attribute_id}
                    {entry.required && <span className="ml-2 text-xs text-amber-300">obligatorio</span>}
                  </span>
                  {canManageAttributes && (
                    <div className="flex items-center gap-3">
                      <label className="flex items-center gap-1.5 text-xs text-muted">
                        <input type="checkbox" checked={entry.required} onChange={(e) => saveAttributes(expanded, assigned.map((a) => ({ attribute_id: a.attribute_id, group_id: a.group_id, position: a.position, required: a.attribute_id === entry.attribute_id ? e.target.checked : a.required })))} /> Obligatorio
                      </label>
                      <Button size="sm" variant="ghost" onClick={() => saveAttributes(expanded, asPayload().filter((a) => a.attribute_id !== entry.attribute_id))}>Quitar</Button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
          {canManageAttributes && (
            <label className="mt-3 grid max-w-sm gap-1.5 text-sm">
              <span className="font-medium text-text">Agregar atributo</span>
              <select
                aria-label="Agregar atributo"
                defaultValue=""
                className={inputCls}
                onChange={(e) => {
                  const attributeId = e.target.value;
                  if (!attributeId) return;
                  const attribute = attributes.find((a) => a.id === attributeId);
                  saveAttributes(expanded, [...asPayload(), { attribute_id: attributeId, group_id: undefined, position: assigned.length, required: attribute?.is_required ?? false }]);
                  e.target.value = "";
                }}
              >
                <option value="">Selecciona…</option>
                {attributes.filter((a) => !assigned.some((entry) => entry.attribute_id === a.id)).map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
              </select>
            </label>
          )}
        </div>
      )}
      {error && <p className="mt-3 text-sm text-red-300" role="alert">{error}</p>}
    </AdminShell>
  );
}
