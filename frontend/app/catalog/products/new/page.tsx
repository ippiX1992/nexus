"use client";
import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";
import { inputCls } from "@/components/admin/forms";
import { AdminShell } from "@/components/admin/AdminShell";
import { Button, LinkButton } from "@/components/admin/Button";
import { Field, FormSection } from "@/components/admin/FormSection";
import { type Brand, catalogCreate, catalogPage, type ProductDetail, type ProductType, technicalError } from "@/lib/catalog";


export default function Page() {
  const router = useRouter();
  const [types, setTypes] = useState<ProductType[]>([]);
  const [brands, setBrands] = useState<Brand[]>([]);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    Promise.all([catalogPage<ProductType>("/product-types?status=active"), catalogPage<Brand>("/brands?status=active")])
      .then(([a, b]) => {
        setTypes(a.items);
        setBrands(b.items);
      })
      .catch((e) => setError(technicalError(e)));
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    const form = new FormData(event.currentTarget);
    try {
      const product = await catalogCreate<ProductDetail>("/products", {
        product_type_id: form.get("product_type_id"),
        brand_id: form.get("brand_id") || null,
        code: form.get("code") || null,
        sku: form.get("sku"),
        translation: { locale: form.get("locale"), name: form.get("name"), slug: form.get("slug"), short_description: null, long_description: null },
      });
      router.push(`/catalog/products/${product.product.id}`);
    } catch (e) {
      setError(technicalError(e));
      setSaving(false);
    }
  }

  return (
    <AdminShell title="Nuevo producto" description="Crea el producto base. Las variantes, precios y stock se configuran después en su ficha.">
      {types.length === 0 && (
        <p className="mb-4 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-300">
          Primero crea un tipo de producto activo (Configuración avanzada → Tipos de producto).
        </p>
      )}
      <form onSubmit={submit} className="max-w-3xl">
        <FormSection title="Información general" description="Cómo se llama y se organiza el producto.">
          <Field label="Nombre">
            <input name="name" required className={inputCls} />
          </Field>
          <Field label="Slug" hint="Identificador para la URL, p. ej. licuadora-oster-negra.">
            <input name="slug" required className={inputCls} />
          </Field>
          <Field label="Tipo de producto">
            <select name="product_type_id" required className={inputCls}>
              <option value="">Selecciona…</option>
              {types.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Marca">
            <select name="brand_id" className={inputCls}>
              <option value="">Sin marca</option>
              {brands.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </Field>
        </FormSection>

        <FormSection title="Identificación" description="Códigos internos e idioma del contenido.">
          <Field label="SKU" hint="Código único del producto en tu inventario.">
            <input name="sku" required className={inputCls} />
          </Field>
          <Field label="Código interno (opcional)">
            <input name="code" className={inputCls} />
          </Field>
          <Field label="Idioma">
            <input name="locale" defaultValue="es-EC" required className={inputCls} />
          </Field>
        </FormSection>

        <div className="mt-6 flex gap-2 border-t border-line pt-6">
          <Button variant="primary" type="submit" disabled={saving || types.length === 0}>
            {saving ? "Creando…" : "Crear producto"}
          </Button>
          <LinkButton href="/catalog/products" variant="secondary">
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
