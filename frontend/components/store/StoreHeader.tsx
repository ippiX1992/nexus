"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { storeCategories, type StoreCategory } from "@/lib/storefront";
import { useCart } from "./cart";
import { useWishlist } from "./wishlist";

export function StoreHeader({ storeName }: { storeName: string }) {
  const router = useRouter();
  const params = useSearchParams();
  const activeCategory = params.get("category") ?? "";
  const { count, setOpen } = useCart();
  const { count: favCount } = useWishlist();
  const [query, setQuery] = useState("");
  const [dept, setDept] = useState("");
  const [categories, setCategories] = useState<StoreCategory[]>([]);
  const [menuOpen, setMenuOpen] = useState(false);
  // ClickHome's real nav curates a handful of departments, not the ~27 flat
  // categories that hang off "Inicio". We mirror that: show only substantial
  // departments (or any with subcategories); niche/marketing ones stay findable
  // via search but out of the menu.
  const departments = categories.filter((category) => category.product_count >= 15 || (category.children?.length ?? 0) > 0);

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
    const next = new URLSearchParams();
    if (query.trim()) next.set("search", query.trim());
    if (dept) next.set("category", dept);
    router.push(`/tienda${next.toString() ? `?${next}` : ""}`);
  }

  return (
    <header className="az-header">
      <div className="az-top">
        <Link href="/tienda" className="az-logo">
          <span className="az-logo-mark">CH</span>
          <span className="az-logo-text">{storeName}</span>
        </Link>
        <form className="az-search" onSubmit={submit} role="search">
          <select className="az-search-dept" value={dept} onChange={(event) => setDept(event.target.value)} aria-label="Departamento">
            <option value="">Todo</option>
            {categories.map((category) => (
              <option key={category.slug} value={category.slug}>
                {category.name}
              </option>
            ))}
          </select>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={`Buscar en ${storeName}`} aria-label="Buscar productos" />
          <button type="submit" className="az-search-btn" aria-label="Buscar">
            🔍
          </button>
        </form>
        <Link href="/tienda/favoritos" className="az-orders">
          <span aria-hidden="true">♥</span>
          <span className="az-orders-label">Favoritos{favCount > 0 ? ` (${favCount})` : ""}</span>
        </Link>
        <Link href="/tienda/rastrear" className="az-orders">
          <span aria-hidden="true">📦</span>
          <span className="az-orders-label">Pedidos</span>
        </Link>
        <button className="az-cart" onClick={() => setOpen(true)} aria-label={`Carrito, ${count} artículos`}>
          <span className="az-cart-stack">
            <span className="az-cart-ico" aria-hidden="true">🛒</span>
            {count > 0 && <span className="az-cart-count">{count}</span>}
          </span>
          <span className="az-cart-label">Carrito</span>
        </button>
      </div>
      <div className="az-sub">
        <button className="az-all" onClick={() => setMenuOpen(true)} aria-label="Todas las categorías">
          <span aria-hidden="true">☰</span> Todos
        </button>
        {departments.map((category) => (
          <Link
            key={category.slug}
            href={`/tienda?category=${category.slug}`}
            className={`az-sub-link${activeCategory === category.slug ? " active" : ""}`}
          >
            {category.name}
          </Link>
        ))}
      </div>

      <div className={`az-menu-scrim${menuOpen ? " open" : ""}`} onClick={() => setMenuOpen(false)} aria-hidden="true" />
      <aside className={`az-menu${menuOpen ? " open" : ""}`} aria-label="Todas las categorías" aria-hidden={!menuOpen}>
        <div className="az-menu-head">
          <strong>Todas las categorías</strong>
          <button className="az-menu-close" onClick={() => setMenuOpen(false)} aria-label="Cerrar">
            ✕
          </button>
        </div>
        <nav className="az-menu-list">
          <Link href="/tienda" className="az-menu-top" onClick={() => setMenuOpen(false)}>
            Inicio
          </Link>
          {departments.map((category) => (
            <div className="az-menu-group" key={category.slug}>
              <Link className="az-menu-top" href={`/tienda?category=${category.slug}`} onClick={() => setMenuOpen(false)}>
                {category.name}
                <span>{category.product_count}</span>
              </Link>
              {category.children?.map((child) => (
                <Link
                  className="az-menu-child"
                  key={child.slug}
                  href={`/tienda?category=${child.slug}`}
                  onClick={() => setMenuOpen(false)}
                >
                  {child.name}
                  <span>{child.product_count}</span>
                </Link>
              ))}
            </div>
          ))}
        </nav>
      </aside>
    </header>
  );
}
