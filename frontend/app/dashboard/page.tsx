"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { AdminShell } from "@/components/admin/AdminShell";
import { StatCard } from "@/components/admin/StatCard";
import { EmptyState } from "@/components/admin/EmptyState";
import { api } from "@/lib/api";
import { listStores, Store } from "@/lib/platform";
import { Attribute, catalogPage, Product, technicalError } from "@/lib/catalog";

type Operation = { id: string; operation_type: string; status: string; progress: number; message?: string };
type Counted<T> = { items: T[]; hasMore: boolean };

export default function Page() {
  const [stores, setStores] = useState<Store[]>([]);
  const [products, setProducts] = useState<Counted<Product>>({ items: [], hasMore: false });
  const [attributes, setAttributes] = useState<Counted<Attribute>>({ items: [], hasMore: false });
  const [operations, setOperations] = useState<Operation[]>([]);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const [context, storeRows, productPage, attributePage, operationRows] = await Promise.all([
          api("/me/context"),
          listStores().catch(() => []),
          catalogPage<Product>("/products?limit=100").catch(() => ({ items: [], has_more: false })),
          catalogPage<Attribute>("/attributes?limit=100").catch(() => ({ items: [], has_more: false })),
          api("/operations").catch(() => []),
        ]);
        setPermissions(context.permissions);
        setStores(storeRows);
        setProducts({ items: productPage.items, hasMore: productPage.has_more });
        setAttributes({ items: attributePage.items, hasMore: attributePage.has_more });
        setOperations(operationRows.slice(0, 5));
        setError("");
      } catch (e) {
        setError(technicalError(e));
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const activeStores = stores.filter((store) => store.status === "active");
  const count = (bucket: Counted<unknown>) => `${bucket.items.length}${bucket.hasMore ? "+" : ""}`;

  return (
    <AdminShell
      title="Panel general"
      description="Resumen de la empresa activa: catálogo, tiendas y actividad reciente."
    >
      {loading ? (
        <p>Cargando…</p>
      ) : (
        <>
          {stores.length > 0 && activeStores.length === 0 && (
            <div className="mb-6 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
              Ninguna Store está activa todavía. <Link href="/platform/stores" className="underline">Actívala</Link> para
              poder publicar Products.
            </div>
          )}

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            <StatCard label="Stores activas" value={activeStores.length} hint={`${stores.length} en total`} />
            <StatCard label="Products" value={count(products)} />
            <StatCard label="Attributes" value={count(attributes)} />
            <StatCard label="Jobs recientes" value={operations.length} />
          </div>

          <h2>Jobs recientes</h2>
          {operations.length === 0 ? (
            <EmptyState title="Sin jobs recientes" description="Las operaciones durables (por ejemplo, generación de combinaciones) aparecerán aquí." />
          ) : (
            operations.map((item) => (
              <div className="row" key={item.id}>
                <span>
                  <strong>{item.operation_type}</strong>
                  <br />
                  {item.message ?? item.id}
                </span>
                <span>
                  {item.status} · {item.progress}%
                </span>
              </div>
            ))
          )}

          <h2>Eventos recientes</h2>
          <EmptyState
            title="Sin panel de eventos todavía"
            description="El outbox de eventos es interno; no existe un endpoint de solo lectura expuesto al admin en este incremento."
          />

          <h2>Accesos rápidos</h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {permissions.includes("catalog.product.create") && (
              <Link className="button compact" href="/catalog/products/new">
                Crear Product
              </Link>
            )}
            {permissions.includes("store.create") && (
              <Link className="button compact" href="/platform/stores/new">
                Crear Store
              </Link>
            )}
            <Link className="button compact" href="/catalog/attributes">
              Ver Attributes
            </Link>
            <Link className="button compact" href="/catalog/options">
              Ver Options
            </Link>
          </div>
        </>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </AdminShell>
  );
}
