"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { NAV_GROUPS } from "./nav";

export function Sidebar({ open, onNavigate }: { open: boolean; onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <aside
      className={`fixed inset-y-0 left-0 z-40 w-60 shrink-0 border-r border-line bg-panel/95 backdrop-blur transition-transform md:translate-x-0 ${open ? "translate-x-0" : "-translate-x-full"}`}
      aria-label="Navegación principal"
    >
      <div className="flex h-14 items-center gap-2 border-b border-line px-4">
        <span className="grid h-7 w-7 place-items-center rounded-lg bg-brand text-sm font-bold text-white">N</span>
        <span className="text-sm font-semibold tracking-wide text-text">Nexus</span>
      </div>
      <nav className="flex h-[calc(100%-3.5rem)] flex-col gap-5 overflow-y-auto px-3 py-4">
        <Link
          href="/dashboard"
          onClick={onNavigate}
          className={`rounded-lg px-3 py-2 text-sm font-medium ${pathname === "/dashboard" ? "bg-brand/15 text-white" : "text-muted hover:bg-white/5 hover:text-text"}`}
        >
          Inicio
        </Link>
        {NAV_GROUPS.map((group) => (
          <div key={group.label}>
            <p className="px-3 text-[11px] font-semibold uppercase tracking-wider text-muted/70">
              {group.label}
              {group.comingSoon && <span className="ml-1 normal-case text-muted/50">· próximamente</span>}
            </p>
            {group.items.length === 0 ? (
              <p className="px-3 py-1.5 text-sm text-muted/50">Sin módulos activos</p>
            ) : (
              <ul className="mt-1 space-y-0.5">
                {group.items.map((item) => {
                  const active = pathname.startsWith(item.href);
                  return (
                    <li key={item.href}>
                      <Link
                        href={item.href}
                        onClick={onNavigate}
                        aria-current={active ? "page" : undefined}
                        className={`block rounded-lg px-3 py-1.5 text-sm ${active ? "bg-brand/15 font-medium text-white" : "text-muted hover:bg-white/5 hover:text-text"}`}
                      >
                        {item.label}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        ))}
      </nav>
    </aside>
  );
}
