"use client";
import { useEffect, useState } from "react";
import { AdminShell } from "@/components/admin/AdminShell";
import { Button, LinkButton } from "@/components/admin/Button";
import { DataTable, type Column } from "@/components/admin/DataTable";
import { EmptyState } from "@/components/admin/EmptyState";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { ApiError, api } from "@/lib/api";
import { listStores, selectStore, type Store } from "@/lib/platform";

export default function Page() {
  const [items, setItems] = useState<Store[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load() {
    try {
      setItems(await listStores());
    } catch (e) {
      const x = e as ApiError;
      setError(`${x.message}${x.correlationId ? ` · ID ${x.correlationId}` : ""}`);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    load();
  }, []);
  async function archive(id: string) {
    await api(`/stores/${id}/archive`, { method: "POST" });
    load();
  }

  const columns: Column<Store>[] = [
    { key: "name", header: "Nombre", render: (s) => <span className="font-medium text-text">{s.name}</span> },
    { key: "code", header: "Código", render: (s) => <span className="text-muted">{s.code}</span>, hideOnMobile: true },
    { key: "config", header: "Idioma / Moneda", render: (s) => <span className="text-muted">{s.default_locale} / {s.default_currency}</span>, hideOnMobile: true },
    { key: "status", header: "Estado", render: (s) => <StatusBadge status={s.status} /> },
  ];

  return (
    <AdminShell
      title="Tiendas"
      description="Las tiendas de tu empresa. Cada una tiene sus sitios, canales, mercados y precios."
      actions={<LinkButton href="/platform/stores/new" variant="primary">Nueva tienda</LinkButton>}
    >
      <DataTable
        columns={columns}
        rows={items}
        keyField={(s) => s.id}
        loading={loading}
        onRowClick={(s) => { window.location.href = `/platform/stores/${s.id}`; }}
        empty={<EmptyState title="Sin tiendas todavía" description="Crea la primera para configurar la plataforma." action={<LinkButton href="/platform/stores/new" variant="primary">Nueva tienda</LinkButton>} />}
        rowActions={(s) => (
          <>
            <Button size="sm" variant="secondary" onClick={() => { selectStore(s.id); window.location.href = "/platform/sites"; }}>Usar</Button>
            {s.status !== "archived" && <Button size="sm" variant="danger" onClick={() => archive(s.id)}>Archivar</Button>}
          </>
        )}
      />
      {error && <p className="mt-3 text-sm text-red-300" role="alert">{error}</p>}
    </AdminShell>
  );
}
