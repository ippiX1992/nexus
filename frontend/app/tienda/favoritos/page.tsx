"use client";
import Link from "next/link";
import { ProductCard } from "@/components/store/ProductCard";
import { useWishlist } from "@/components/store/wishlist";

export default function FavoritesPage() {
  const { items } = useWishlist();
  return (
    <div className="sf-grid-wrap">
      <nav className="sf-crumbs" aria-label="Ruta">
        <Link href="/tienda">Inicio</Link>
        <span>›</span>
        <span>Favoritos</span>
      </nav>
      <div className="sf-grid-head">
        <h2>Tus favoritos</h2>
        <span className="sf-muted">{items.length} productos</span>
      </div>
      {items.length === 0 ? (
        <p className="sf-muted">Aún no tienes favoritos. Toca el ♥ en cualquier producto para guardarlo aquí.</p>
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
