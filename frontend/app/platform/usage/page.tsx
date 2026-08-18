"use client";
import { useEffect, useState } from "react";
import { AdminShell } from "@/components/admin/AdminShell";
import { DataTable, type Column } from "@/components/admin/DataTable";
import { EmptyState } from "@/components/admin/EmptyState";
import { ApiError, api } from "@/lib/api";

type Entitlement = { key: string; value: number; source: string };

export default function Page() {
  const [usage, setUsage] = useState<Record<string, number>>({});
  const [limits, setLimits] = useState<Entitlement[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([api("/platform/usage"), api("/platform/entitlements")])
      .then(([u, e]) => {
        setUsage(u);
        setLimits(e);
      })
      .catch((e: ApiError) => setError(`${e.message}${e.correlationId ? ` · ID ${e.correlationId}` : ""}`))
      .finally(() => setLoading(false));
  }, []);

  const current = (key: string) => usage[key.split(".")[0].replace("max_per_store", "")] ?? 0;
  const columns: Column<Entitlement>[] = [
    { key: "key", header: "Cuota", render: (l) => <span className="font-medium text-text">{l.key}</span> },
    { key: "usage", header: "Uso", align: "right", render: (l) => current(l.key) },
    { key: "value", header: "Límite", align: "right", render: (l) => l.value },
    { key: "source", header: "Fuente", render: (l) => <span className="text-muted">{l.source}</span>, hideOnMobile: true },
  ];

  return (
    <AdminShell title="Uso y cuotas" description="Consumo de recursos frente a los límites de tu plan.">
      <DataTable
        columns={columns}
        rows={limits}
        keyField={(l) => l.key}
        loading={loading}
        empty={<EmptyState title="Sin cuotas" description="No hay límites configurados." />}
      />
      {error && <p className="mt-3 text-sm text-red-300" role="alert">{error}</p>}
    </AdminShell>
  );
}
