"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { useCart } from "./cart";

export function StoreHeader({ storeName }: { storeName: string }) {
  const router = useRouter();
  const { count, setOpen } = useCart();
  const [query, setQuery] = useState("");

  // Prefill the box from the URL without useSearchParams (avoids a Suspense
  // boundary); this is a client component so window is available in the effect.
  useEffect(() => {
    setQuery(new URLSearchParams(window.location.search).get("search") ?? "");
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
          <span className="sf-logo-mark">◆</span>
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
    </header>
  );
}
