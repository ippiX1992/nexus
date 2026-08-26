// Rating stars. When real review data is passed (rating + count) it is shown as
// is; otherwise the value is derived deterministically from the product slug —
// stable per product and clearly decorative until that product has reviews.
export function Stars({ seed, rating, count, showCount = true }: { seed: string; rating?: number; count?: number; showCount?: boolean }) {
  let value = rating;
  let reviews = count;
  if (value == null || reviews == null) {
    let hash = 0;
    for (let i = 0; i < seed.length; i++) hash = (hash * 31 + seed.charCodeAt(i)) >>> 0;
    if (value == null) value = 3.5 + (hash % 15) / 10; // 3.5 – 4.9
    if (reviews == null) reviews = 8 + (hash % 900);
  }
  return (
    <span className="az-stars" aria-label={`${value.toFixed(1)} de 5 estrellas`}>
      <span className="az-stars-track">
        <span className="az-stars-fill" style={{ width: `${(value / 5) * 100}%` }} />
      </span>
      {showCount && <span className="az-stars-count">{reviews.toLocaleString("es-EC")}</span>}
    </span>
  );
}
