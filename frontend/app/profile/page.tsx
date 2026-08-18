"use client";
import { useEffect, useState } from "react";
import { AdminShell } from "@/components/admin/AdminShell";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { api } from "@/lib/api";

type User = { email: string; full_name: string; two_factor_enabled: boolean };

export default function Page() {
  const [user, setUser] = useState<User>();
  const [error, setError] = useState("");

  useEffect(() => {
    api("/me").then(setUser).catch((e) => setError(e.message));
  }, []);

  return (
    <AdminShell title="Perfil" description="Tu cuenta en Nexus.">
      {user && (
        <div className="max-w-lg rounded-xl border border-line bg-panel p-5">
          <div className="flex items-center gap-4">
            <span className="grid h-12 w-12 place-items-center rounded-full bg-brand/20 text-lg font-semibold text-brand">
              {user.full_name.slice(0, 1).toUpperCase()}
            </span>
            <div>
              <p className="text-base font-semibold text-text">{user.full_name}</p>
              <p className="text-sm text-muted">{user.email}</p>
            </div>
          </div>
          <div className="mt-4 flex items-center justify-between border-t border-line pt-4 text-sm">
            <span className="text-muted">Verificación en dos pasos</span>
            <StatusBadge label={user.two_factor_enabled ? "Activa" : "Inactiva"} tone={user.two_factor_enabled ? "success" : "neutral"} />
          </div>
        </div>
      )}
      {error && <p className="mt-3 text-sm text-red-300" role="alert">{error}</p>}
    </AdminShell>
  );
}
