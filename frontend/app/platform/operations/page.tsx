"use client";
import { useEffect, useState } from "react";
import { AdminShell } from "@/components/admin/AdminShell";
import { DataTable, type Column } from "@/components/admin/DataTable";
import { EmptyState } from "@/components/admin/EmptyState";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { ApiError, api } from "@/lib/api";

type Operation = { id: string; operation_type: string; status: string; progress: number; message?: string; correlation_id: string };

export default function Page() {
  const [items, setItems] = useState<Operation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api("/operations")
      .then(setItems)
      .catch((e: ApiError) => setError(`${e.message}${e.correlationId ? ` · ID ${e.correlationId}` : ""}`))
      .finally(() => setLoading(false));
  }, []);

  const columns: Column<Operation>[] = [
    { key: "operation_type", header: "Operación", render: (o) => <span className="font-medium text-text">{o.operation_type}</span> },
    { key: "message", header: "Detalle", render: (o) => <span className="text-muted">{o.message ?? "—"}</span>, hideOnMobile: true },
    { key: "status", header: "Estado", render: (o) => <StatusBadge status={o.status} /> },
    { key: "progress", header: "Progreso", align: "right", render: (o) => `${o.progress}%` },
  ];

  return (
    <AdminShell title="Operaciones" description="Procesos largos del sistema (importaciones, recálculos) y su progreso.">
      <DataTable
        columns={columns}
        rows={items}
        keyField={(o) => o.id}
        loading={loading}
        empty={<EmptyState title="Sin operaciones" description="No hay procesos en curso." />}
      />
      {error && <p className="mt-3 text-sm text-red-300" role="alert">{error}</p>}
    </AdminShell>
  );
}
