"use client";
import Link from "next/link";
import { formatPrice, type StoreProduct } from "@/lib/storefront";
import { useCart } from "./cart";
import { Stars } from "./Stars";
import { Thumb } from "./Thumb";
import { useUI } from "./ui";
import { useWishlist } from "./wishlist";

// Amazon-style product card: white tile, product image on top, blue title link,
// bold price, stock note and a yellow "Agregar al carro" button.
export function ProductCard({ product }: { product: StoreProduct }) {
  const { add } = useCart();
  const { has, toggle } = useWishlist();
  const { showToast, openQuickView } = useUI();
  const price = product.price != null ? Number(product.price) : null;
  return (
    <div className="az-card">
      <button
        className={`az-fav${has(product.slug) ? " active" : ""}`}
        onClick={() => toggle(product)}
        aria-label={has(product.slug) ? "Quitar de favoritos" : "Agregar a favoritos"}
      >
        ♥
      </button>
      <Link href={`/tienda/${product.slug}`} className="az-card-img" aria-label={product.name}>
        {product.image ? (
          <>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={product.image} alt={product.name} loading="lazy" />
            {product.image2 && (
              // eslint-disable-next-line @next/next/no-img-element
              <img className="az-card-img2" src={product.image2} alt="" loading="lazy" />
            )}
          </>
        ) : (
          <Thumb name={product.name} />
        )}
        <button
          className="az-quick"
          onClick={(event) => {
            event.preventDefault();
            event.stopPropagation();
            openQuickView(product.slug);
          }}
        >
          Vista rápida
        </button>
      </Link>
      {product.brand && <span className="az-card-brand">{product.brand}</span>}
      <Link href={`/tienda/${product.slug}`} className="az-card-title">
        {product.name}
      </Link>
      <Stars seed={product.slug} />
      <div className="az-card-price">{price != null ? formatPrice(product.price, product.currency) : "Consultar"}</div>
      <div className={`az-card-stock ${product.in_stock ? "in" : "out"}`}>{product.in_stock ? "Disponible" : "Agotado"}</div>
      {product.in_stock && price != null && (
        <button
          className="az-add"
          onClick={() => {
            add({ slug: product.slug, name: product.name, price, sku: product.sku, currency: product.currency, available: product.available });
            showToast("Agregado al carrito ✓");
          }}
        >
          Agregar al carro
        </button>
      )}
    </div>
  );
}
