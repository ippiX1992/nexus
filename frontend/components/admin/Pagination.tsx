"use client";
import { Button } from "./Button";

/** Cursor-style "load more" with a shown/total count. Keeps list pages
 *  consistent without inventing per-page pagination UIs. */
export function LoadMore({
  onMore,
  loading,
  hasMore,
  shown,
  total,
}: {
  onMore: () => void;
  loading?: boolean;
  hasMore: boolean;
  shown: number;
  total?: number;
}) {
  if (!hasMore && !total) return null;
  return (
    <div className="mt-4 flex items-center justify-between gap-3">
      <p className="text-xs text-muted">
        {shown}
        {total ? ` de ${total}` : ""} {shown === 1 ? "resultado" : "resultados"}
      </p>
      {hasMore && (
        <Button size="sm" onClick={onMore} disabled={loading}>
          {loading ? "Cargando…" : "Cargar más"}
        </Button>
      )}
    </div>
  );
}
