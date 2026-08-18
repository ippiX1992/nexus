"use client";

import Link from "next/link";
import { type FormEvent, useEffect, useState } from "react";
import { Button } from "@/components/admin/Button";
import { DataTable, type Column } from "@/components/admin/DataTable";
import { EmptyState } from "@/components/admin/EmptyState";
import { FilterBar, Select } from "@/components/admin/FilterBar";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { ApiError, api } from "@/lib/api";
import { activeStore, createResource, listStores, selectStore, type Store, updateResource } from "@/lib/platform";

type Kind = "sites" | "channels" | "environments" | "markets";
type Item = {
  id: string;
  name: string;
  code: string;
  status: string;
  slug?: string;
  primary_domain_placeholder?: string | null;
  default_locale?: string;
  timezone?: string;
};

const labels: Record<Kind, string> = { sites: "Sitios", channels: "Canales", environments: "Ambientes", markets: "Mercados" };
const singularLabel: Record<Kind, string> = { sites: "sitio", channels: "canal", environments: "ambiente", markets: "mercado" };
const singular: Record<Kind, string> = { sites: "sites", channels: "channels", environments: "environments", markets: "markets" };
const inputCls = "rounded-lg border border-line bg-bg px-3 py-2 text-sm text-text focus:border-brand focus:outline-none";

function technicalError(value: unknown) {
  if (value instanceof ApiError) return `${value.message}${value.correlationId ? ` · ID ${value.correlationId}` : ""}`;
  return value instanceof Error ? value.message : "Error inesperado";
}
function createPayload(kind: Kind, form: FormData) {
  const base = { code: form.get("code"), name: form.get("name") };
  if (kind === "sites") return { ...base, slug: form.get("slug"), site_type: form.get("type"), primary_domain_placeholder: form.get("domain") || null };
  if (kind === "channels") return { ...base, channel_type: form.get("type") };
  if (kind === "environments") return { ...base, environment_type: form.get("type") };
  return { ...base, country_code: form.get("country"), currency_code: form.get("currency"), default_locale: form.get("locale"), timezone: form.get("timezone") };
}
function editPayload(kind: Kind, form: FormData) {
  const base = { name: form.get("name") };
  if (kind === "sites") return { ...base, slug: form.get("slug"), primary_domain_placeholder: form.get("domain") || null };
  if (kind === "markets") return { ...base, default_locale: form.get("locale"), timezone: form.get("timezone") };
  return base;
}

const Label = ({ children }: { children: React.ReactNode }) => <span className="font-medium text-text">{children}</span>;

