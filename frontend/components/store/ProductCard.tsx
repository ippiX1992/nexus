"use client";
import Link from "next/link";
import { formatPrice, type StoreProduct } from "@/lib/storefront";
import { useCart } from "./cart";
import { Thumb } from "./Thumb";

// Card styled after Next.js Commerce (vercel/commerce): a full-bleed media with
// a floating label (name + price pill) at the bottom, blue hover border, and a
// discreet quick-add button that appears on hover.
export function ProductCard({ product, feature = false }: { product: StoreProduct; feature?: boolean }) {
  const { add } = useCart();
  const price = product.price != null ? Number(product.price) : null;
  return (
    <div className={`sf-card${feature ? " sf-card-feat" : ""}`}>
      <Link href={`/tienda/${product.slug}`} className="sf-card-media" aria-label={product.name}>
        {product.image ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img className="sf-img" src={product.image} alt={product.name} loading="lazy" />
        ) : (
          <Thumb name={product.name} />
        )}
        <div className="sf-label">
          <h3 className="sf-label-name">{product.name}</h3>
          <span className="sf-price-pill">{formatPrice(product.price, product.currency)}</span>
        </div>
        {!product.in_stock && <span className="sf-badge">Agotado</span>}
      </Link>
      {product.in_stock && price != null && (
        <button
          className="sf-quickadd"
          aria-label={`Agregar ${product.name} al carrito`}
          onClick={() => add({ slug: product.slug, name: product.name, price, sku: product.sku, currency: product.currency, available: product.available })}
        >
          <span aria-hidden="true">+</span>
        </button>
      )}
    </div>
  );
}
