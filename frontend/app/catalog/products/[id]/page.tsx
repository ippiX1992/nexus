"use client";
import { inputCls } from "@/components/admin/forms";
import { useParams } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";
import { AdminShell } from "@/components/admin/AdminShell";
import { Button } from "@/components/admin/Button";
import { EmptyState } from "@/components/admin/EmptyState";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { ProductGeneral } from "@/components/admin/ProductGeneral";
import { ProductMedia } from "@/components/admin/ProductMedia";
import { Tabs } from "@/components/admin/Tabs";
import { activeStore, listStores, selectStore, type Store } from "@/lib/platform";
import { type Attribute, type AttributeOption, type Category, catalogCommand, catalogContext, catalogCreate, catalogGet, catalogPage, catalogUpdate, type Option, type OptionValue, type ProductAttributeValue, type ProductAttributeValueOption, type ProductDetail, type ProductOption, type ProductTypeAttribute, type Taxonomy, technicalError, type Variant, type VariantOptionValue } from "@/lib/catalog";


export default function Page() {
  const params = useParams<{ id: string }>();
  const productId = params.id;
  const [detail, setDetail] = useState<ProductDetail | null>(null);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [stores, setStores] = useState<Store[]>([]);
  const [storeId, setStoreId] = useState(activeStore() ?? "");
  const [categories, setCategories] = useState<Category[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("general");
  const [options, setOptions] = useState<Option[]>([]);
  const [productOptions, setProductOptions] = useState<ProductOption[]>([]);
  const [valuesByOption, setValuesByOption] = useState<Record<string, OptionValue[]>>({});
  const [attributes, setAttributes] = useState<Attribute[]>([]);
  const [productTypeAttributes, setProductTypeAttributes] = useState<ProductTypeAttribute[]>([]);
  const [attributeOptions, setAttributeOptions] = useState<Record<string, AttributeOption[]>>({});
  const [attributeValues, setAttributeValues] = useState<ProductAttributeValue[]>([]);
  const [attributeValueOptions, setAttributeValueOptions] = useState<ProductAttributeValueOption[]>([]);
  const canUpdate = permissions.includes("catalog.product.update");
  const canVariant = permissions.includes("catalog.variant.update");
  const canCreateVariant = permissions.includes("catalog.variant.create");
  const canArchive = permissions.includes("catalog.product.archive");
  const canAssign = permissions.includes("catalog.assignment.manage");
  const canManageProductOptions = permissions.includes("catalog.product_option.manage");
  const canManageSpecs = permissions.includes("catalog.product_attribute_value.manage");

  async function load() {
    setLoading(true);
    try {
      const [value, ctx, storeRows, taxonomyPage, optionPage, attributePage] = await Promise.all([catalogGet<ProductDetail>(`/products/${productId}`), catalogContext(), listStores(), catalogPage<Taxonomy>("/taxonomies"), catalogPage<Option>("/options"), catalogPage<Attribute>("/attributes")]);
      const categoryRows = (await Promise.all(taxonomyPage.items.map((item) => catalogGet<Category[]>(`/taxonomies/${item.id}/categories`)))).flat();
      const activeOptions = optionPage.items.filter((item) => item.status !== "archived");
      const assigned = await catalogGet<ProductOption[]>(`/products/${productId}/options`);
      const activeAssigned = assigned.filter((item) => !item.archived_at);
      const valuePairs = await Promise.all(activeAssigned.map(async (item) => [item.option_id, await catalogGet<OptionValue[]>(`/options/${item.option_id}/values`)] as const));
      const activeAttributes = attributePage.items.filter((item) => item.status !== "archived");
      const typeAttributes = (await catalogGet<ProductTypeAttribute[]>(`/product-types/${value.product.product_type_id}/attributes`)).filter((item) => !item.archived_at);
      const selectable = typeAttributes.filter((entry) => {
        const attribute = activeAttributes.find((a) => a.id === entry.attribute_id);
        return attribute && (attribute.data_type === "SELECT" || attribute.data_type === "MULTI_SELECT");
      });
      const attributeOptionPairs = await Promise.all(selectable.map(async (entry) => [entry.attribute_id, await catalogGet<AttributeOption[]>(`/attributes/${entry.attribute_id}/options`)] as const));
      const [specValues, specValueOptions] = await Promise.all([catalogGet<ProductAttributeValue[]>(`/products/${productId}/attributes`), catalogGet<ProductAttributeValueOption[]>(`/products/${productId}/attribute-value-options`)]);
      setDetail(value);
      setPermissions(ctx.permissions);
      setStores(storeRows);
      setCategories(categoryRows);
      setOptions(activeOptions);
      setProductOptions(activeAssigned);
      setValuesByOption(Object.fromEntries(valuePairs));
      setAttributes(activeAttributes);
      setProductTypeAttributes(typeAttributes);
      setAttributeOptions(Object.fromEntries(attributeOptionPairs));
      setAttributeValues(specValues);
      setAttributeValueOptions(specValueOptions);
      setError("");
    } catch (e) {
      setError(technicalError(e));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [productId]);

  function chooseStore(id: string) {
    setStoreId(id);
    if (id) selectStore(id);
  }
  async function productAction(action: "activate" | "archive") {
    if (!detail) return;
    try {
      await catalogCommand(`/products/${productId}/${action}`, detail.product.version);
      await load();
    } catch (e) {
      setError(technicalError(e));
    }
  }
  async function createVariant(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const element = event.currentTarget;
    const form = new FormData(element);
    const optionValueIds = productOptions.map((item) => form.get(`option-${item.option_id}`)).filter((value): value is string => typeof value === "string" && value.length > 0);
    try {
      await catalogCreate(`/products/${productId}/variants`, optionValueIds.length > 0 ? { sku: form.get("sku"), option_value_ids: optionValueIds } : { sku: form.get("sku") });
      element.reset();
      await load();
    } catch (e) {
      setError(technicalError(e));
    }
  }
  async function updateVariant(variant: Variant, sku: string) {
    try {
      await catalogUpdate(`/variants/${variant.id}`, { sku }, variant.version);
      await load();
    } catch (e) {
      setError(technicalError(e));
    }
  }
  async function archiveVariant(variant: Variant) {
    try {
      await catalogCommand(`/variants/${variant.id}/archive`, variant.version);
      await load();
    } catch (e) {
      setError(technicalError(e));
    }
  }
  async function assignStore() {
    if (!storeId) return;
    try {
      await catalogCreate(`/products/${productId}/stores/${storeId}`, { status: "draft" }, "PUT");
      await load();
    } catch (e) {
      setError(technicalError(e));
    }
  }
  async function unassignStore() {
    const assignment = detail?.stores.find((item) => item.store_id === storeId);
    if (!assignment) return;
    try {
      await catalogCommand(`/products/${productId}/stores/${storeId}`, assignment.version, "DELETE");
      await load();
    } catch (e) {
      setError(technicalError(e));
    }
  }
  async function assignCategory(categoryId: string) {
    if (!detail || !categoryId) return;
    const assignments = detail.categories.filter((item) => item.category_id !== categoryId).map((item) => ({ category_id: item.category_id, is_primary: item.is_primary, position: item.position }));
    assignments.push({ category_id: categoryId, is_primary: assignments.length === 0, position: assignments.length });
    try {
      await catalogUpdate(`/products/${productId}/categories`, { assignments }, detail.product.version, "PUT");
      await load();
    } catch (e) {
      setError(technicalError(e));
    }
  }
  async function addProductOption(optionId: string) {
    if (!detail || !optionId) return;
    const next = productOptions.map((item) => ({ option_id: item.option_id, position: item.position }));
    next.push({ option_id: optionId, position: next.length });
    try {
      await catalogUpdate(`/products/${productId}/options`, { options: next }, detail.product.version, "PUT");
      await load();
    } catch (e) {
      setError(technicalError(e));
    }
  }
  async function removeProductOption(optionId: string) {
    if (!detail) return;
    const next = productOptions.filter((item) => item.option_id !== optionId).map((item) => ({ option_id: item.option_id, position: item.position }));
    try {
      await catalogUpdate(`/products/${productId}/options`, { options: next }, detail.product.version, "PUT");
      await load();
    } catch (e) {
      setError(technicalError(e));
    }
  }
  async function saveSpecifications(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!detail) return;
    const element = event.currentTarget;
    const form = new FormData(element);
    const values: { attribute_id: string; value: unknown }[] = [];
    for (const entry of productTypeAttributes) {
      const attribute = attributes.find((a) => a.id === entry.attribute_id);
      if (!attribute) continue;
      if (attribute.data_type === "MULTI_SELECT") {
        const selected = form.getAll(`spec-${attribute.id}`).map(String).filter(Boolean);
        if (selected.length > 0) values.push({ attribute_id: attribute.id, value: selected });
        continue;
      }
      const raw = form.get(`spec-${attribute.id}`);
      if (attribute.data_type === "BOOLEAN") {
        values.push({ attribute_id: attribute.id, value: raw === "on" });
        continue;
      }
      if (raw === null || raw === "") continue;
      if (attribute.data_type === "INTEGER") {
        values.push({ attribute_id: attribute.id, value: parseInt(String(raw), 10) });
        continue;
      }
      if (attribute.data_type === "DATETIME") {
        values.push({ attribute_id: attribute.id, value: `${raw}:00Z` });
        continue;
      }
      values.push({ attribute_id: attribute.id, value: String(raw) });
    }
    try {
      await catalogUpdate(`/products/${productId}/attributes`, { values }, detail.product.version, "PUT");
      await load();
    } catch (e) {
      setError(technicalError(e));
    }
  }

  const breadcrumbs = [
    { href: "/dashboard", label: "Inicio" },
    { href: "/catalog/products", label: "Productos" },
    { href: `/catalog/products/${productId}`, label: detail?.translations[0]?.name ?? "Producto" },
  ];
  if (loading && !detail) return <AdminShell title="Producto" breadcrumbs={breadcrumbs}><p className="text-muted">Cargando…</p></AdminShell>;
  if (!detail) return <AdminShell title="Producto" breadcrumbs={breadcrumbs}><p className="text-sm text-red-300" role="alert">{error || "No encontrado"}</p></AdminShell>;

  const name = detail.translations[0]?.name ?? detail.product.code ?? detail.product.id;
  const active = detail.product.status !== "archived";
  const label = (a: Attribute, entry: ProductTypeAttribute) => `${a.name}${a.unit ? ` (${a.unit})` : ""}${entry.required ? " *" : ""}`;

  return (
    <AdminShell
      title={name}
      breadcrumbs={breadcrumbs}
      actions={
        <>
          {canUpdate && detail.product.status === "draft" && <Button variant="primary" onClick={() => productAction("activate")}>Activar</Button>}
          {canArchive && active && <Button variant="danger" onClick={() => productAction("archive")}>Archivar</Button>}
        </>
      }
    >
      <div className="mb-5 flex items-center gap-3">
        <StatusBadge status={detail.product.status} />
        <span className="text-sm text-muted">Activo no significa publicado.</span>
      </div>

      <Tabs
        tabs={[
          { key: "general", label: "General" },
          { key: "variants", label: "Variantes", count: detail.variants.length },
          { key: "options", label: "Opciones", count: productOptions.length },
          { key: "media", label: "Medios" },
          { key: "specs", label: "Especificaciones" },
          { key: "categories", label: "Categorías", count: detail.categories.length },
          { key: "store", label: "Tienda" },
        ]}
        active={tab}
        onChange={setTab}
      />

      {tab === "general" && (
        <ProductGeneral
          productId={productId}
          locale={detail.translations[0]?.locale ?? "es-EC"}
          version={detail.product.version}
          canManage={canUpdate}
          onSaved={load}
        />
      )}

      {tab === "variants" && (
        <>
          {canCreateVariant && active && (
            <form onSubmit={createVariant} className="mb-4 flex flex-wrap items-end gap-3 rounded-xl border border-line bg-panel p-4">
              <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">Nuevo SKU</span><input name="sku" required className={inputCls} /></label>
              {productOptions.map((item) => (
                <label key={item.option_id} className="grid gap-1.5 text-sm">
                  <span className="font-medium text-text">{options.find((o) => o.id === item.option_id)?.name ?? item.option_id}</span>
                  <select name={`option-${item.option_id}`} required className={inputCls}>
                    <option value="">Selecciona</option>
                    {(valuesByOption[item.option_id] ?? []).filter((v) => v.status !== "archived").map((v) => <option key={v.id} value={v.id}>{v.value}</option>)}
                  </select>
                </label>
              ))}
              <Button variant="primary" type="submit">Crear variante</Button>
            </form>
          )}
          <div className="overflow-hidden rounded-xl border border-line bg-panel">
            {detail.variants.map((variant) => (
              <VariantEditor key={variant.id} variant={variant} editable={canVariant && variant.status !== "archived"} canArchive={permissions.includes("catalog.variant.archive")} options={options} valuesByOption={valuesByOption} onSave={updateVariant} onArchive={archiveVariant} />
            ))}
          </div>
        </>
      )}

      {tab === "options" && (
        <div className="rounded-xl border border-line bg-panel p-4">
          {productOptions.length === 0 ? (
            <p className="text-sm text-muted">Este producto no tiene opciones. Sin opciones, sus variantes no tienen combinación.</p>
          ) : (
            <div className="divide-y divide-line/60">
              {productOptions.map((item) => (
                <div key={item.option_id} className="flex items-center justify-between gap-3 py-2 text-sm">
                  <span className="text-text">{options.find((o) => o.id === item.option_id)?.name ?? item.option_id}{item.required && <span className="ml-2 text-xs text-amber-300">requerida</span>}</span>
                  {canManageProductOptions && active && <Button size="sm" variant="ghost" onClick={() => removeProductOption(item.option_id)}>Quitar</Button>}
                </div>
              ))}
            </div>
          )}
          {canManageProductOptions && active && (
            <label className="mt-3 grid max-w-sm gap-1.5 text-sm">
              <span className="font-medium text-text">Agregar opción</span>
              <select aria-label="Agregar opción" defaultValue="" className={inputCls} onChange={(e) => { addProductOption(e.target.value); e.target.value = ""; }}>
                <option value="">Selecciona</option>
                {options.filter((item) => !productOptions.some((a) => a.option_id === item.id)).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
              </select>
            </label>
          )}
        </div>
      )}

      {tab === "media" && (
        <ProductMedia productId={productId} canManage={permissions.includes("catalog.product.update")} />
      )}

      {tab === "specs" && (
        productTypeAttributes.length === 0 ? (
          <EmptyState title="Sin especificaciones" description="El tipo de este producto no tiene atributos asignados." />
        ) : (
          <form onSubmit={saveSpecifications} className="grid max-w-2xl gap-4 rounded-xl border border-line bg-panel p-4">
            {productTypeAttributes.map((entry) => {
              const attribute = attributes.find((a) => a.id === entry.attribute_id);
              if (!attribute) return null;
              const existing = attributeValues.find((v) => v.attribute_id === attribute.id);
              const l = label(attribute, entry);
              if (attribute.data_type === "BOOLEAN") return <label key={attribute.id} className="flex items-center gap-2 text-sm text-text"><input type="checkbox" name={`spec-${attribute.id}`} defaultChecked={existing?.value_boolean === true} /> {l}</label>;
              if (attribute.data_type === "LONG_TEXT") return <label key={attribute.id} className="grid gap-1.5 text-sm"><span className="font-medium text-text">{l}</span><textarea name={`spec-${attribute.id}`} defaultValue={existing?.value_long_text ?? ""} className={inputCls} /></label>;
              if (attribute.data_type === "INTEGER") return <label key={attribute.id} className="grid gap-1.5 text-sm"><span className="font-medium text-text">{l}</span><input type="number" step="1" name={`spec-${attribute.id}`} defaultValue={existing?.value_integer ?? ""} className={inputCls} /></label>;
              if (attribute.data_type === "DECIMAL") return <label key={attribute.id} className="grid gap-1.5 text-sm"><span className="font-medium text-text">{l}</span><input type="number" step="any" name={`spec-${attribute.id}`} defaultValue={existing?.value_decimal ?? ""} className={inputCls} /></label>;
              if (attribute.data_type === "DATE") return <label key={attribute.id} className="grid gap-1.5 text-sm"><span className="font-medium text-text">{l}</span><input type="date" name={`spec-${attribute.id}`} defaultValue={existing?.value_date ?? ""} className={inputCls} /></label>;
              if (attribute.data_type === "DATETIME") return <label key={attribute.id} className="grid gap-1.5 text-sm"><span className="font-medium text-text">{l}</span><input type="datetime-local" name={`spec-${attribute.id}`} defaultValue={existing?.value_datetime?.slice(0, 16) ?? ""} className={inputCls} /></label>;
              if (attribute.data_type === "SELECT") return (
                <label key={attribute.id} className="grid gap-1.5 text-sm"><span className="font-medium text-text">{l}</span>
                  <select name={`spec-${attribute.id}`} defaultValue={existing?.value_option_id ?? ""} className={inputCls}>
                    <option value="">Sin valor</option>
                    {(attributeOptions[attribute.id] ?? []).filter((o) => o.status !== "archived").map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
                  </select>
                </label>
              );
              if (attribute.data_type === "MULTI_SELECT") {
                const selectedIds = new Set(attributeValueOptions.filter((v) => v.attribute_id === attribute.id).map((v) => v.attribute_option_id));
                return (
                  <fieldset key={attribute.id} className="grid gap-1.5 text-sm">
                    <legend className="font-medium text-text">{l}</legend>
                    {(attributeOptions[attribute.id] ?? []).filter((o) => o.status !== "archived").map((o) => (
                      <label key={o.id} className="flex items-center gap-2 text-text"><input type="checkbox" name={`spec-${attribute.id}`} value={o.id} defaultChecked={selectedIds.has(o.id)} /> {o.label}</label>
                    ))}
                  </fieldset>
                );
              }
              return <label key={attribute.id} className="grid gap-1.5 text-sm"><span className="font-medium text-text">{l}</span><input name={`spec-${attribute.id}`} defaultValue={existing?.value_text ?? ""} className={inputCls} /></label>;
            })}
            {canManageSpecs && <div><Button variant="primary" type="submit">Guardar especificaciones</Button></div>}
          </form>
        )
      )}

      {tab === "categories" && (
        <div className="rounded-xl border border-line bg-panel p-4">
          {detail.categories.length === 0 ? (
            <p className="text-sm text-muted">Sin categorías asignadas.</p>
          ) : (
            <div className="mb-3 flex flex-wrap gap-2">
              {detail.categories.map((item) => (
                <StatusBadge key={item.category_id} label={`${categories.find((c) => c.id === item.category_id)?.name ?? item.category_id}${item.is_primary ? " · principal" : ""}`} tone={item.is_primary ? "brand" : "neutral"} />
              ))}
            </div>
          )}
          {canAssign && active && (
            <label className="grid max-w-sm gap-1.5 text-sm">
              <span className="font-medium text-text">Agregar categoría</span>
              <select aria-label="Agregar categoría" defaultValue="" className={inputCls} onChange={(e) => assignCategory(e.target.value)}>
                <option value="">Selecciona</option>
                {categories.filter((item) => item.status !== "archived" && !detail.categories.some((v) => v.category_id === item.id)).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
              </select>
            </label>
          )}
        </div>
      )}

      {tab === "store" && (
        <div className="grid max-w-sm gap-3 rounded-xl border border-line bg-panel p-4">
          <label className="grid gap-1.5 text-sm">
            <span className="font-medium text-text">Tienda</span>
            <select aria-label="Asignación a tienda" value={storeId} onChange={(e) => chooseStore(e.target.value)} className={inputCls}>
              <option value="">Selecciona</option>
              {stores.filter((item) => item.status !== "archived").map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </label>
          {storeId && (
            <p className="text-sm text-muted">
              {detail.stores.find((item) => item.store_id === storeId)?.status ?? "No asignado"}
              {detail.stores.find((item) => item.store_id === storeId)?.eligible ? " · elegible" : " · no elegible"}
            </p>
          )}
          {canAssign && storeId && active && (
            <div className="flex gap-2">
              <Button size="sm" variant="primary" onClick={assignStore}>Asignar</Button>
              {detail.stores.some((item) => item.store_id === storeId && item.status !== "archived") && <Button size="sm" variant="danger" onClick={unassignStore}>Retirar</Button>}
            </div>
          )}
        </div>
      )}

      {error && <p className="mt-3 text-sm text-red-300" role="alert">{error}</p>}
    </AdminShell>
  );
}

function VariantEditor({ variant, editable, canArchive, options, valuesByOption, onSave, onArchive }: { variant: Variant; editable: boolean; canArchive: boolean; options: Option[]; valuesByOption: Record<string, OptionValue[]>; onSave: (variant: Variant, sku: string) => Promise<void>; onArchive: (variant: Variant) => Promise<void> }) {
  const [sku, setSku] = useState(variant.sku);
  const [combination, setCombination] = useState<VariantOptionValue[]>([]);
  useEffect(() => {
    if (!variant.combination_fingerprint) {
      setCombination([]);
      return;
    }
    catalogGet<VariantOptionValue[]>(`/variants/${variant.id}/options`).then(setCombination).catch(() => setCombination([]));
  }, [variant.id, variant.combination_fingerprint]);
  const valueName = (item: VariantOptionValue) => (valuesByOption[item.option_id] ?? []).find((v) => v.id === item.option_value_id)?.value ?? item.option_value_id;
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line/50 px-4 py-3 last:border-0">
      <span className="text-sm">
        <span className="flex items-center gap-2">
          <span className="font-medium text-text">{variant.is_default ? "Variante por defecto" : "Variante"}</span>
          <StatusBadge status={variant.status} />
        </span>
        {combination.length > 0 && <span className="text-xs text-muted">{combination.map((item) => `${options.find((o) => o.id === item.option_id)?.name ?? item.option_id}: ${valueName(item)}`).join(" · ")}</span>}
      </span>
      <span className="flex items-center gap-2">
        {editable ? <input aria-label={`SKU ${variant.sku}`} value={sku} onChange={(e) => setSku(e.target.value)} className="w-40 rounded-lg border border-line bg-bg px-2.5 py-1.5 text-sm text-text focus:border-brand focus:outline-none" /> : <span className="text-sm text-muted">{variant.sku}</span>}
        {editable && sku !== variant.sku && <Button size="sm" variant="secondary" onClick={() => onSave(variant, sku)}>Guardar</Button>}
        {canArchive && variant.status !== "archived" && !variant.is_default && <Button size="sm" variant="danger" onClick={() => onArchive(variant)}>Archivar</Button>}
      </span>
    </div>
  );
}
