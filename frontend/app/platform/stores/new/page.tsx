"use client";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";
import { AdminShell } from "@/components/admin/AdminShell";
import { Button, LinkButton } from "@/components/admin/Button";
import { Field, FormSection } from "@/components/admin/FormSection";
import { ApiError } from "@/lib/api";
import { createResource, selectStore } from "@/lib/platform";

const inputCls = "w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm text-text focus:border-brand focus:outline-none";

export default function Page() {
  const router = useRouter();
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    const form = new FormData(event.currentTarget);
    try {
      const store = await createResource("/stores", {
        code: form.get("code"),
        name: form.get("name"),
        slug: form.get("slug"),
        default_locale: form.get("locale"),
        default_currency: form.get("currency"),
        timezone: form.get("timezone"),
      });
      selectStore(store.id);
      router.push(`/platform/stores/${store.id}`);
    } catch (e) {
      const x = e as ApiError;
      setError(`${x.message}${x.correlationId ? ` · ID ${x.correlationId}` : ""}`);
      setSaving(false);
    }
  }

  return (
    <AdminShell title="Nueva tienda" description="Crea una tienda. Después podrás añadir sus sitios, canales, mercados y precios.">
      <form onSubmit={submit} className="max-w-3xl">
        <FormSection title="Información general" description="Nombre y código de la tienda.">
          <Field label="Nombre">
            <input name="name" required className={inputCls} />
          </Field>
          <Field label="Código">
            <input name="code" required className={inputCls} />
          </Field>
          <Field label="Slug" hint="Identificador para la URL.">
            <input name="slug" required className={inputCls} />
          </Field>
        </FormSection>
        <FormSection title="Configuración regional" description="Idioma, moneda y zona horaria por defecto.">
          <Field label="Idioma (BCP 47)">
            <input name="locale" defaultValue="es-EC" required className={inputCls} />
          </Field>
          <Field label="Moneda (ISO 4217)">
            <input name="currency" defaultValue="USD" maxLength={3} required className={inputCls} />
          </Field>
          <Field label="Zona horaria (IANA)">
            <input name="timezone" defaultValue="America/Guayaquil" required className={inputCls} />
          </Field>
        </FormSection>
        <div className="mt-6 flex gap-2 border-t border-line pt-6">
          <Button variant="primary" type="submit" disabled={saving}>
            {saving ? "Creando…" : "Crear tienda"}
          </Button>
          <LinkButton href="/platform/stores" variant="secondary">
            Cancelar
          </LinkButton>
        </div>
        {error && (
          <p className="mt-3 text-sm text-red-300" role="alert">
            {error}
          </p>
        )}
      </form>
    </AdminShell>
  );
}
