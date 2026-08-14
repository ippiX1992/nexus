"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { AdminShell } from "@/components/admin/AdminShell";
import { EmptyState } from "@/components/admin/EmptyState";
import { catalogContext, catalogPage, Product, technicalError } from "@/lib/catalog";

// The "search" filter comes from the Topbar search box, which navigates to
// /catalog/products?search=... . We read it from window.location on the client
// instead of next/navigation's useSearchParams so the page does NOT need a
// Suspense boundary -- with the Suspense+useSearchParams pattern the fallback
// could stick on a direct URL load. Reading it in an effect keeps this a plain
// client page that renders immediately like every other catalog list.
export default function Page() {
  const [items, setItems] = useState<Product[]>([]);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [cursor, setCursor] = useState<string | undefined>();
  const [search, setSearch] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const current = new URLSearchParams(window.location.search).get("search") ?? "";
    setSearch(current);
    load(current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function load(term: string, next?: string, append = false) {
    setLoading(true);
    try {
      const query = `?limit=25${next ? `&cursor=${encodeURIComponent(next)}` : ""}${term ? `&search=${encodeURIComponent(term)}` : ""}`;
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
        <button className="compact" disabled={loading} onClick={() => load(search, cursor, true)}>
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
