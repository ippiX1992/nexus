"use client";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { activeStore, listStores } from "@/lib/platform";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";
import { Breadcrumbs } from "./Breadcrumbs";
import { PageHeader } from "./PageHeader";
import { breadcrumbsForPath, type NavItem } from "./nav";

type Identity = { tenantName?: string; storeName?: string | null; userName?: string };

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
  const [identity, setIdentity] = useState<Identity>({});

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
        const storeId = activeStore();
        const storeName = storeId ? stores.find((store) => store.id === storeId)?.name ?? null : null;
        setIdentity({ tenantName, storeName, userName: user.full_name });
      } catch {
        router.replace("/");
      }
    })();
    return () => {
      active = false;
    };
  }, [router]);

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
          storeName={identity.storeName}
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
