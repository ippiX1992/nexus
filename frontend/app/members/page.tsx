"use client";
import { useEffect, useState } from "react";
import { AdminShell } from "@/components/admin/AdminShell";
import { DataTable, type Column } from "@/components/admin/DataTable";
import { EmptyState } from "@/components/admin/EmptyState";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { api } from "@/lib/api";

type Member = { membership_id: string; email: string; full_name: string; is_active: boolean; roles: string[] };

export default function Page() {
  const [members, setMembers] = useState<Member[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api("/members")
      .then(setMembers)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const columns: Column<Member>[] = [
    { key: "full_name", header: "Nombre", render: (m) => <span className="font-medium text-text">{m.full_name}</span> },
    { key: "email", header: "Correo", render: (m) => <span className="text-muted">{m.email}</span> },
    { key: "roles", header: "Roles", render: (m) => <span className="text-muted">{m.roles.join(", ") || "—"}</span>, hideOnMobile: true },
    { key: "status", header: "Estado", render: (m) => <StatusBadge label={m.is_active ? "Activo" : "Inactivo"} tone={m.is_active ? "success" : "neutral"} /> },
  ];

  return (
    <AdminShell title="Usuarios" description="Personas con acceso a la empresa activa.">
      <DataTable
        columns={columns}
        rows={members}
        keyField={(m) => m.membership_id}
        loading={loading}
        empty={<EmptyState title="Sin usuarios" description="Aún no hay miembros en esta empresa." />}
      />
      {error && <p className="mt-3 text-sm text-red-300" role="alert">{error}</p>}
    </AdminShell>
  );
}
