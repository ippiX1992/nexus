"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { NAV_GROUPS, type NavGroup } from "./nav";

// Minimal stroke icon set (no external deps; CSP-safe). 24×24, currentColor.
const PATHS: Record<string, string> = {
  home: "M3 10.5 12 3l9 7.5M5 9.5V20h5v-5h4v5h5V9.5",
  cart: "M3 4h2l2.4 12.2a1 1 0 0 0 1 .8h8.7a1 1 0 0 0 1-.8L21 8H6M9 21h.01M17 21h.01",
  tag: "M3 12V4h8l9 9-8 8-9-9Zm4-4h.01",
  box: "M21 8 12 3 3 8m18 0-9 5m9-5v8l-9 5m0-8L3 8m9 5v8M3 8v8l9 5",
  dollar: "M12 3v18M8.5 8a3 3 0 0 1 3-3h1.5a2.5 2.5 0 0 1 0 5h-2a2.5 2.5 0 0 0 0 5H14a3 3 0 0 0 3-3",
  store: "M4 9V6l2-3h12l2 3v3M4 9h16M4 9v11h16V9M4 9a2 2 0 0 0 4 0 2 2 0 0 0 4 0 2 2 0 0 0 4 0 2 2 0 0 0 4 0M9 20v-5h4v5",
  users: "M16 20v-1a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v1M9.5 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Zm11 9v-1a4 4 0 0 0-3-3.9M16 4.1a4 4 0 0 1 0 7.8",
  sliders: "M4 6h10M18 6h2M4 12h2M10 12h10M4 18h8M16 18h4M14 4v4M6 10v4M12 16v4",
};

function Icon({ name, className = "" }: { name: string; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={`h-[1.05rem] w-[1.05rem] shrink-0 ${className}`} aria-hidden>
      <path d={PATHS[name] ?? PATHS.box} stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

const itemCls = (active: boolean) =>
  `flex items-center rounded-lg px-3 py-1.5 text-sm transition ${
    active ? "bg-brand/15 font-medium text-white" : "text-muted hover:bg-white/5 hover:text-text"
  }`;

function Group({ group, pathname, onNavigate }: { group: NavGroup; pathname: string; onNavigate?: () => void }) {
  const hasActive = group.items.some((i) => pathname.startsWith(i.href));
  const [open, setOpen] = useState(!group.collapsible || hasActive);
  // Keep an advanced group open if you navigate onto one of its pages.
  useEffect(() => {
    if (hasActive) setOpen(true);
  }, [hasActive]);

  const header = (
    <span className="flex items-center gap-2.5 px-3 text-[11px] font-semibold uppercase tracking-wider text-muted/70">
      <Icon name={group.icon} className="text-muted/60" />
      {group.label}
    </span>
  );

  return (
    <div>
      {group.collapsible ? (
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          className="flex w-full items-center justify-between rounded-lg py-1 hover:bg-white/5"
        >
          {header}
          <svg viewBox="0 0 24 24" fill="none" className={`mr-2 h-4 w-4 text-muted/60 transition-transform ${open ? "rotate-180" : ""}`} aria-hidden>
            <path d="m6 9 6 6 6-6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      ) : (
        <div className="py-1">{header}</div>
      )}
      {open && (
        <ul className="mt-1 space-y-0.5">
          {group.items.map((item) => {
            const active = pathname.startsWith(item.href);
            return (
              <li key={item.href}>
                <Link href={item.href} onClick={onNavigate} aria-current={active ? "page" : undefined} className={`${itemCls(active)} pl-[2.4rem]`}>
                  {item.label}
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

export function Sidebar({ open, onNavigate }: { open: boolean; onNavigate?: () => void }) {
  const pathname = usePathname();
  const homeActive = pathname === "/dashboard";
  return (
    <aside
      className={`fixed inset-y-0 left-0 z-40 w-60 shrink-0 border-r border-line bg-panel/95 backdrop-blur transition-transform md:translate-x-0 ${open ? "translate-x-0" : "-translate-x-full"}`}
      aria-label="Navegación principal"
    >
      <div className="flex h-14 items-center gap-2 border-b border-line px-4">
        <span className="grid h-7 w-7 place-items-center rounded-lg bg-brand text-sm font-bold text-white">N</span>
        <span className="text-sm font-semibold tracking-wide text-text">Nexus</span>
      </div>
      <nav className="flex h-[calc(100%-3.5rem)] flex-col gap-4 overflow-y-auto px-3 py-4">
        <Link href="/dashboard" onClick={onNavigate} aria-current={homeActive ? "page" : undefined} className={itemCls(homeActive)}>
          <Icon name="home" className="mr-2.5" />
          Inicio
        </Link>
        {NAV_GROUPS.map((group) => (
          <Group key={group.label} group={group} pathname={pathname} onNavigate={onNavigate} />
        ))}
      </nav>
    </aside>
  );
}
