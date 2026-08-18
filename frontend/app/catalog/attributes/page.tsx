"use client";
import { inputCls } from "@/components/admin/forms";
import { type FormEvent, useEffect, useState } from "react";
import { AdminShell } from "@/components/admin/AdminShell";
import { Button } from "@/components/admin/Button";
import { DataTable, type Column } from "@/components/admin/DataTable";
import { EmptyState } from "@/components/admin/EmptyState";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { type Attribute, type AttributeDataType, type AttributeOption, catalogCommand, catalogContext, catalogCreate, catalogGet, catalogPage, technicalError } from "@/lib/catalog";

const DATA_TYPES: AttributeDataType[] = ["TEXT", "LONG_TEXT", "INTEGER", "DECIMAL", "BOOLEAN", "DATE", "DATETIME", "SELECT", "MULTI_SELECT"];

export default function Page() {
  const [items, setItems] = useState<Attribute[]>([]);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [expanded, setExpanded] = useState<Attribute | null>(null);
  const [options, setOptions] = useState<AttributeOption[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const canManage = permissions.includes("catalog.attribute.create") || permissions.includes("catalog.attribute.update");
  const canArchive = permissions.includes("catalog.attribute.archive");
  const canManageOptions = permissions.includes("catalog.attribute_option.create");

  async function load() {
    setLoading(true);
    try {
      const [page, ctx] = await Promise.all([catalogPage<Attribute>("/attributes"), catalogContext()]);
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
      await catalogCreate("/attributes", {
        code: form.get("code"),
        name: form.get("name"),
        data_type: form.get("data_type"),
        unit: form.get("unit") || undefined,
        is_required: form.get("is_required") === "on",
        is_filterable: form.get("is_filterable") === "on",
        is_searchable: form.get("is_searchable") === "on",
        is_comparable: form.get("is_comparable") === "on",
      });
      el.reset();
      setShowForm(false);
      await load();
    } catch (e) {
      setError(technicalError(e));
    }
  }
  async function command(item: Attribute, kind: "archive" | "restore") {
    try {
      await catalogCommand(`/attributes/${item.id}/${kind}`, item.version);
      await load();
    } catch (e) {
      setError(technicalError(e));
    }
  }
  async function toggleOptions(attribute: Attribute) {
    if (expanded?.id === attribute.id) return setExpanded(null);
    try {
      setOptions(await catalogGet<AttributeOption[]>(`/attributes/${attribute.id}/options`));
      setExpanded(attribute);
    } catch (e) {
      setError(technicalError(e));
    }
  }
  async function submitOption(attributeId: string, event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const el = event.currentTarget;
    const form = new FormData(el);
    try {
      await catalogCreate(`/attributes/${attributeId}/options`, { code: form.get("code"), label: form.get("label") });
      el.reset();
      setOptions(await catalogGet<AttributeOption[]>(`/attributes/${attributeId}/options`));
    } catch (e) {
      setError(technicalError(e));
    }
  }
  async function archiveOption(attributeId: string, option: AttributeOption) {
    try {
      await catalogCommand(`/attribute-options/${option.id}/archive`, option.version);
      setOptions(await catalogGet<AttributeOption[]>(`/attributes/${attributeId}/options`));
    } catch (e) {
      setError(technicalError(e));
    }
  }

  const columns: Column<Attribute>[] = [
    { key: "name", header: "Nombre", render: (a) => <span className="font-medium text-text">{a.name}</span> },
    { key: "code", header: "Código", render: (a) => <span className="text-muted">{a.code}</span>, hideOnMobile: true },
    { key: "data_type", header: "Tipo", render: (a) => <span className="text-muted">{a.data_type}{a.unit ? ` · ${a.unit}` : ""}</span> },
    { key: "status", header: "Estado", render: (a) => <StatusBadge status={a.status} /> },
  ];
  const hasValues = (a: Attribute) => a.data_type === "SELECT" || a.data_type === "MULTI_SELECT";

  return (
    <AdminShell
      title="Atributos"
      description="Características informativas de un producto (Potencia, Material). Para combinaciones de variante, ver Opciones."
      actions={canManage && <Button variant="primary" onClick={() => setShowForm((v) => !v)}>{showForm ? "Cerrar" : "Nuevo atributo"}</Button>}
    >
      {showForm && canManage && (
        <form onSubmit={submit} className="mb-5 grid gap-3 rounded-xl border border-line bg-panel p-4 sm:grid-cols-2 lg:grid-cols-4">
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">Código</span><input name="code" required className={inputCls} /></label>
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">Nombre</span><input name="name" required className={inputCls} /></label>
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">Tipo de dato</span><select name="data_type" defaultValue="TEXT" className={inputCls}>{DATA_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}</select></label>
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">Unidad (opcional)</span><input name="unit" className={inputCls} /></label>
          <div className="col-span-full flex flex-wrap gap-4 text-sm text-text">
            <label className="flex items-center gap-1.5"><input type="checkbox" name="is_required" /> Obligatorio</label>
            <label className="flex items-center gap-1.5"><input type="checkbox" name="is_filterable" /> Filtrable</label>
            <label className="flex items-center gap-1.5"><input type="checkbox" name="is_searchable" /> Buscable</label>
            <label className="flex items-center gap-1.5"><input type="checkbox" name="is_comparable" /> Comparable</label>
          </div>
          <div><Button variant="primary" type="submit">Crear atributo</Button></div>
        </form>
      )}
      <DataTable
        columns={columns}
        rows={items}
        keyField={(a) => a.id}
        loading={loading}
        empty={<EmptyState title="Sin atributos" description="Crea el primero para describir tus productos." action={canManage ? <Button variant="primary" onClick={() => setShowForm(true)}>Nuevo atributo</Button> : undefined} />}
        rowActions={(a) => (
          <>
            {hasValues(a) && <Button size="sm" variant="ghost" onClick={() => toggleOptions(a)}>{expanded?.id === a.id ? "Ocultar" : "Valores"}</Button>}
            {canArchive && a.status !== "archived" && <Button size="sm" variant="danger" onClick={() => command(a, "archive")}>Archivar</Button>}
            {canArchive && a.status === "archived" && <Button size="sm" variant="secondary" onClick={() => command(a, "restore")}>Restaurar</Button>}
          </>
        )}
      />

      {expanded && (
        <div className="mt-4 rounded-xl border border-line bg-panel p-4">
          <div className="mb-3 flex items-center justify-between">
            <strong className="text-text">Valores de {expanded.name}</strong>
            <Button size="sm" variant="ghost" onClick={() => setExpanded(null)}>Cerrar</Button>
          </div>
          <div className="divide-y divide-line/60">
            {options.map((option) => (
              <div key={option.id} className="flex items-center justify-between gap-3 py-2 text-sm">
                <span className="text-text">{option.label} <span className="text-xs text-muted">({option.code})</span></span>
                {canManageOptions && option.status !== "archived" && <Button size="sm" variant="ghost" onClick={() => archiveOption(expanded.id, option)}>Archivar</Button>}
              </div>
            ))}
          </div>
          {canManageOptions && (
            <form onSubmit={(e) => submitOption(expanded.id, e)} className="mt-3 flex flex-wrap items-end gap-2">
              <input name="code" placeholder="código" required className={inputCls} />
              <input name="label" placeholder="etiqueta" required className={inputCls} />
              <Button size="sm" variant="secondary" type="submit">Agregar valor</Button>
            </form>
          )}
        </div>
      )}
      {error && <p className="mt-3 text-sm text-red-300" role="alert">{error}</p>}
    </AdminShell>
  );
}
