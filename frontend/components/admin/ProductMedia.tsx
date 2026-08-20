"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { inputCls } from "@/components/admin/forms";
import { api, apiUpload } from "@/lib/api";

type MediaItem = {
  id: string;
  media_type: "image" | "video";
  url: string;
  alt_text: string | null;
  position: number;
  is_primary: boolean;
};

// Product media manager: upload photos (stored on the server), set the cover,
// remove, and attach a video URL. Photos render on the storefront product page.
export function ProductMedia({ productId, canManage }: { productId: string; canManage: boolean }) {
  const [items, setItems] = useState<MediaItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [videoUrl, setVideoUrl] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setItems(await api(`/catalog/products/${productId}/media`));
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudieron cargar los medios");
    } finally {
      setLoading(false);
    }
  }, [productId]);

  useEffect(() => {
    load();
  }, [load]);

  async function upload(files: FileList | File[] | null) {
    const list = files ? Array.from(files) : [];
    if (list.length === 0) return;
    setBusy(true);
    setError("");
    try {
      for (const file of list) {
        const fd = new FormData();
        fd.append("file", file);
        await apiUpload(`/catalog/products/${productId}/media`, fd);
      }
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo subir la imagen");
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try {
      await fn();
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ocurrió un error");
    } finally {
      setBusy(false);
    }
  }

  const remove = (id: string) => act(() => api(`/catalog/products/${productId}/media/${id}`, { method: "DELETE" }));
  const makePrimary = (id: string) => act(() => api(`/catalog/products/${productId}/media/${id}/primary`, { method: "POST" }));
  const addVideo = () => {
    const url = videoUrl.trim();
    if (!url) return;
    setVideoUrl("");
    return act(() => api(`/catalog/products/${productId}/media/video`, { method: "POST", body: JSON.stringify({ external_url: url }) }));
  };

  return (
    <div className="space-y-4">
      {canManage && (
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            upload(e.dataTransfer.files);
          }}
          className={`flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-6 py-8 text-center transition-colors ${dragOver ? "border-brand bg-brand/5" : "border-line"}`}
        >
          <p className="text-sm text-text">Arrastra fotos aquí o</p>
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            disabled={busy}
            className="rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          >
            {busy ? "Subiendo…" : "Elegir fotos"}
          </button>
          <p className="text-xs text-muted">JPG, PNG, WEBP o AVIF · hasta 25 MB c/u · la primera foto es la portada</p>
          <input
            ref={fileRef}
            type="file"
            accept="image/jpeg,image/png,image/webp,image/avif,image/gif"
            multiple
            className="hidden"
            onChange={(e) => upload(e.target.files)}
          />
        </div>
      )}

      {error && <p className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-300">{error}</p>}

      {loading ? (
        <p className="text-sm text-muted">Cargando medios…</p>
      ) : items.length === 0 ? (
        <p className="rounded-lg border border-line p-6 text-sm text-muted">Aún no hay fotos ni videos para este producto.</p>
      ) : (
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {items.map((item) => (
            <li key={item.id} className="group relative overflow-hidden rounded-lg border border-line bg-bg">
              <div className="flex aspect-square items-center justify-center bg-white">
                {item.media_type === "image" ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={item.url} alt={item.alt_text ?? ""} className="h-full w-full object-contain p-2" />
                ) : (
                  <div className="flex flex-col items-center gap-1 text-[#0f1111]">
                    <span className="text-3xl">▶</span>
                    <span className="max-w-[90%] truncate px-2 text-xs">{item.url}</span>
                  </div>
                )}
              </div>
              {item.is_primary && (
                <span className="absolute left-2 top-2 rounded-full bg-brand px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white">Portada</span>
              )}
              {canManage && (
                <div className="flex items-center justify-between gap-1 p-1.5">
                  {item.media_type === "image" && !item.is_primary ? (
                    <button type="button" onClick={() => makePrimary(item.id)} disabled={busy} className="rounded px-2 py-1 text-xs text-brand hover:underline disabled:opacity-50">
                      Hacer portada
                    </button>
                  ) : (
                    <span />
                  )}
                  <button type="button" onClick={() => remove(item.id)} disabled={busy} className="rounded px-2 py-1 text-xs text-red-400 hover:underline disabled:opacity-50">
                    Eliminar
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}

      {canManage && (
        <div className="flex flex-wrap items-end gap-2 border-t border-line pt-4">
          <label className="grid flex-1 gap-1.5 text-sm">
            <span className="text-muted">Agregar video (URL de YouTube, Vimeo o MP4)</span>
            <input value={videoUrl} onChange={(e) => setVideoUrl(e.target.value)} placeholder="https://…" className={inputCls} />
          </label>
          <button type="button" onClick={addVideo} disabled={busy || !videoUrl.trim()} className="rounded-lg border border-line px-4 py-2 text-sm font-semibold text-text disabled:opacity-50">
            Agregar video
          </button>
        </div>
      )}
    </div>
  );
}
