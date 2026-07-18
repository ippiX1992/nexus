"use client";
import Link from "next/link";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { AdminShell } from "@/components/admin/AdminShell";
import { EmptyState } from "@/components/admin/EmptyState";
import { catalogContext, catalogPage, Product, technicalError } from "@/lib/catalog";

export default function Page() {
  return (
    <Suspense fallback={<AdminShell title="Products">Cargando…</AdminShell>}>
      <ProductsList />
    </Suspense>
  );
}

function ProductsList() {
  const searchParams = useSearchParams();
  const search = searchParams.get("search") ?? "";
  const [items, setItems] = useState<Product[]>([]);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [cursor, setCursor] = useState<string | undefined>();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  async function load(next?: string, append = false) {
    setLoading(true);
    try {
      const query = `?limit=25${next ? `&cursor=${encodeURIComponent(next)}` : ""}${search ? `&search=${encodeURIComponent(search)}` : ""}`;
      const [page, ctx] = await Promise.all([catalogPage<Product>(`/products${query}`), catalogContext()]);
      setItems((previous) => (append ? [...previous, ...page.items] : page.items));
      setCursor(page.next_cursor);
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  return (
    <AdminShell
      title="Products"
      description={search ? `Resultados para "${search}"` : "Catálogo de productos del tenant activo."}
      actions={
        permissions.includes("catalog.product.create") && (
          <Link className="button compact" href="/catalog/products/new">
            Crear Product
          </Link>
        )
      }
    >
      {loading && items.length === 0 ? (
        <p>Cargando…</p>
      ) : items.length === 0 ? (
        <EmptyState
          title={search ? "Sin resultados" : "No hay Products"}
          description={search ? `Nada coincide con "${search}".` : "Crea el primero para iniciar el catálogo."}
        />
      ) : (
        items.map((item) => (
          <div className="row" key={item.id}>
            <span>
              <Link href={`/catalog/products/${item.id}`}>
                <strong>{item.name ?? item.code ?? item.id}</strong>
              </Link>
              <br />
              {item.default_sku ?? "Sin SKU"} · {item.status} · v{item.version}
            </span>
          </div>
        ))
      )}
      {cursor && (
        <button className="compact" disabled={loading} onClick={() => load(cursor, true)}>
          {loading ? "Cargando…" : "Cargar más"}
        </button>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </AdminShell>
  );
}
