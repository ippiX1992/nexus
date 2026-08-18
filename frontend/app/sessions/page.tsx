"use client";
import { useEffect, useState } from "react";
import { AdminShell } from "@/components/admin/AdminShell";
import { Button } from "@/components/admin/Button";
import { DataTable, type Column } from "@/components/admin/DataTable";
import { EmptyState } from "@/components/admin/EmptyState";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { api } from "@/lib/api";

type Session = { id: string; user_agent: string; ip_address: string; current: boolean };

export default function Page() {
  const [items, setItems] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = () =>
    api("/auth/sessions")
      .then(setItems)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  useEffect(() => {
    load();
  }, []);
  async function close(id: string) {
    await api(`/auth/sessions/${id}`, { method: "DELETE" });
    load();
  }

  const columns: Column<Session>[] = [
    {
      key: "device",
      header: "Dispositivo",
      render: (s) => (
        <span className="flex items-center gap-2">
          <span className="font-medium text-text">{s.user_agent || "Dispositivo desconocido"}</span>
          {s.current && <StatusBadge label="Esta sesión" tone="brand" />}
        </span>
      ),
    },
    { key: "ip_address", header: "IP", render: (s) => <span className="text-muted">{s.ip_address || "—"}</span>, hideOnMobile: true },
  ];

  return (
    <AdminShell title="Sesiones activas" description="Dispositivos con acceso a tu cuenta. Cierra los que no reconozcas.">
      <DataTable
        columns={columns}
        rows={items}
        keyField={(s) => s.id}
        loading={loading}
        empty={<EmptyState title="Sin sesiones" description="No hay sesiones activas." />}
        rowActions={(s) => (
          <Button size="sm" variant="danger" onClick={() => close(s.id)}>
            Cerrar
          </Button>
        )}
      />
      {error && <p className="mt-3 text-sm text-red-300" role="alert">{error}</p>}
    </AdminShell>
  );
}
