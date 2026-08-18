"use client";
import { useEffect, useState } from "react";
import { AdminShell } from "@/components/admin/AdminShell";
import { DataTable, type Column } from "@/components/admin/DataTable";
import { EmptyState } from "@/components/admin/EmptyState";
import { FilterBar } from "@/components/admin/FilterBar";
import { SearchInput } from "@/components/admin/SearchInput";
import { type PriceHistoryEntry, pricingPage, technicalError } from "@/lib/pricing";

export default function Page() {
  const [items, setItems] = useState<PriceHistoryEntry[]>([]);
  const [variantId, setVariantId] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  async function load(filterVariantId?: string) {
    setLoading(true);
    try {
      const query = filterVariantId ? `?variant_id=${filterVariantId}` : "";
      const page = await pricingPage<PriceHistoryEntry>(`/price-history${query}`);
      setItems(page.items);
      setError("");
    } catch (e) {
      setError(technicalError(e));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    load();
  }, []);

  const columns: Column<PriceHistoryEntry>[] = [
    { key: "field_name", header: "Campo", render: (h) => <span className="font-medium text-text">{h.field_name}</span> },
    { key: "previous_amount", header: "Anterior", align: "right", render: (h) => h.previous_amount ?? "—" },
    { key: "new_amount", header: "Nuevo", align: "right", render: (h) => <span className="text-text">{h.new_amount ?? "—"}</span> },
    { key: "currency_code", header: "Moneda", render: (h) => <span className="text-muted">{h.currency_code}</span>, hideOnMobile: true },
    { key: "changed_at", header: "Fecha", render: (h) => <span className="text-muted">{new Date(h.changed_at).toLocaleString("es-EC")}</span>, hideOnMobile: true },
  ];

  return (
    <AdminShell title="Historial de precios" description="Cada cambio de precio base, comparación, MSRP o costo queda registrado aquí, con el valor anterior y el nuevo.">
      <FilterBar>
        <SearchInput value={variantId} onChange={setVariantId} onSubmit={() => load(variantId || undefined)} placeholder="Filtrar por ID de producto (variant)" className="w-full sm:w-80" />
      </FilterBar>
      <DataTable
        columns={columns}
        rows={items}
        keyField={(h) => h.id}
        loading={loading}
        empty={<EmptyState title="Sin historial todavía" description="Los cambios de precio aparecerán aquí en cuanto se edite una lista o una regla." />}
      />
      {error && <p className="mt-3 text-sm text-red-300" role="alert">{error}</p>}
    </AdminShell>
  );
}
