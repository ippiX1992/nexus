"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { Carousel } from "@/components/store/Carousel";
import { HeroBanner } from "@/components/store/HeroBanner";
import { ProductCard } from "@/components/store/ProductCard";
import { SkeletonGrid } from "@/components/store/Skeletons";
import { storeCategories, storeProducts, type StoreCategory, type StoreProduct } from "@/lib/storefront";

type Section = { category: StoreCategory; items: StoreProduct[] };
const PAGE = 24;

export default function StorePage() {
  const params = useSearchParams();
  const router = useRouter();
  const search = params.get("search") ?? "";
  const category = params.get("category") ?? "";
  const sort = params.get("sort") ?? "name";
  const minPrice = params.get("min") ?? "";
  const maxPrice = params.get("max") ?? "";
  const isHome = !search && !category;

  function changeSort(value: string) {
    const next = new URLSearchParams(Array.from(params.entries()));
    if (value === "name") next.delete("sort");
    else next.set("sort", value);
    router.push(`/tienda?${next.toString()}`);
  }

  function applyPrice(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const next = new URLSearchParams(Array.from(params.entries()));
    for (const [field, key] of [["min", "min"], ["max", "max"]] as const) {
      const value = String(form.get(field) || "").trim();
      if (value) next.set(key, value);
      else next.delete(key);
    }
    router.push(`/tienda?${next.toString()}`);
  }

  const [items, setItems] = useState<StoreProduct[]>([]);
  const [total, setTotal] = useState(0);
  const [categories, setCategories] = useState<StoreCategory[]>([]);
  const [sections, setSections] = useState<Section[]>([]);
  const [deals, setDeals] = useState<StoreProduct[]>([]);
  const [newest, setNewest] = useState<StoreProduct[]>([]);
  const [featured, setFeatured] = useState<StoreProduct[]>([]);
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
          const [cats, dealItems, newestItems, randomItems] = await Promise.all([
            storeCategories(),
            storeProducts("", "", 12, 0, "random"),
            storeProducts("", "", 16, 0, "newest"),
            storeProducts("", "", 16, 0, "random"),
          ]);
          // Same curation as the header: real departments, not the flat category noise.
          const departments = cats.filter((entry) => entry.product_count >= 15 || (entry.children?.length ?? 0) > 0);
          const top = departments.slice(0, 8);
          const perCategory = await Promise.all(top.map((entry) => storeProducts("", entry.slug, 12)));
          if (!alive) return;
          setCategories(departments);
          setDeals(dealItems.items);
          setNewest(newestItems.items);
          setFeatured(randomItems.items);
          setSections(top.map((entry, index) => ({ category: entry, items: perCategory[index].items })));
        } else {
          const [page, cats] = await Promise.all([
            storeProducts(search, category, PAGE, 0, sort, Number(minPrice) || 0, Number(maxPrice) || 0),
            category ? storeCategories() : Promise.resolve([]),
          ]);
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
  }, [search, category, sort, minPrice, maxPrice, isHome]);

  async function loadMore() {
    setLoadingMore(true);
    try {
      const page = await storeProducts(search, category, PAGE, items.length, sort, Number(minPrice) || 0, Number(maxPrice) || 0);
      setItems((previous) => [...previous, ...page.items]);
      setTotal(page.total);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Error");
    } finally {
      setLoadingMore(false);
    }
  }

  if (loading)
    return (
      <div className="sf-grid-wrap">
        <div className="sf-grid-head">
          <span className="sf-skel sf-skel-heading" />
        </div>
        <SkeletonGrid />
      </div>
    );
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

          {newest.length > 0 && (
            <section className="sf-section">
              <div className="sf-section-head">
                <h2>✨ Novedades</h2>
              </div>
              <Carousel>
                {newest.map((product) => (
                  <div className="sf-carousel-item" key={product.slug}>
                    <ProductCard product={product} />
                  </div>
                ))}
              </Carousel>
            </section>
          )}

          {featured.length > 0 && (
            <section className="sf-section">
              <div className="sf-section-head">
                <h2>Recomendados para ti</h2>
              </div>
              <Carousel>
                {featured.map((product) => (
                  <div className="sf-carousel-item" key={product.slug}>
                    <ProductCard product={product} />
                  </div>
                ))}
              </Carousel>
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
      <nav className="sf-crumbs" aria-label="Ruta">
        <Link href="/tienda">Inicio</Link>
        <span>›</span>
        <span>{search ? `Búsqueda: “${search}”` : catName}</span>
      </nav>
      <div className="sf-grid-head">
        <h2>{search ? `Resultados para “${search}”` : catName}</h2>
        <div className="az-toolbar">
          <span className="sf-muted">{total} productos</span>
          <form className="az-price" onSubmit={applyPrice}>
            <input name="min" type="number" min="0" step="0.01" placeholder="Mín" defaultValue={minPrice} aria-label="Precio mínimo" />
            <span>–</span>
            <input name="max" type="number" min="0" step="0.01" placeholder="Máx" defaultValue={maxPrice} aria-label="Precio máximo" />
            <button type="submit">Filtrar</button>
          </form>
          <label className="az-sort">
            Ordenar:
            <select value={sort} onChange={(event) => changeSort(event.target.value)}>
              <option value="name">Relevancia</option>
              <option value="price_asc">Precio: menor a mayor</option>
              <option value="price_desc">Precio: mayor a menor</option>
            </select>
          </label>
        </div>
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
