"use client";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { ACTIVE_STORE_CHANGED, activeStore, listStores, selectStore, type Store } from "@/lib/platform";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";
import { Breadcrumbs } from "./Breadcrumbs";
import { PageHeader } from "./PageHeader";
import { breadcrumbsForPath, type NavItem } from "./nav";

import { getIdentityCache, type Identity, setIdentityCache } from "@/lib/identityCache";

export function AdminShell({
  title,
  description,
  actions,
  breadcrumbs,
  children,
}: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  breadcrumbs?: NavItem[];
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [identity, setIdentity] = useState<Identity>(getIdentityCache() ?? { stores: [], activeStoreId: "" });

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const [context, tenants, user, stores] = await Promise.all([
          api("/me/context"),
          api("/me/tenants"),
          api("/me"),
          listStores().catch(() => []),
        ]);
        if (!active) return;
        const tenantName = tenants.find((tenant: { id: string }) => tenant.id === context.tenant_id)?.name;
        const storedId = activeStore() ?? "";
        const activeStoreId = stores.some((store) => store.id === storedId && store.status !== "archived") ? storedId : "";
        if (storedId && !activeStoreId) selectStore(null);
        const next = { tenantName, userName: user.full_name, stores, activeStoreId };
        setIdentityCache(next);
        setIdentity(next);
      } catch {
        setIdentityCache(null);
        router.replace("/");
      }
    })();
    return () => {
      active = false;
    };
  }, [router]);

  useEffect(() => {
    const handleStoreChange = (event: Event) => {
      const storeId = (event as CustomEvent<{ storeId: string | null }>).detail.storeId ?? "";
      setIdentity((current) => {
        const next = { ...current, activeStoreId: storeId };
        setIdentityCache(next);
        return next;
      });
    };
    window.addEventListener(ACTIVE_STORE_CHANGED, handleStoreChange);
    return () => window.removeEventListener(ACTIVE_STORE_CHANGED, handleStoreChange);
  }, []);

  function changeStore(storeId: string) {
    // No full reload: selectStore dispatches ACTIVE_STORE_CHANGED, which the
    // topbar selector and any store-scoped page (PlatformCollection) listen to.
    selectStore(storeId || null);
  }

  return (
    <div className="min-h-screen bg-bg text-text">
      {sidebarOpen && (
        <button
          type="button"
          aria-label="Cerrar navegación"
          onClick={() => setSidebarOpen(false)}
          className="fixed inset-0 z-30 bg-black/60 md:hidden"
        />
      )}
      <Sidebar open={sidebarOpen} onNavigate={() => setSidebarOpen(false)} />
      <div className="flex min-h-screen flex-col md:pl-60">
        <Topbar
          tenantName={identity.tenantName}
          stores={identity.stores}
          activeStoreId={identity.activeStoreId}
          onStoreChange={changeStore}
          userName={identity.userName}
          onToggleSidebar={() => setSidebarOpen((value) => !value)}
        />
        <main className="flex-1 px-4 py-6 sm:px-6 lg:px-8">
          <Breadcrumbs items={breadcrumbs ?? breadcrumbsForPath(pathname, title)} />
          <PageHeader title={title} description={description} actions={actions} />
          {children}
        </main>
      </div>
    </div>
  );
}
