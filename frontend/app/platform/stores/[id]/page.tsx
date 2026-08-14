"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Shell } from "@/components/Shell";
import { ApiError, api } from "@/lib/api";
import { selectStore, type Store, updateResource } from "@/lib/platform";

function errorMessage(error: unknown) {
  if (error instanceof ApiError) return `${error.message}${error.correlationId ? ` · ID ${error.correlationId}` : ""}`;
  return error instanceof Error ? error.message : "Error inesperado";
}

export default function Page() {
  const { id } = useParams<{ id: string }>();
  const [store, setStore] = useState<Store>();
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function load() {
    try {
      const value = await api(`/stores/${id}`);
      setStore(value);
      selectStore(value.id);
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  useEffect(() => {
    load();
  }, [id]);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      const value = await updateResource(`/stores/${id}`, {
        name: form.get("name"),
        slug: form.get("slug"),
        default_locale: form.get("locale"),
        default_currency: form.get("currency"),
        timezone: form.get("timezone"),
      });
      setStore(value);
      selectStore(value.id);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setSaving(false);
    }
  }

  async function transition(action: string) {
    try {
      await api(`/stores/${id}/${action}`, { method: "POST" });
      await load();
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  return (
    <Shell title={store?.name ?? "Detalle de Store"}>
      {store && (
        <>
          <div className="tile-grid">
            <div className="tile"><strong>Estado</strong><p>{store.status}</p></div>
            <div className="tile"><strong>Código</strong><p>{store.code}</p></div>
          </div>
          {store.status !== "archived" && (
            <form className="tile" onSubmit={save} key={`${store.id}-${store.name}-${store.slug}`}>
              <strong>Editar Store</strong>
              <label>Nombre<input name="name" defaultValue={store.name} required minLength={2} /></label>
              <label>Slug<input name="slug" defaultValue={store.slug} required /></label>
              <label>Locale BCP 47<input name="locale" defaultValue={store.default_locale} required /></label>
              <label>Moneda ISO 4217<input name="currency" defaultValue={store.default_currency} required maxLength={3} /></label>
              <label>Zona horaria IANA<input name="timezone" defaultValue={store.timezone} required /></label>
              <button disabled={saving}>{saving ? "Guardando…" : "Guardar cambios"}</button>
            </form>
          )}
          <div className="nav">
            {store.status !== "active" && store.status !== "archived" && <button onClick={() => transition("activate")}>Activar</button>}
            {store.status === "active" && <button onClick={() => transition("suspend")}>Suspender</button>}
            {store.status !== "archived" && <button onClick={() => transition("archive")}>Archivar</button>}
          </div>
          <p>
            <Link href="/platform/sites">Configurar Sites</Link> · <Link href="/platform/channels">Channels</Link> · <Link href="/platform/environments">Environments</Link> · <Link href="/platform/markets">Markets</Link>
          </p>
        </>
      )}
      {error && <p className="error" role="alert">{error}</p>}
    </Shell>
  );
}
