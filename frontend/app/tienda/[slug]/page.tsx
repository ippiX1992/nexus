"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { useCart } from "@/components/store/cart";
import { Stars } from "@/components/store/Stars";
import { Thumb } from "@/components/store/Thumb";
import { formatPrice, storeProduct, type StoreProductDetail } from "@/lib/storefront";

export default function ProductPage() {
  const params = useParams();
  const slug = String(params.slug);
  const { add } = useCart();
  const [product, setProduct] = useState<StoreProductDetail | null>(null);
  const [qty, setQty] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoading(true);
    storeProduct(slug)
      .then(setProduct)
      .catch((caught) => setError(caught instanceof Error ? caught.message : "Error"))
      .finally(() => setLoading(false));
  }, [slug]);

  if (loading) return <p className="sf-muted sf-pad">Cargando…</p>;
  if (error || !product)
    return (
      <div className="sf-pad">
        <p className="sf-error">{error || "Producto no encontrado"}</p>
        <Link className="sf-back" href="/tienda">
          ← Volver al catálogo
        </Link>
      </div>
    );

  const price = product.price != null ? Number(product.price) : null;

  return (
    <article className="sf-detail">
      <Link className="sf-back" href="/tienda">
        ← Volver al catálogo
      </Link>
      <div className="sf-detail-grid">
        <div className="sf-detail-media">
          {product.image ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img className="sf-img" src={product.image} alt={product.name} />
          ) : (
            <Thumb name={product.name} />
          )}
        </div>
        <div className="sf-detail-info">
          {product.brand && <span className="sf-brand">{product.brand}</span>}
          <h1>{product.name}</h1>
          <Stars seed={product.slug} />
          <div className="sf-detail-price">{formatPrice(product.price, product.currency)}</div>
          <div className={`sf-stock ${product.in_stock ? "in" : "out"}`}>
            {product.in_stock ? `En stock · ${product.available} disponibles` : "Agotado"}
          </div>
          {product.in_stock && price != null && (
            <div className="sf-buy">
              <div className="sf-stepper">
                <button onClick={() => setQty((current) => Math.max(1, current - 1))} aria-label="Quitar uno">
                  −
                </button>
                <span>{qty}</span>
                <button onClick={() => setQty((current) => Math.min(product.available, current + 1))} aria-label="Agregar uno">
                  +
                </button>
              </div>
              <button
                className="sf-add sf-add-lg"
                onClick={() =>
                  add(
                    { slug: product.slug, name: product.name, price, sku: product.sku, currency: product.currency, available: product.available },
                    qty,
                  )
                }
              >
                Agregar al carrito
              </button>
            </div>
          )}
          <p className="sf-sku">SKU: {product.sku}</p>
          {product.long_description && (
            <div className="sf-desc">
              <h3>Descripción</h3>
              <p>{product.long_description}</p>
            </div>
          )}
        </div>
      </div>
    </article>
  );
}
