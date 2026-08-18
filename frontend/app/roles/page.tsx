"use client";
import { useEffect, useState } from "react";
import { AdminShell } from "@/components/admin/AdminShell";
import { DataTable, type Column } from "@/components/admin/DataTable";
import { EmptyState } from "@/components/admin/EmptyState";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { api } from "@/lib/api";

type Role = { id: string; name: string; is_system: boolean; permissions: string[] };

export default function Page() {
  const [roles, setRoles] = useState<Role[]>([]);
  const [expanded, setExpanded] = useState<Role | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api("/roles")
      .then(setRoles)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const columns: Column<Role>[] = [
    { key: "name", header: "Rol", render: (r) => <span className="font-medium text-text">{r.name}</span> },
    { key: "type", header: "Tipo", render: (r) => <StatusBadge label={r.is_system ? "Sistema" : "Personalizado"} tone={r.is_system ? "info" : "neutral"} /> },
    { key: "permissions", header: "Permisos", align: "right", render: (r) => r.permissions.length },
  ];

  return (
    <AdminShell title="Roles y permisos" description="Los roles definen qué puede hacer cada usuario.">
      <DataTable
        columns={columns}
        rows={roles}
        keyField={(r) => r.id}
        loading={loading}
        onRowClick={(r) => setExpanded((cur) => (cur?.id === r.id ? null : r))}
        empty={<EmptyState title="Sin roles" description="Aún no hay roles configurados." />}
      />
      {expanded && (
        <div className="mt-4 rounded-xl border border-line bg-panel p-4">
          <div className="mb-2 flex items-center justify-between">
            <strong className="text-text">Permisos de {expanded.name}</strong>
            <button type="button" className="text-sm text-muted hover:text-text" onClick={() => setExpanded(null)}>Cerrar</button>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {expanded.permissions.length === 0 ? (
              <span className="text-sm text-muted">Sin permisos.</span>
            ) : (
              expanded.permissions.map((p) => (
                <span key={p} className="rounded-md bg-white/5 px-2 py-0.5 font-mono text-xs text-muted">
                  {p}
                </span>
              ))
            )}
          </div>
        </div>
      )}
      {error && <p className="mt-3 text-sm text-red-300" role="alert">{error}</p>}
    </AdminShell>
  );
}
