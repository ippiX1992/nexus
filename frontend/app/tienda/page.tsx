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

  const showFeatured = !search && !loading && !error && items.length >= 3;

  return (
    <div className="sf-grid-wrap">
      {showFeatured && (
        <section className="sf-featured" aria-label="Destacados">
          {items.slice(0, 3).map((product, index) => (
            <ProductCard key={product.slug} product={product} feature={index === 0} />
          ))}
        </section>
      )}
      <div className="sf-grid-head">
        <h2>{search ? `Resultados para “${search}”` : "Catálogo completo"}</h2>
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
    </div>
  );
}
