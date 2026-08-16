"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { HeroBanner } from "@/components/store/HeroBanner";
import { ProductCard } from "@/components/store/ProductCard";
import { storeCategories, storeProducts, type StoreCategory, type StoreProduct } from "@/lib/storefront";

type Section = { category: StoreCategory; items: StoreProduct[] };
const PAGE = 24;

export default function StorePage() {
  const params = useSearchParams();
  const search = params.get("search") ?? "";
  const category = params.get("category") ?? "";
  const isHome = !search && !category;

  const [items, setItems] = useState<StoreProduct[]>([]);
  const [total, setTotal] = useState(0);
  const [categories, setCategories] = useState<StoreCategory[]>([]);
  const [sections, setSections] = useState<Section[]>([]);
  const [deals, setDeals] = useState<StoreProduct[]>([]);
  const [catName, setCatName] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError("");
    (async () => {
      try {
        if (isHome) {
          const [cats, dealItems] = await Promise.all([storeCategories(), storeProducts("", "", 12)]);
          const top = cats.slice(0, 8);
          const perCategory = await Promise.all(top.map((entry) => storeProducts("", entry.slug, 12)));
          if (!alive) return;
          setCategories(cats);
          setDeals(dealItems.items);
          setSections(top.map((entry, index) => ({ category: entry, items: perCategory[index].items })));
        } else {
          const [page, cats] = await Promise.all([storeProducts(search, category, PAGE), category ? storeCategories() : Promise.resolve([])]);
          if (!alive) return;
          setItems(page.items);
          setTotal(page.total);
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

  async function loadMore() {
    setLoadingMore(true);
    try {
      const page = await storeProducts(search, category, PAGE, items.length);
      setItems((previous) => [...previous, ...page.items]);
      setTotal(page.total);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Error");
    } finally {
      setLoadingMore(false);
    }
  }

  if (loading) return <div className="sf-grid-wrap"><p className="sf-muted">Cargando productos…</p></div>;
  if (error) return <div className="sf-grid-wrap"><p className="sf-error">No se pudo cargar la tienda: {error}</p></div>;

  if (isHome) {
    return (
      <>
        <HeroBanner />
        <div className="sf-grid-wrap">
          {categories.length > 0 && (
            <section className="az-tiles" aria-label="Categorías destacadas">
              {categories.slice(0, 8).map((entry) => (
                <Link key={entry.slug} href={`/tienda?category=${entry.slug}`} className="az-tile">
                  <span className="az-tile-name">{entry.name}</span>
                  <span className="az-tile-count">{entry.product_count} productos →</span>
                </Link>
              ))}
            </section>
          )}

          {deals.length > 0 && (
            <section className="az-deals">
              <div className="az-deals-head">
                <h2>Ofertas del día</h2>
                <span className="az-deals-tag">Envío a todo el Ecuador</span>
              </div>
              <div className="sf-row">
                {deals.map((product) => (
                  <div className="sf-row-item" key={product.slug}>
                    <ProductCard product={product} />
                  </div>
                ))}
              </div>
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
      </>
    );
  }

  return (
    <div className="sf-grid-wrap">
      <div className="sf-grid-head">
        <h2>{search ? `Resultados para “${search}”` : catName}</h2>
        <span className="sf-muted">{total} productos</span>
      </div>
      {items.length === 0 ? (
        <p className="sf-muted">No encontramos productos{search ? ` para “${search}”` : ""}.</p>
      ) : (
        <>
          <div className="sf-grid">
            {items.map((product) => (
              <ProductCard key={product.slug} product={product} />
            ))}
          </div>
          {items.length < total && (
            <div className="az-more">
              <button className="az-more-btn" onClick={loadMore} disabled={loadingMore}>
                {loadingMore ? "Cargando…" : `Ver más (${items.length}/${total})`}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
