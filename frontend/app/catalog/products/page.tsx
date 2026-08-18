"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AdminShell } from "@/components/admin/AdminShell";
import { LinkButton } from "@/components/admin/Button";
import { DataTable, type Column } from "@/components/admin/DataTable";
import { EmptyState } from "@/components/admin/EmptyState";
import { FilterBar } from "@/components/admin/FilterBar";
import { LoadMore } from "@/components/admin/Pagination";
import { SearchInput } from "@/components/admin/SearchInput";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { catalogContext, catalogPage, type Product, technicalError } from "@/lib/catalog";

export default function Page() {
  const router = useRouter();
  const [items, setItems] = useState<Product[]>([]);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [cursor, setCursor] = useState<string | undefined>();
  const [search, setSearch] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const current = new URLSearchParams(window.location.search).get("search") ?? "";
    setSearch(current);
    load(current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function load(term: string, next?: string, append = false) {
    setLoading(true);
    try {
      const query = `?limit=25${next ? `&cursor=${encodeURIComponent(next)}` : ""}${term ? `&search=${encodeURIComponent(term)}` : ""}`;
      const [page, ctx] = await Promise.all([catalogPage<Product>(`/products${query}`), catalogContext()]);
      setItems((previous) => (append ? [...previous, ...page.items] : page.items));
      setCursor(page.next_cursor);
      setPermissions(ctx.permissions);
      setError("");
    } catch (e) {
      setError(technicalError(e));
    } finally {
      setLoading(false);
    }
  }

  const columns: Column<Product>[] = [
    { key: "name", header: "Producto", render: (p) => <span className="font-medium text-text">{p.name ?? p.code ?? "—"}</span> },
    { key: "default_sku", header: "SKU", render: (p) => <span className="text-muted">{p.default_sku ?? "Sin SKU"}</span>, hideOnMobile: true },
    { key: "category", header: "Categoría", render: (p) => <span className="text-muted">{p.category ?? "—"}</span>, hideOnMobile: true },
    { key: "status", header: "Estado", render: (p) => <StatusBadge status={p.status} /> },
    { key: "stock", header: "Stock", align: "right", render: (p) => (p.stock == null ? "—" : <span className={p.stock <= 0 ? "text-red-300" : p.stock <= 5 ? "text-amber-300" : "text-text"}>{p.stock}</span>) },
  ];

  return (
    <AdminShell
      title="Productos"
      description="Catálogo de productos de la tienda activa."
      actions={
        permissions.includes("catalog.product.create") && (
          <LinkButton href="/catalog/products/new" variant="primary">
            Crear producto
          </LinkButton>
        )
      }
    >
      <FilterBar>
        <SearchInput value={search} onChange={setSearch} onSubmit={() => load(search)} placeholder="Buscar producto o SKU" className="w-full sm:w-80" />
      </FilterBar>
      <DataTable
        columns={columns}
        rows={items}
        keyField={(p) => p.id}
        loading={loading}
        stickyHeader
        onRowClick={(p) => router.push(`/catalog/products/${p.id}`)}
        empty={
          <EmptyState
            title={search ? "Sin resultados" : "No hay productos"}
            description={search ? `Nada coincide con "${search}".` : "Crea el primero para iniciar el catálogo."}
            action={permissions.includes("catalog.product.create") ? <LinkButton href="/catalog/products/new" variant="primary">Crear producto</LinkButton> : undefined}
          />
        }
      />
      <LoadMore onMore={() => load(search, cursor, true)} loading={loading} hasMore={!!cursor} shown={items.length} />
      {error && (
        <p className="mt-3 text-sm text-red-300" role="alert">
          {error}
        </p>
      )}
    </AdminShell>
  );
}
