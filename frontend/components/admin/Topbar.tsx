"use client";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { api } from "@/lib/api";
import { setIdentityCache } from "@/lib/identityCache";
import type { Store } from "@/lib/platform";

export function Topbar({
  tenantName,
  stores,
  activeStoreId,
  onStoreChange,
  userName,
  onToggleSidebar,
}: {
  tenantName?: string;
  stores: Store[];
  activeStoreId: string;
  onStoreChange: (storeId: string) => void;
  userName?: string;
  onToggleSidebar: () => void;
}) {
  const router = useRouter();
  const [menuOpen, setMenuOpen] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);

  async function logout() {
    setLoggingOut(true);
    try {
      await api("/auth/logout", { method: "POST" });
    } finally {
      sessionStorage.removeItem("access_token");
      sessionStorage.removeItem("challenge_token");
      sessionStorage.removeItem("active_store_id");
      setIdentityCache(null);
      router.replace("/");
    }
  }

  function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = (new FormData(event.currentTarget).get("q") as string || "").trim();
    if (value) router.push(`/catalog/products?search=${encodeURIComponent(value)}`);
  }

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-line bg-panel/95 px-4 backdrop-blur">
      <button
        type="button"
        onClick={onToggleSidebar}
        aria-label="Mostrar navegación"
        className="w-auto rounded-lg p-2 text-muted hover:bg-white/5 hover:text-text md:hidden"
      >
        ☰
      </button>

      <div className="flex min-w-0 items-center gap-2 text-xs text-muted">
        <span className="hidden truncate rounded-md bg-white/5 px-2 py-1 lg:inline" title="Tenant activo">
          {tenantName ?? "…"}
        </span>
        <select
          aria-label="Tienda activa"
          title="Tienda activa"
          value={activeStoreId}
          onChange={(event) => onStoreChange(event.target.value)}
          className="max-w-52 rounded-md border border-line bg-bg px-2 py-1 text-xs text-text"
        >
          <option value="">Todas las tiendas</option>
          {stores.filter((store) => store.status !== "archived").map((store) => (
            <option key={store.id} value={store.id}>{store.name}</option>
          ))}
        </select>
      </div>

      <form onSubmit={search} className="ml-auto min-w-0 flex-1 lg:flex-none">
        <input
          name="q"
          type="search"
          placeholder="Buscar producto o SKU…"
          aria-label="Buscar producto o SKU"
          className="w-full max-w-[10rem] rounded-lg border border-line bg-bg px-3 py-1.5 text-sm text-text placeholder:text-muted/60 focus:border-brand focus:outline-none sm:max-w-xs"
        />
      </form>

      <div className="relative shrink-0">
        <button
          type="button"
          onClick={() => setMenuOpen((value) => !value)}
          aria-haspopup="menu"
          aria-expanded={menuOpen}
          className="flex w-auto items-center gap-2 rounded-lg px-2 py-1.5 text-sm text-text hover:bg-white/5"
        >
          <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-brand/20 text-xs font-semibold text-brand">
            {(userName ?? "U").slice(0, 1).toUpperCase()}
          </span>
          <span className="hidden max-w-[8rem] truncate lg:inline">{userName ?? "Cuenta"}</span>
        </button>
        {menuOpen && (
          <div
            role="menu"
            className="absolute right-0 mt-2 w-48 overflow-hidden rounded-lg border border-line bg-panel shadow-xl"
          >
            <a href="/profile" role="menuitem" className="block px-4 py-2 text-sm text-text hover:bg-white/5">
              Perfil
            </a>
            <a href="/security" role="menuitem" className="block px-4 py-2 text-sm text-text hover:bg-white/5">
              Seguridad
            </a>
            <a href="/sessions" role="menuitem" className="block px-4 py-2 text-sm text-text hover:bg-white/5">
              Sesiones
            </a>
            <button
              type="button"
              role="menuitem"
              disabled={loggingOut}
              onClick={logout}
              className="block w-full px-4 py-2 text-left text-sm text-red-300 hover:bg-white/5 disabled:opacity-60"
            >
              {loggingOut ? "Cerrando…" : "Cerrar sesión"}
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
