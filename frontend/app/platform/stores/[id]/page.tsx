"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";
import { inputCls } from "@/components/admin/forms";
import { AdminShell } from "@/components/admin/AdminShell";
import { Button, LinkButton } from "@/components/admin/Button";
import { Field, FormSection } from "@/components/admin/FormSection";
import { StatusBadge } from "@/components/admin/StatusBadge";
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      const value = await updateResource(`/stores/${id}`, { name: form.get("name"), slug: form.get("slug"), default_locale: form.get("locale"), default_currency: form.get("currency"), timezone: form.get("timezone") });
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

  const breadcrumbs = [
    { href: "/dashboard", label: "Inicio" },
    { href: "/platform/stores", label: "Tiendas" },
    { href: `/platform/stores/${id}`, label: store?.name ?? "Tienda" },
  ];

  return (
    <AdminShell
      title={store?.name ?? "Tienda"}
      breadcrumbs={breadcrumbs}
      actions={
        store && (
          <>
            {store.status !== "active" && store.status !== "archived" && <Button variant="primary" onClick={() => transition("activate")}>Activar</Button>}
            {store.status === "active" && <Button variant="secondary" onClick={() => transition("suspend")}>Suspender</Button>}
            {store.status !== "archived" && <Button variant="danger" onClick={() => transition("archive")}>Archivar</Button>}
          </>
        )
      }
    >
      {store && (
        <>
          <div className="mb-5 flex items-center gap-3">
            <StatusBadge status={store.status} />
            <span className="text-sm text-muted">Código {store.code}</span>
          </div>

          {store.status !== "archived" && (
            <form onSubmit={save} key={`${store.id}-${store.name}-${store.slug}`} className="max-w-3xl">
              <FormSection title="Información general" description="Nombre y slug de la tienda.">
                <Field label="Nombre"><input name="name" defaultValue={store.name} required minLength={2} className={inputCls} /></Field>
                <Field label="Slug"><input name="slug" defaultValue={store.slug} required className={inputCls} /></Field>
              </FormSection>
              <FormSection title="Configuración regional" description="Idioma, moneda y zona horaria por defecto.">
                <Field label="Idioma (BCP 47)"><input name="locale" defaultValue={store.default_locale} required className={inputCls} /></Field>
                <Field label="Moneda (ISO 4217)"><input name="currency" defaultValue={store.default_currency} required maxLength={3} className={inputCls} /></Field>
                <Field label="Zona horaria (IANA)"><input name="timezone" defaultValue={store.timezone} required className={inputCls} /></Field>
              </FormSection>
              <div className="mt-6 border-t border-line pt-6">
                <Button variant="primary" type="submit" disabled={saving}>{saving ? "Guardando…" : "Guardar cambios"}</Button>
              </div>
            </form>
          )}

          <div className="mt-8 flex flex-wrap gap-2">
            <LinkButton href="/platform/sites" variant="secondary" size="sm">Sitios</LinkButton>
            <LinkButton href="/platform/channels" variant="secondary" size="sm">Canales</LinkButton>
            <LinkButton href="/platform/markets" variant="secondary" size="sm">Mercados</LinkButton>
            <LinkButton href="/platform/environments" variant="secondary" size="sm">Ambientes</LinkButton>
          </div>
        </>
      )}
      {error && <p className="mt-3 text-sm text-red-300" role="alert">{error}</p>}
    </AdminShell>
  );
}
