"use client";
import { useEffect, useState } from "react";
import { ProductCard } from "@/components/store/ProductCard";
import { storeProducts, type StoreProduct } from "@/lib/storefront";

export default function StorePage() {
  const [items, setItems] = useState<StoreProduct[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Read ?search from the URL on the client so this stays a plain client page
  // (no Suspense boundary needed). Re-runs when the querystring changes because
  // the Topbar search does a full router.push to /tienda?search=...
  useEffect(() => {
    const term = new URLSearchParams(window.location.search).get("search") ?? "";
    setSearch(term);
    setLoading(true);
    storeProducts(term)
      .then((page) => {
        setItems(page.items);
        setError("");
      })
      .catch((caught) => setError(caught instanceof Error ? caught.message : "Error"))
      .finally(() => setLoading(false));
  }, []);

  return (
    <>
      {!search && (
        <section className="sf-hero">
          <div className="sf-hero-copy">
            <h1>Tecnología y hogar para tu día a día</h1>
            <p>Envíos a todo el Ecuador · Precios y stock actualizados al instante</p>
          </div>
        </section>
      )}
      <section className="sf-grid-wrap">
        <div className="sf-grid-head">
          <h2>{search ? `Resultados para “${search}”` : "Catálogo"}</h2>
          {!loading && !error && <span className="sf-muted">{items.length} productos</span>}
        </div>
        {loading ? (
          <p className="sf-muted">Cargando productos…</p>
        ) : error ? (
          <p className="sf-error">No se pudo cargar la tienda: {error}</p>
        ) : items.length === 0 ? (
          <p className="sf-muted">No encontramos productos{search ? ` para “${search}”` : ""}.</p>
        ) : (
          <div className="sf-grid">
            {items.map((product) => (
              <ProductCard key={product.slug} product={product} />
            ))}
          </div>
        )}
      </section>
    </>
  );
}
