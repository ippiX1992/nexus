"use client";
import { inputCls } from "@/components/admin/forms";
import { type FormEvent, useEffect, useState } from "react";
import { AdminShell } from "@/components/admin/AdminShell";
import { Button } from "@/components/admin/Button";
import { DataTable, type Column } from "@/components/admin/DataTable";
import { EmptyState } from "@/components/admin/EmptyState";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { type Option, type OptionValue, catalogCommand, catalogContext, catalogCreate, catalogGet, catalogPage, technicalError } from "@/lib/catalog";


export default function Page() {
  const [items, setItems] = useState<Option[]>([]);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [expanded, setExpanded] = useState<Option | null>(null);
  const [values, setValues] = useState<OptionValue[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const canManage = permissions.includes("catalog.option.create") || permissions.includes("catalog.option.update");
  const canManageValues = permissions.includes("catalog.option_value.create");

  async function load() {
    setLoading(true);
    try {
      const [page, ctx] = await Promise.all([catalogPage<Option>("/options"), catalogContext()]);
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
      await catalogCreate("/options", { code: form.get("code"), name: form.get("name"), input_type: form.get("input_type") || "select" });
      el.reset();
      setShowForm(false);
      await load();
    } catch (e) {
      setError(technicalError(e));
    }
  }
  async function archive(item: Option) {
    try {
      await catalogCommand(`/options/${item.id}/archive`, item.version);
      await load();
    } catch (e) {
      setError(technicalError(e));
    }
  }
  async function toggleValues(option: Option) {
    if (expanded?.id === option.id) return setExpanded(null);
    try {
      setValues(await catalogGet<OptionValue[]>(`/options/${option.id}/values`));
      setExpanded(option);
    } catch (e) {
      setError(technicalError(e));
    }
  }
  async function submitValue(optionId: string, event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const el = event.currentTarget;
    const form = new FormData(el);
    try {
      await catalogCreate(`/options/${optionId}/values`, { code: form.get("code"), value: form.get("value"), swatch_hex: form.get("swatch_hex") || undefined });
      el.reset();
      setValues(await catalogGet<OptionValue[]>(`/options/${optionId}/values`));
    } catch (e) {
      setError(technicalError(e));
    }
  }
  async function archiveValue(optionId: string, value: OptionValue) {
    try {
      await catalogCommand(`/option-values/${value.id}/archive`, value.version);
      setValues(await catalogGet<OptionValue[]>(`/options/${optionId}/values`));
    } catch (e) {
      setError(technicalError(e));
    }
  }

  const columns: Column<Option>[] = [
    { key: "name", header: "Nombre", render: (o) => <span className="font-medium text-text">{o.name}</span> },
    { key: "code", header: "Código", render: (o) => <span className="text-muted">{o.code}</span> },
    { key: "input_type", header: "Tipo", render: (o) => <span className="text-muted">{o.input_type}</span>, hideOnMobile: true },
    { key: "status", header: "Estado", render: (o) => <StatusBadge status={o.status} /> },
  ];

  return (
    <AdminShell
      title="Opciones"
      description="Dimensiones que generan variantes (Color, Talla). Para atributos descriptivos, ver Atributos."
      actions={canManage && <Button variant="primary" onClick={() => setShowForm((v) => !v)}>{showForm ? "Cerrar" : "Nueva opción"}</Button>}
    >
      {showForm && canManage && (
        <form onSubmit={submit} className="mb-5 grid gap-3 rounded-xl border border-line bg-panel p-4 sm:grid-cols-2 lg:grid-cols-4">
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">Código</span><input name="code" required className={inputCls} /></label>
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">Nombre</span><input name="name" required className={inputCls} /></label>
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">Tipo</span><select name="input_type" defaultValue="select" className={inputCls}><option value="select">select</option><option value="swatch">swatch</option></select></label>
          <div className="flex items-end"><Button variant="primary" type="submit">Crear opción</Button></div>
        </form>
      )}
      <DataTable
        columns={columns}
        rows={items}
        keyField={(o) => o.id}
        loading={loading}
        empty={<EmptyState title="Sin opciones" description="Crea la primera (Color, Talla…) para generar variantes." action={canManage ? <Button variant="primary" onClick={() => setShowForm(true)}>Nueva opción</Button> : undefined} />}
        rowActions={(o) => (
          <>
            <Button size="sm" variant="ghost" onClick={() => toggleValues(o)}>{expanded?.id === o.id ? "Ocultar" : "Valores"}</Button>
            {canManage && o.status !== "archived" && <Button size="sm" variant="danger" onClick={() => archive(o)}>Archivar</Button>}
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
            {values.map((value) => (
              <div key={value.id} className="flex items-center justify-between gap-3 py-2 text-sm">
                <span className="flex items-center gap-2 text-text">
                  {value.value} <span className="text-xs text-muted">({value.code})</span>
                  {value.swatch_hex && <span className="inline-block h-3 w-3 rounded-full ring-1 ring-line" style={{ background: value.swatch_hex }} />}
                </span>
                {canManageValues && value.status !== "archived" && <Button size="sm" variant="ghost" onClick={() => archiveValue(expanded.id, value)}>Archivar</Button>}
              </div>
            ))}
          </div>
          {canManageValues && (
            <form onSubmit={(e) => submitValue(expanded.id, e)} className="mt-3 flex flex-wrap items-end gap-2">
              <input name="code" placeholder="código" required className={inputCls} />
              <input name="value" placeholder="valor" required className={inputCls} />
              {expanded.input_type === "swatch" && <input name="swatch_hex" placeholder="#RRGGBB" className={inputCls} />}
              <Button size="sm" variant="secondary" type="submit">Agregar valor</Button>
            </form>
          )}
        </div>
      )}
      {error && <p className="mt-3 text-sm text-red-300" role="alert">{error}</p>}
    </AdminShell>
  );
}
