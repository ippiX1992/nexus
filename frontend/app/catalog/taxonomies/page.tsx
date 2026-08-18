"use client";
import { type FormEvent, useEffect, useState } from "react";
import { AdminShell } from "@/components/admin/AdminShell";
import { Button } from "@/components/admin/Button";
import { EmptyState } from "@/components/admin/EmptyState";
import { FilterBar, Select } from "@/components/admin/FilterBar";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { type Category, catalogCommand, catalogContext, catalogCreate, catalogGet, catalogPage, type Taxonomy, technicalError } from "@/lib/catalog";

const inputCls = "rounded-lg border border-line bg-bg px-3 py-2 text-sm text-text focus:border-brand focus:outline-none";

export default function Page() {
  const [taxonomies, setTaxonomies] = useState<Taxonomy[]>([]);
  const [selected, setSelected] = useState("");
  const [categories, setCategories] = useState<Category[]>([]);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [showTaxForm, setShowTaxForm] = useState(false);
  const [showCatForm, setShowCatForm] = useState(false);
  const [error, setError] = useState("");
  const canTaxonomy = permissions.includes("catalog.taxonomy.manage");
  const canCategory = permissions.includes("catalog.category.manage");

  async function load() {
    try {
      const [page, ctx] = await Promise.all([catalogPage<Taxonomy>("/taxonomies"), catalogContext()]);
      setTaxonomies(page.items);
      setPermissions(ctx.permissions);
      const id = selected || page.items[0]?.id || "";
      setSelected(id);
      if (id) setCategories(await catalogGet(`/taxonomies/${id}/categories`));
      setError("");
    } catch (e) {
      setError(technicalError(e));
    }
  }
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  async function choose(id: string) {
    setSelected(id);
    try {
      setCategories(await catalogGet(`/taxonomies/${id}/categories`));
    } catch (e) {
      setError(technicalError(e));
    }
  }
  async function createTaxonomy(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const el = event.currentTarget;
    const form = new FormData(el);
    try {
      await catalogCreate("/taxonomies", { code: form.get("code"), name: form.get("name") });
      el.reset();
      setShowTaxForm(false);
      await load();
    } catch (e) {
      setError(technicalError(e));
    }
  }
  async function createCategory(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const el = event.currentTarget;
    const form = new FormData(el);
    try {
      await catalogCreate(`/taxonomies/${selected}/categories`, { parent_id: form.get("parent_id") || null, code: form.get("code"), name: form.get("name"), slug: form.get("slug"), position: 0 });
      el.reset();
      setShowCatForm(false);
      await choose(selected);
    } catch (e) {
      setError(technicalError(e));
    }
  }
  async function archive(item: Category) {
    try {
      await catalogCommand(`/categories/${item.id}/archive`, item.version);
      await choose(selected);
    } catch (e) {
      setError(technicalError(e));
    }
  }
  function depth(item: Category) {
    let current = item;
    let count = 0;
    while (current.parent_id && count < 20) {
      const parent = categories.find((v) => v.id === current.parent_id);
      if (!parent) break;
      count++;
      current = parent;
    }
    return count;
  }

  return (
    <AdminShell
      title="Categorías"
      description="Organiza tu catálogo en categorías jerárquicas."
      actions={
        canTaxonomy && (
          <Button variant="secondary" onClick={() => { setShowCatForm(false); setShowTaxForm((v) => !v); }}>
            {showTaxForm ? "Cerrar" : "Nueva taxonomía"}
          </Button>
        )
      }
    >
      {showTaxForm && canTaxonomy && (
        <form onSubmit={createTaxonomy} className="mb-5 grid gap-3 rounded-xl border border-line bg-panel p-4 sm:grid-cols-2 lg:grid-cols-3">
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">Código</span><input name="code" required className={inputCls} /></label>
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">Nombre</span><input name="name" required className={inputCls} /></label>
          <div className="flex items-end"><Button variant="primary" type="submit">Crear taxonomía</Button></div>
        </form>
      )}

      <FilterBar>
        <Select value={selected} onChange={choose} label="Taxonomía">
          <option value="">Selecciona una taxonomía</option>
          {taxonomies.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
        </Select>
        {selected && canCategory && (
          <Button variant="primary" onClick={() => { setShowTaxForm(false); setShowCatForm((v) => !v); }}>
            {showCatForm ? "Cerrar" : "Nueva categoría"}
          </Button>
        )}
      </FilterBar>

      {showCatForm && canCategory && selected && (
        <form onSubmit={createCategory} className="mb-5 grid gap-3 rounded-xl border border-line bg-panel p-4 sm:grid-cols-2 lg:grid-cols-4">
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">Categoría madre</span>
            <select name="parent_id" className={inputCls}>
              <option value="">Raíz</option>
              {categories.filter((c) => c.status !== "archived").map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </label>
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">Código</span><input name="code" required className={inputCls} /></label>
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">Nombre</span><input name="name" required className={inputCls} /></label>
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">Slug</span><input name="slug" required className={inputCls} /></label>
          <div><Button variant="primary" type="submit">Crear categoría</Button></div>
        </form>
      )}

      {selected && categories.length === 0 ? (
        <EmptyState title="Sin categorías" description="Crea la primera categoría de esta taxonomía." action={canCategory ? <Button variant="primary" onClick={() => setShowCatForm(true)}>Nueva categoría</Button> : undefined} />
      ) : (
        <div className="overflow-hidden rounded-xl border border-line bg-panel">
          {categories.map((item) => (
            <div key={item.id} className="flex items-center justify-between gap-3 border-b border-line/50 px-4 py-2.5 last:border-0" style={{ paddingLeft: `${1 + depth(item) * 1.5}rem` }}>
              <span className="flex items-center gap-2 text-sm">
                {depth(item) > 0 && <span className="text-muted/50">└</span>}
                <span className="font-medium text-text">{item.name}</span>
                <span className="text-xs text-muted">{item.code}</span>
                <StatusBadge status={item.status} />
              </span>
              {canCategory && item.status !== "archived" && <Button size="sm" variant="danger" onClick={() => archive(item)}>Archivar</Button>}
            </div>
          ))}
        </div>
      )}
      {error && <p className="mt-3 text-sm text-red-300" role="alert">{error}</p>}
    </AdminShell>
  );
}
