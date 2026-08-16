"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { storeCategories, type StoreCategory } from "@/lib/storefront";
import { useCart } from "./cart";

export function StoreHeader({ storeName }: { storeName: string }) {
  const router = useRouter();
  const params = useSearchParams();
  const activeCategory = params.get("category") ?? "";
  const { count, setOpen } = useCart();
  const [query, setQuery] = useState("");
  const [categories, setCategories] = useState<StoreCategory[]>([]);

  useEffect(() => {
    setQuery(params.get("search") ?? "");
  }, [params]);

  useEffect(() => {
    storeCategories()
      .then(setCategories)
      .catch(() => setCategories([]));
  }, []);

  function submit(event: FormEvent) {
    event.preventDefault();
    const term = query.trim();
    router.push(term ? `/tienda?search=${encodeURIComponent(term)}` : "/tienda");
  }

  return (
    <header className="sf-header">
      <div className="sf-header-inner">
        <Link href="/tienda" className="sf-logo">
          <span className="sf-logo-mark">CH</span>
          {storeName}
        </Link>
        <form className="sf-search" onSubmit={submit} role="search">
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Buscar productos…" aria-label="Buscar productos" />
          <button type="submit">Buscar</button>
        </form>
        <button className="sf-cart-btn" onClick={() => setOpen(true)} aria-label={`Abrir carrito, ${count} artículos`}>
          <span className="sf-cart-icon" aria-hidden="true">🛒</span>
          {count > 0 && <span className="sf-cart-count">{count}</span>}
        </button>
      </div>
      {categories.length > 0 && (
        <nav className="sf-nav" aria-label="Categorías">
          <div className="sf-nav-inner">
            <Link href="/tienda" className={`sf-nav-link${!activeCategory ? " active" : ""}`}>
              Inicio
            </Link>
            {categories.map((category) => (
              <Link
                key={category.slug}
                href={`/tienda?category=${category.slug}`}
                className={`sf-nav-link${activeCategory === category.slug ? " active" : ""}`}
              >
                {category.name}
              </Link>
            ))}
          </div>
        </nav>
      )}
    </header>
  );
}
