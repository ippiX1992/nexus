"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { ApiError, api } from "@/lib/api";
import {
  activeStore,
  createResource,
  listStores,
  selectStore,
  type Store,
  updateResource,
} from "@/lib/platform";

type Kind = "sites" | "channels" | "environments" | "markets";
type Item = {
  id: string;
  name: string;
  code: string;
  status: string;
  slug?: string;
  site_type?: string;
  primary_domain_placeholder?: string | null;
  channel_type?: string;
  environment_type?: string;
  country_code?: string;
  currency_code?: string;
  default_locale?: string;
  timezone?: string;
};

const labels: Record<Kind, string> = { sites: "Sites", channels: "Channels", environments: "Environments", markets: "Markets" };
const singular: Record<Kind, string> = { sites: "sites", channels: "channels", environments: "environments", markets: "markets" };

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

export function PlatformCollection({ kind }: { kind: Kind }) {
  const [store, setStore] = useState(activeStore());
  const [stores, setStores] = useState<Store[]>([]);
  const [items, setItems] = useState<Item[]>([]);
  const [editing, setEditing] = useState<string | null>(null);
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
    load();
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
    const formElement = event.currentTarget;
    try {
      await createResource(`/stores/${store}/${kind}`, createPayload(kind, new FormData(formElement)));
      formElement.reset();
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
      if (editing === id) setEditing(null);
      await load();
    } catch (caught) {
      setError(technicalError(caught));
    }
  }

  return (
    <>
      <div className="row">
        <span>Store activo</span>
        <select aria-label="Store activo" value={store ?? ""} onChange={(event) => choose(event.target.value)}>
          <option value="">Selecciona un Store</option>
          {stores.filter((item) => item.status !== "archived").map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
        </select>
      </div>
      {!store && <p>Selecciona un Store o <Link href="/platform/stores/new">crea uno</Link>.</p>}
      {store && (
        <form className="tile" onSubmit={submit}>
          <strong>Crear {labels[kind].slice(0, -1)}</strong>
          <label>Código<input name="code" required /></label>
          <label>Nombre<input name="name" required /></label>
          {kind === "sites" && <><label>Slug<input name="slug" required /></label><label>Tipo<select name="type"><option value="commerce">Commerce</option><option value="content">Content</option><option value="landing">Landing</option><option value="portal">Portal</option></select></label><label>Dominio futuro<input name="domain" /></label></>}
          {kind === "channels" && <label>Tipo<select name="type">{["web", "mobile", "marketplace", "b2b", "social", "pos", "api"].map((value) => <option key={value}>{value}</option>)}</select></label>}
          {kind === "environments" && <label>Tipo<select name="type">{["development", "preview", "staging", "production"].map((value) => <option key={value}>{value}</option>)}</select></label>}
          {kind === "markets" && <><label>País ISO<input name="country" defaultValue="EC" maxLength={2} /></label><label>Moneda ISO<input name="currency" defaultValue="USD" maxLength={3} /></label><label>Locale<input name="locale" defaultValue="es-EC" /></label><label>Zona IANA<input name="timezone" defaultValue="America/Guayaquil" /></label></>}
          <button>Crear</button>
        </form>
      )}
      {loading ? <p>Cargando…</p> : items.length === 0 && store ? <p>No hay {labels[kind].toLowerCase()} todavía.</p> : items.map((item) => (
        <div className="tile" key={item.id}>
          {editing === item.id ? (
            <form onSubmit={(event) => save(event, item)}>
              <strong>Editar {item.code}</strong>
              <label>Nombre<input name="name" defaultValue={item.name} required minLength={2} /></label>
              {kind === "sites" && <><label>Slug<input name="slug" defaultValue={item.slug} required /></label><label>Dominio futuro<input name="domain" defaultValue={item.primary_domain_placeholder ?? ""} /></label></>}
              {kind === "markets" && <><label>Locale<input name="locale" defaultValue={item.default_locale} required /></label><label>Zona IANA<input name="timezone" defaultValue={item.timezone} required /></label></>}
              <div className="nav"><button disabled={saving}>{saving ? "Guardando…" : "Guardar"}</button><button type="button" onClick={() => setEditing(null)}>Cancelar</button></div>
            </form>
          ) : (
            <div className="row">
              <span><strong>{item.name}</strong><br />{item.code} · {item.status}</span>
              {item.status !== "archived" && <span><button type="button" style={{ width: "auto" }} onClick={() => setEditing(item.id)}>Editar</button><button type="button" style={{ width: "auto" }} onClick={() => archive(item.id)}>Archivar</button></span>}
            </div>
          )}
        </div>
      ))}
      {error && <p className="error" role="alert">{error}</p>}
    </>
  );
}
