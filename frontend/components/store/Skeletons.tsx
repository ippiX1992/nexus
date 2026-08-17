// Shimmer placeholders shown while products load — the polished "big store"
// feel instead of a bare "Cargando…" line.
export function SkeletonGrid({ count = 12 }: { count?: number }) {
  return (
    <div className="sf-grid">
      {Array.from({ length: count }).map((_, index) => (
        <div className="sf-skel-card" key={index}>
          <div className="sf-skel sf-skel-img" />
          <div className="sf-skel sf-skel-line" />
          <div className="sf-skel sf-skel-line short" />
          <div className="sf-skel sf-skel-price" />
          <div className="sf-skel sf-skel-btn" />
        </div>
      ))}
    </div>
  );
}