export function PlatformCollection({ kind }: { kind: Kind }) {
  const [store, setStore] = useState<string | null>(null);
  const [stores, setStores] = useState<Store[]>([]);
  const [items, setItems] = useState<Item[]>([]);
  const [editing, setEditing] = useState<Item | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  async function load(storeId = store) {
    setLoading(true);
    setError("");
    try {
      setStores(await listStores());
      setItems(storeId ? await api(`/stores/${storeId}/${kind}`) : []);
    } catch (caught) {
      setError(technicalError(caught));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    const initial = activeStore();
    setStore(initial);
    load(initial);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kind]);

  function choose(id: string) {
    const selected = id || null;
    selectStore(selected);
    setStore(selected);
    setEditing(null);
    load(selected);
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!store) return;
    const el = event.currentTarget;
    try {
      await createResource(`/stores/${store}/${kind}`, createPayload(kind, new FormData(el)));
      el.reset();
      setShowForm(false);
      await load();
    } catch (caught) {
      setError(technicalError(caught));
    }
  }
  async function save(event: FormEvent<HTMLFormElement>, item: Item) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      await updateResource(`/${singular[kind]}/${item.id}`, editPayload(kind, new FormData(event.currentTarget)));
      setEditing(null);
      await load();
    } catch (caught) {
      setError(technicalError(caught));
    } finally {
      setSaving(false);
    }
  }
  async function archive(id: string) {
    try {
      await api(`/${singular[kind]}/${id}/archive`, { method: "POST" });
      if (editing?.id === id) setEditing(null);
      await load();
    } catch (caught) {
      setError(technicalError(caught));
    }
  }

  const columns: Column<Item>[] = [
    { key: "name", header: "Nombre", render: (i) => <span className="font-medium text-text">{i.name}</span> },
    { key: "code", header: "Código", render: (i) => <span className="text-muted">{i.code}</span> },
    { key: "status", header: "Estado", render: (i) => <StatusBadge status={i.status} /> },
  ];

  return (
    <>
      <FilterBar>
        <Select value={store ?? ""} onChange={choose} label="Tienda activa">
          <option value="">Selecciona una tienda</option>
          {stores.filter((s) => s.status !== "archived").map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </Select>
        {store && (
          <Button variant="primary" onClick={() => { setEditing(null); setShowForm((v) => !v); }}>
            {showForm ? "Cerrar" : `Nuevo ${singularLabel[kind]}`}
          </Button>
        )}
      </FilterBar>

      {!store && (
        <EmptyState
          title="Selecciona una tienda"
          description={`Elige una tienda para ver sus ${labels[kind].toLowerCase()}.`}
          action={<Link className="text-sm text-brand hover:underline" href="/platform/stores/new">Crear una tienda</Link>}
        />
      )}

      {store && showForm && (
        <form onSubmit={submit} className="mb-5 grid gap-3 rounded-xl border border-line bg-panel p-4 sm:grid-cols-2 lg:grid-cols-3">
          <label className="grid gap-1.5 text-sm"><Label>Código</Label><input name="code" required className={inputCls} /></label>
          <label className="grid gap-1.5 text-sm"><Label>Nombre</Label><input name="name" required className={inputCls} /></label>
          {kind === "sites" && (
            <>
              <label className="grid gap-1.5 text-sm"><Label>Slug</Label><input name="slug" required className={inputCls} /></label>
              <label className="grid gap-1.5 text-sm"><Label>Tipo</Label><select name="type" className={inputCls}><option value="commerce">Commerce</option><option value="content">Content</option><option value="landing">Landing</option><option value="portal">Portal</option></select></label>
              <label className="grid gap-1.5 text-sm"><Label>Dominio futuro</Label><input name="domain" className={inputCls} /></label>
            </>
          )}
          {kind === "channels" && <label className="grid gap-1.5 text-sm"><Label>Tipo</Label><select name="type" className={inputCls}>{["web", "mobile", "marketplace", "b2b", "social", "pos", "api"].map((v) => <option key={v}>{v}</option>)}</select></label>}
          {kind === "environments" && <label className="grid gap-1.5 text-sm"><Label>Tipo</Label><select name="type" className={inputCls}>{["development", "preview", "staging", "production"].map((v) => <option key={v}>{v}</option>)}</select></label>}
          {kind === "markets" && (
            <>
              <label className="grid gap-1.5 text-sm"><Label>País ISO</Label><input name="country" defaultValue="EC" maxLength={2} className={inputCls} /></label>
              <label className="grid gap-1.5 text-sm"><Label>Moneda ISO</Label><input name="currency" defaultValue="USD" maxLength={3} className={inputCls} /></label>
              <label className="grid gap-1.5 text-sm"><Label>Idioma</Label><input name="locale" defaultValue="es-EC" className={inputCls} /></label>
              <label className="grid gap-1.5 text-sm"><Label>Zona horaria</Label><input name="timezone" defaultValue="America/Guayaquil" className={inputCls} /></label>
            </>
          )}
          <div className="flex items-end"><Button variant="primary" type="submit">Crear</Button></div>
        </form>
      )}

      {store && editing && (
        <form onSubmit={(e) => save(e, editing)} className="mb-5 grid gap-3 rounded-xl border border-brand/40 bg-panel p-4 sm:grid-cols-2 lg:grid-cols-3">
          <div className="col-span-full text-sm font-semibold text-text">Editar {editing.code}</div>
          <label className="grid gap-1.5 text-sm"><Label>Nombre</Label><input name="name" defaultValue={editing.name} required minLength={2} className={inputCls} /></label>
          {kind === "sites" && (
            <>
              <label className="grid gap-1.5 text-sm"><Label>Slug</Label><input name="slug" defaultValue={editing.slug} required className={inputCls} /></label>
              <label className="grid gap-1.5 text-sm"><Label>Dominio futuro</Label><input name="domain" defaultValue={editing.primary_domain_placeholder ?? ""} className={inputCls} /></label>
            </>
          )}
          {kind === "markets" && (
            <>
              <label className="grid gap-1.5 text-sm"><Label>Idioma</Label><input name="locale" defaultValue={editing.default_locale} required className={inputCls} /></label>
              <label className="grid gap-1.5 text-sm"><Label>Zona horaria</Label><input name="timezone" defaultValue={editing.timezone} required className={inputCls} /></label>
            </>
          )}
          <div className="col-span-full flex gap-2">
            <Button variant="primary" type="submit" disabled={saving}>{saving ? "Guardando…" : "Guardar"}</Button>
            <Button variant="secondary" type="button" onClick={() => setEditing(null)}>Cancelar</Button>
          </div>
        </form>
      )}

      {store && (
        <DataTable
          columns={columns}
          rows={items}
          keyField={(i) => i.id}
          loading={loading}
          empty={<EmptyState title={`Sin ${labels[kind].toLowerCase()}`} description={`Crea el primer ${singularLabel[kind]} de esta tienda.`} action={<Button variant="primary" onClick={() => setShowForm(true)}>{`Nuevo ${singularLabel[kind]}`}</Button>} />}
          rowActions={(i) =>
            i.status !== "archived" ? (
              <>
                <Button size="sm" variant="secondary" onClick={() => { setShowForm(false); setEditing(i); }}>Editar</Button>
                <Button size="sm" variant="danger" onClick={() => archive(i.id)}>Archivar</Button>
              </>
            ) : null
          }
        />
      )}
      {error && <p className="mt-3 text-sm text-red-300" role="alert">{error}</p>}
    </>
  );
}
