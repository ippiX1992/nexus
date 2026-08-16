// Placeholder rating stars. The catalog has no review data, so the rating and
// review count are derived deterministically from the product slug — stable per
// product and clearly decorative (not real customer reviews).
export function Stars({ seed, showCount = true }: { seed: string; showCount?: boolean }) {
  let hash = 0;
  for (let i = 0; i < seed.length; i++) hash = (hash * 31 + seed.charCodeAt(i)) >>> 0;
  const rating = 3.5 + (hash % 15) / 10; // 3.5 – 4.9
  const reviews = 8 + (hash % 900);
  return (
    <span className="az-stars" aria-label={`${rating.toFixed(1)} de 5 estrellas`}>
      <span className="az-stars-track">
        <span className="az-stars-fill" style={{ width: `${(rating / 5) * 100}%` }} />
      </span>
      {showCount && <span className="az-stars-count">{reviews.toLocaleString("es-EC")}</span>}
    </span>
  );
}
