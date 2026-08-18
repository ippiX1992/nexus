"use client";
import { useEffect, useState } from "react";
import { AdminShell } from "@/components/admin/AdminShell";
import { DataTable, type Column } from "@/components/admin/DataTable";
import { EmptyState } from "@/components/admin/EmptyState";
import { FilterBar, Select } from "@/components/admin/FilterBar";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { variantLabels } from "@/lib/catalog";
import { type Location, type Reservation, inventoryPage } from "@/lib/inventory";

export default function Page() {
  const [rows, setRows] = useState<Reservation[]>([]);
  const [locations, setLocations] = useState<Location[]>([]);
  const [names, setNames] = useState<Map<string, string>>(new Map());
  const [status, setStatus] = useState("held");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load(current: string) {
    setLoading(true);
    try {
      const query = current ? `?status=${current}` : "";
      const [page, locationPage, labels] = await Promise.all([
        inventoryPage<Reservation>(`/reservations${query}`),
        inventoryPage<Location>("/locations"),
        variantLabels().catch(() => new Map<string, string>()),
      ]);
      setRows(page.items);
      setLocations(locationPage.items);
      setNames(labels);
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    load(status);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  const locationName = (id: string) => locations.find((l) => l.id === id)?.name ?? "—";
  const variantName = (id: string) => names.get(id) ?? "—";

  const columns: Column<Reservation>[] = [
    { key: "variant", header: "Producto", render: (r) => <span className="font-medium text-text">{variantName(r.variant_id)}</span> },
    { key: "location", header: "Ubicación", render: (r) => locationName(r.location_id), hideOnMobile: true },
    { key: "quantity", header: "Cantidad", align: "right", render: (r) => r.quantity },
    { key: "status", header: "Estado", render: (r) => <StatusBadge status={r.status} /> },
    {
      key: "expires_at",
      header: "Vence",
      hideOnMobile: true,
      render: (r) => (r.expires_at ? new Date(r.expires_at).toLocaleString("es-EC") : "Sin vencimiento"),
    },
  ];

  return (
    <AdminShell title="Reservas" description="Retenciones de stock creadas por pedidos y el carrito. Las gestiona el motor de inventario.">
      <FilterBar>
        <Select value={status} onChange={setStatus} label="Estado">
          <option value="held">Reservadas (activas)</option>
          <option value="committed">Consumidas</option>
          <option value="released">Liberadas</option>
          <option value="expired">Expiradas</option>
          <option value="">Todas</option>
        </Select>
      </FilterBar>
      <DataTable
        columns={columns}
        rows={rows}
        keyField={(r) => r.id}
        loading={loading}
        empty={<EmptyState title="Sin reservas" description="Cuando un pedido reserve stock, la retención aparecerá aquí." />}
      />
      {error && (
        <p className="mt-3 text-sm text-red-300" role="alert">
          {error}
        </p>
      )}
    </AdminShell>
  );
}
