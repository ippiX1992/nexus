"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { useCart } from "@/components/store/cart";
import { Stars } from "@/components/store/Stars";
import { Thumb } from "@/components/store/Thumb";
import { useUI } from "@/components/store/ui";
import { useWishlist } from "@/components/store/wishlist";
import { createReview, formatPrice, getReviews, storeProduct, type ReviewSummary, type StoreProductDetail } from "@/lib/storefront";

export default function ProductPage() {
  const params = useParams();
  const slug = String(params.slug);
  const { add } = useCart();
  const { has, toggle } = useWishlist();
  const { showToast } = useUI();
  const [product, setProduct] = useState<StoreProductDetail | null>(null);
  const [qty, setQty] = useState(1);
  const [activeImage, setActiveImage] = useState(0);
  const [reviews, setReviews] = useState<ReviewSummary | null>(null);
  const [reviewBusy, setReviewBusy] = useState(false);
  const [activeTab, setActiveTab] = useState<"desc" | "specs" | "reviews">("desc");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoading(true);
    setActiveImage(0);
    setReviews(null);
    storeProduct(slug)
      .then(setProduct)
      .catch((caught) => setError(caught instanceof Error ? caught.message : "Error"))
      .finally(() => setLoading(false));
    getReviews(slug).then(setReviews).catch(() => setReviews(null));
  }, [slug]);

  async function submitReview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const author = String(form.get("author") || "").trim();
    const rating = Number(form.get("rating") || 5);
    if (author.length < 2) return;
    setReviewBusy(true);
    try {
      setReviews(await createReview(slug, { author, rating, comment: String(form.get("comment") || "") || undefined }));
      event.currentTarget.reset();
    } catch {
      /* ignore */
    } finally {
      setReviewBusy(false);
    }
  }

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
  const gallery = product.images && product.images.length ? product.images : product.image ? [product.image] : [];

  return (
    <article className="sf-detail">
      <nav className="sf-crumbs" aria-label="Ruta">
        <Link href="/tienda">Inicio</Link>
        <span>›</span>
        {product.brand && (
          <>
            <span>{product.brand}</span>
            <span>›</span>
          </>
        )}
        <span className="sf-crumbs-current">{product.name.length > 60 ? `${product.name.slice(0, 60)}…` : product.name}</span>
      </nav>
      <div className="sf-detail-grid">
        <div className="sf-detail-gallery">
          <div className="sf-detail-media">
            {gallery.length > 0 ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img className="sf-img" src={gallery[activeImage]} alt={product.name} />
            ) : (
              <Thumb name={product.name} />
            )}
          </div>
          {gallery.length > 1 && (
            <div className="sf-gallery-thumbs">
              {gallery.map((src, index) => (
                <button
                  key={src}
                  className={`sf-gallery-thumb${index === activeImage ? " active" : ""}`}
                  onMouseEnter={() => setActiveImage(index)}
                  onClick={() => setActiveImage(index)}
                  aria-label={`Foto ${index + 1}`}
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={src} alt="" loading="lazy" />
                </button>
              ))}
            </div>
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
                onClick={() => {
                  add(
                    { slug: product.slug, name: product.name, price, sku: product.sku, currency: product.currency, available: product.available },
                    qty,
                  );
                  showToast("Agregado al carrito ✓");
                }}
              >
                Agregar al carrito
              </button>
            </div>
          )}
          <button className={`sf-fav-btn${has(product.slug) ? " active" : ""}`} onClick={() => toggle(product)}>
            {has(product.slug) ? "♥ En favoritos" : "♡ Guardar en favoritos"}
          </button>
          <p className="sf-sku">SKU: {product.sku}</p>
          <div className="sf-guarantees">
            <span>🛡️ 12 meses de garantía</span>
            <span>↩️ Devolución en 7 días</span>
            <span>🚚 Envío a todo el Ecuador</span>
          </div>
        </div>
      </div>

      <section className="sf-tabs">
        <div className="sf-tabs-head" role="tablist">
          <button role="tab" className={activeTab === "desc" ? "active" : ""} onClick={() => setActiveTab("desc")}>
            Descripción
          </button>
          <button role="tab" className={activeTab === "specs" ? "active" : ""} onClick={() => setActiveTab("specs")}>
            Especificaciones
          </button>
          <button role="tab" className={activeTab === "reviews" ? "active" : ""} onClick={() => setActiveTab("reviews")}>
            Opiniones{reviews && reviews.count > 0 ? ` (${reviews.count})` : ""}
          </button>
        </div>

        {activeTab === "desc" && (
          <div className="sf-tab-panel sf-desc">
            {product.long_description ? <p>{product.long_description}</p> : <p className="sf-muted">Sin descripción disponible.</p>}
          </div>
        )}

        {activeTab === "specs" && (
          <div className="sf-tab-panel sf-specs">
            <table>
              <tbody>
                {(product.specs ?? []).map((spec) => (
                  <tr key={spec.label}>
                    <th>{spec.label}</th>
                    <td>{spec.value}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {activeTab === "reviews" && (
          <div className="sf-tab-panel">
            <p className="sf-reviews-avg">
              {reviews && reviews.count > 0 ? `${reviews.average.toFixed(1)} ★ · ${reviews.count} opiniones` : "Aún sin opiniones"}
            </p>
            {reviews?.items.map((review, index) => (
              <div className="sf-review" key={index}>
                <div className="sf-review-head">
                  <strong>{review.author}</strong>
                  <span className="sf-review-stars">
                    {"★".repeat(review.rating)}
                    {"☆".repeat(5 - review.rating)}
                  </span>
                </div>
                {review.comment && <p>{review.comment}</p>}
              </div>
            ))}
            <form className="sf-review-form" onSubmit={submitReview}>
              <strong>Deja tu opinión</strong>
              <input name="author" placeholder="Tu nombre" required minLength={2} />
              <select name="rating" defaultValue="5">
                <option value="5">★★★★★ (5)</option>
                <option value="4">★★★★ (4)</option>
                <option value="3">★★★ (3)</option>
                <option value="2">★★ (2)</option>
                <option value="1">★ (1)</option>
              </select>
              <textarea name="comment" rows={2} placeholder="Cuéntanos tu experiencia (opcional)" />
              <button disabled={reviewBusy}>{reviewBusy ? "Enviando…" : "Publicar opinión"}</button>
            </form>
          </div>
        )}
      </section>
    </article>
  );
}
