"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { formatPrice, imageAt, storeProduct, type StoreProductDetail } from "@/lib/storefront";
import { useCart } from "./cart";
import { Stars } from "./Stars";
import { Thumb } from "./Thumb";
import { useUI } from "./ui";

export function QuickView() {
  const { quickViewSlug, closeQuickView, showToast } = useUI();
  const { add } = useCart();
  const [product, setProduct] = useState<StoreProductDetail | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!quickViewSlug) {
      setProduct(null);
      return;
    }
    setLoading(true);
    storeProduct(quickViewSlug)
      .then(setProduct)
      .catch(() => setProduct(null))
      .finally(() => setLoading(false));
  }, [quickViewSlug]);

  if (!quickViewSlug) return null;
  const price = product?.price != null ? Number(product.price) : null;

  return (
    <>
      <div className="sf-qv-scrim" onClick={closeQuickView} aria-hidden="true" />
      <div className="sf-qv" role="dialog" aria-modal="true" aria-label="Vista rápida del producto">
        <button className="sf-qv-close" onClick={closeQuickView} aria-label="Cerrar">
          ✕
        </button>
        {loading || !product ? (
          <p className="sf-muted sf-pad">Cargando…</p>
        ) : (
          <div className="sf-qv-grid">
            <div className="sf-qv-media">
              {product.image ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={imageAt(product.image, "thickbox")!} alt={product.name} />
              ) : (
                <Thumb name={product.name} />
              )}
            </div>
            <div className="sf-qv-info">
              {product.brand && <span className="sf-brand">{product.brand}</span>}
              <h2>{product.name}</h2>
              <Stars seed={product.slug} />
              <div className="sf-detail-price">{formatPrice(product.price, product.currency)}</div>
              <div className={`sf-stock ${product.in_stock ? "in" : "out"}`}>
                {product.in_stock ? `En stock · ${product.available} disponibles` : "Agotado"}
              </div>
              {product.short_description && <p className="sf-qv-desc">{product.short_description}</p>}
              {product.in_stock && price != null && (
                <button
                  className="sf-add sf-add-lg"
                  onClick={() => {
                    add({ slug: product.slug, name: product.name, price, sku: product.sku, currency: product.currency, available: product.available });
                    showToast("Agregado al carrito ✓");
                    closeQuickView();
                  }}
                >
                  Agregar al carrito
                </button>
              )}
              <Link className="sf-qv-full" href={`/tienda/${product.slug}`} onClick={closeQuickView}>
                Ver ficha completa →
              </Link>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
