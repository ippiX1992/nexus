"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AdminShell } from "@/components/admin/AdminShell";
import { Button, LinkButton } from "@/components/admin/Button";
import { DataTable, type Column } from "@/components/admin/DataTable";
import { EmptyState } from "@/components/admin/EmptyState";
import { FilterBar } from "@/components/admin/FilterBar";
import { inputCls } from "@/components/admin/forms";
import { LoadMore } from "@/components/admin/Pagination";
import { SearchInput } from "@/components/admin/SearchInput";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { type Brand, catalogCommand, catalogContext, catalogPage, type Product, technicalError } from "@/lib/catalog";

export default function Page() {
  const router = useRouter();
  const [items, setItems] = useState<Product[]>([]);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [brands, setBrands] = useState<Brand[]>([]);
  const [cursor, setCursor] = useState<string | undefined>();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [brand, setBrand] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);

  const canManage = permissions.includes("catalog.product.update") || permissions.includes("catalog.product.archive");
  const toggleRow = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const toggleAll = (checked: boolean) => setSelected(checked ? new Set(items.map((p) => p.id)) : new Set());
  const clearSelection = () => setSelected(new Set());

  async function bulkAction(action: "archive" | "activate") {
    const targets = items.filter(
      (p) => selected.has(p.id) && (action === "archive" ? p.status !== "archived" : p.status !== "active"),
    );
    if (targets.length === 0) {
      clearSelection();
      return;
    }
    setBulkBusy(true);
    setError("");
    let ok = 0;
    for (const p of targets) {
      try {
        await catalogCommand(`/products/${p.id}/${action}`, p.version, "POST");
        ok++;
      } catch {
        /* skip items that can't transition */
      }
    }
    setBulkBusy(false);
    clearSelection();
    await load();
    if (ok < targets.length) setError(`${ok}/${targets.length} productos actualizados (algunos no se pudieron cambiar).`);
  }

  useEffect(() => {
    const current = new URLSearchParams(window.location.search).get("search") ?? "";
    setSearch(current);
    catalogPage<Brand>("/brands?status=active&limit=100")
      .then((page) => setBrands(page.items))
      .catch(() => setBrands([]));
    load({ search: current });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function load(opts: { search?: string; status?: string; brand?: string; cursor?: string; append?: boolean } = {}) {
    const term = opts.search ?? search;
    const st = opts.status ?? status;
    const br = opts.brand ?? brand;
    setLoading(true);
    try {
      const q = new URLSearchParams({ limit: "25" });
      if (opts.cursor) q.set("cursor", opts.cursor);
      if (term) q.set("search", term);
      if (st) q.set("status", st);
      if (br) q.set("brand", br);
      const [page, ctx] = await Promise.all([catalogPage<Product>(`/products?${q}`), catalogContext()]);
      setItems((previous) => (opts.append ? [...previous, ...page.items] : page.items));
      setCursor(page.next_cursor);
      setPermissions(ctx.permissions);
      setError("");
    } catch (e) {
      setError(technicalError(e));
    } finally {
      setLoading(false);
    }
  }

  const hasFilters = !!(search || status || brand);

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
        <SearchInput value={search} onChange={setSearch} onSubmit={() => load({ search })} placeholder="Buscar producto o SKU" className="w-full sm:w-72" />
        <select
          aria-label="Estado"
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            load({ status: e.target.value });
          }}
          className={inputCls}
        >
          <option value="">Todos los estados</option>
          <option value="active">Activo</option>
          <option value="draft">Borrador</option>
          <option value="archived">Archivado</option>
        </select>
        <select
          aria-label="Marca"
          value={brand}
          onChange={(e) => {
            setBrand(e.target.value);
            load({ brand: e.target.value });
          }}
          className={inputCls}
        >
          <option value="">Todas las marcas</option>
          {brands.map((b) => (
            <option key={b.id} value={b.id}>
              {b.name}
            </option>
          ))}
        </select>
      </FilterBar>
      {canManage && selected.size > 0 && (
        <div className="mb-3 flex flex-wrap items-center gap-3 rounded-xl border border-brand/40 bg-brand/10 px-4 py-2.5 text-sm">
          <span className="font-medium text-text">{selected.size} seleccionado{selected.size === 1 ? "" : "s"}</span>
          <Button size="sm" variant="primary" onClick={() => bulkAction("activate")} disabled={bulkBusy}>Activar</Button>
          <Button size="sm" variant="danger" onClick={() => bulkAction("archive")} disabled={bulkBusy}>Archivar</Button>
          <button type="button" onClick={clearSelection} className="w-fit text-xs text-muted hover:underline">Limpiar</button>
        </div>
      )}
      <DataTable
        columns={columns}
        rows={items}
        keyField={(p) => p.id}
        loading={loading}
        stickyHeader
        selectedIds={canManage ? selected : undefined}
        onToggleRow={toggleRow}
        onToggleAll={toggleAll}
        onRowClick={(p) => router.push(`/catalog/products/${p.id}`)}
        empty={
          <EmptyState
            title={hasFilters ? "Sin resultados" : "No hay productos"}
            description={hasFilters ? "Ningún producto coincide con los filtros." : "Crea el primero para iniciar el catálogo."}
            action={permissions.includes("catalog.product.create") ? <LinkButton href="/catalog/products/new" variant="primary">Crear producto</LinkButton> : undefined}
          />
        }
      />
      <LoadMore onMore={() => load({ cursor, append: true })} loading={loading} hasMore={!!cursor} shown={items.length} />
      {error && (
        <p className="mt-3 text-sm text-red-300" role="alert">
          {error}
        </p>
      )}
    </AdminShell>
  );
}
