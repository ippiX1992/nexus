"use client";
import { type FormEvent, useCallback, useEffect, useState } from "react";
import { inputCls } from "@/components/admin/forms";
import { catalogGet, catalogUpdate, technicalError } from "@/lib/catalog";

type TranslationFull = {
  id: string;
  product_id: string;
  locale: string;
  name: string;
  slug: string;
  short_description: string | null;
  long_description: string | null;
};

// Edit the product's descriptive content (name + short/long description) for its
// locale. Saves via PUT /catalog/products/{id}/translations/{locale} with the
// product version as If-Match; onSaved reloads the parent so the header/version
// refresh.
export function ProductGeneral({
  productId,
  locale,
  version,
  canManage,
  onSaved,
}: {
  productId: string;
  locale: string;
  version: number;
  canManage: boolean;
  onSaved: () => void;
}) {
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [shortDesc, setShortDesc] = useState("");
  const [longDesc, setLongDesc] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [ok, setOk] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const rows = await catalogGet<TranslationFull[]>(`/products/${productId}/translations`);
      const t = rows.find((r) => r.locale === locale) ?? rows[0];
      if (t) {
        setName(t.name);
        setSlug(t.slug);
        setShortDesc(t.short_description ?? "");
        setLongDesc(t.long_description ?? "");
      }
    } catch (e) {
      setError(technicalError(e));
    } finally {
      setLoading(false);
    }
  }, [productId, locale]);

  useEffect(() => {
    load();
  }, [load]);

  async function save(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setOk(false);
    try {
      await catalogUpdate(
        `/products/${productId}/translations/${encodeURIComponent(locale)}`,
        {
          name: name.trim(),
          slug: slug.trim(),
          short_description: shortDesc.trim() || null,
          long_description: longDesc.trim() || null,
        },
        version,
        "PUT",
      );
      setOk(true);
      onSaved();
    } catch (e) {
      setError(technicalError(e));
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <p className="text-sm text-muted">Cargando…</p>;

  const disabled = !canManage || saving;

  return (
    <form onSubmit={save} className="max-w-3xl space-y-4 rounded-xl border border-line bg-panel p-5">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-text">Información del producto</h3>
        <span className="text-xs text-muted">Idioma: {locale}</span>
      </div>

      <label className="grid gap-1.5 text-sm">
        <span className="font-medium text-text">Nombre</span>
        <input value={name} onChange={(e) => setName(e.target.value)} required maxLength={300} disabled={disabled} className={inputCls} />
      </label>

      <label className="grid gap-1.5 text-sm">
        <span className="font-medium text-text">Slug (URL en la tienda)</span>
        <input value={slug} onChange={(e) => setSlug(e.target.value)} required maxLength={200} disabled={disabled} className={inputCls} />
        <span className="text-xs text-muted">Cambiarlo cambia el enlace del producto en la tienda.</span>
      </label>

      <label className="grid gap-1.5 text-sm">
        <span className="font-medium text-text">Descripción corta</span>
        <textarea value={shortDesc} onChange={(e) => setShortDesc(e.target.value)} rows={2} maxLength={1000} disabled={disabled} className={inputCls} />
        <span className="text-xs text-muted">{shortDesc.length}/1000 · resumen breve que se muestra junto al producto.</span>
      </label>

      <label className="grid gap-1.5 text-sm">
        <span className="font-medium text-text">Descripción larga</span>
        <textarea value={longDesc} onChange={(e) => setLongDesc(e.target.value)} rows={8} disabled={disabled} className={inputCls} />
        <span className="text-xs text-muted">Detalle completo en la pestaña &quot;Descripción&quot; de la ficha.</span>
      </label>

      {error && <p className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-300" role="alert">{error}</p>}
      {ok && !error && <p className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-300">Cambios guardados.</p>}

      {canManage && (
        <button type="submit" disabled={saving} className="rounded-lg bg-brand px-5 py-2 text-sm font-semibold text-white disabled:opacity-50">
          {saving ? "Guardando…" : "Guardar cambios"}
        </button>
      )}
    </form>
  );
}
