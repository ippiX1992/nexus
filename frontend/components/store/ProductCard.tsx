"use client";
import Link from "next/link";
import { formatPrice, type StoreProduct } from "@/lib/storefront";
import { useCart } from "./cart";
import { Thumb } from "./Thumb";

export function ProductCard({ product }: { product: StoreProduct }) {
  const { add } = useCart();
  const price = product.price != null ? Number(product.price) : null;
  return (
    <article className="sf-card">
      <Link href={`/tienda/${product.slug}`} className="sf-card-media">
        <Thumb name={product.name} />
        {!product.in_stock && <span className="sf-badge sf-badge-out">Agotado</span>}
      </Link>
      <div className="sf-card-body">
        {product.brand && <span className="sf-brand">{product.brand}</span>}
        <Link href={`/tienda/${product.slug}`} className="sf-card-name">
          {product.name}
        </Link>
        <div className="sf-card-foot">
          <span className="sf-price">{formatPrice(product.price, product.currency)}</span>
          <button
            className="sf-add"
            disabled={!product.in_stock || price == null}
            onClick={() =>
              price != null &&
              add({ slug: product.slug, name: product.name, price, sku: product.sku, currency: product.currency, available: product.available })
            }
          >
            Agregar
          </button>
        </div>
      </div>
    </article>
  );
}
