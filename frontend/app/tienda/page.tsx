"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ProductCard } from "@/components/store/ProductCard";
import { storeCategories, storeProducts, type StoreCategory, type StoreProduct } from "@/lib/storefront";

type Section = { category: StoreCategory; items: StoreProduct[] };

export default function StorePage() {
  const params = useSearchParams();
  const search = params.get("search") ?? "";
  const category = params.get("category") ?? "";
  const isHome = !search && !category;

  const [items, setItems] = useState<StoreProduct[]>([]);
  const [featured, setFeatured] = useState<StoreProduct[]>([]);
  const [sections, setSections] = useState<Section[]>([]);
  const [catName, setCatName] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError("");
    (async () => {
      try {
        if (isHome) {
          const [cats, all] = await Promise.all([storeCategories(), storeProducts()]);
          const perCategory = await Promise.all(cats.map((entry) => storeProducts("", entry.slug)));
          if (!alive) return;
          setFeatured(all.items.slice(0, 3));
          setSections(cats.map((entry, index) => ({ category: entry, items: perCategory[index].items })));
        } else {
          const [page, cats] = await Promise.all([storeProducts(search, category), category ? storeCategories() : Promise.resolve([])]);
          if (!alive) return;
          setItems(page.items);
          setCatName(cats.find((entry) => entry.slug === category)?.name ?? category);
        }
      } catch (caught) {
        if (alive) setError(caught instanceof Error ? caught.message : "Error");
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [search, category, isHome]);

  if (loading) return <div className="sf-grid-wrap"><p className="sf-muted">Cargando productos…</p></div>;
  if (error) return <div className="sf-grid-wrap"><p className="sf-error">No se pudo cargar la tienda: {error}</p></div>;

  if (isHome) {
    return (
      <div className="sf-grid-wrap">
        {featured.length >= 3 && (
          <section className="sf-featured" aria-label="Destacados">
            {featured.map((product, index) => (
              <ProductCard key={product.slug} product={product} feature={index === 0} />
            ))}
          </section>
        )}
        {sections.map((section) => (
          <section className="sf-section" key={section.category.slug}>
            <div className="sf-section-head">
              <h2>{section.category.name}</h2>
              <Link className="sf-seeall" href={`/tienda?category=${section.category.slug}`}>
                Ver todo ({section.category.product_count}) →
              </Link>
            </div>
            <div className="sf-row">
              {section.items.map((product) => (
                <div className="sf-row-item" key={product.slug}>
                  <ProductCard product={product} />
                </div>
              ))}
            </div>
          </section>
        ))}
      </div>
    );
  }

  return (
    <div className="sf-grid-wrap">
      <div className="sf-grid-head">
        <h2>{search ? `Resultados para “${search}”` : catName}</h2>
        <span className="sf-muted">{items.length} productos</span>
      </div>
      {items.length === 0 ? (
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
