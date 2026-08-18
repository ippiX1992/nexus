"use client";
import { useParams } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";
import { AdminShell } from "@/components/admin/AdminShell";
import { Button, LinkButton } from "@/components/admin/Button";
import { DataTable, type Column } from "@/components/admin/DataTable";
import { EmptyState } from "@/components/admin/EmptyState";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { api } from "@/lib/api";
import { activeStore, listStores, type Store } from "@/lib/platform";
import { type FulfillmentScope, type Location, type ScopeType, type Warehouse, inventoryCommand, inventoryCreate, inventoryGet, inventoryPage, technicalError } from "@/lib/inventory";

type ScopeOption = { id: string; name: string };
const inputCls = "rounded-lg border border-line bg-bg px-3 py-2 text-sm text-text focus:border-brand focus:outline-none";
const SCOPE_LABEL: Record<string, string> = { store: "Tienda", channel: "Canal", market: "Mercado" };

export default function Page() {
  const params = useParams();
  const warehouseId = String(params.id);
  const [warehouse, setWarehouse] = useState<Warehouse | null>(null);
  const [locations, setLocations] = useState<Location[]>([]);
  const [scopes, setScopes] = useState<FulfillmentScope[]>([]);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [stores, setStores] = useState<Store[]>([]);
  const [storeId, setStoreId] = useState(activeStore() ?? "");
  const [channels, setChannels] = useState<ScopeOption[]>([]);
  const [markets, setMarkets] = useState<ScopeOption[]>([]);
  const [showLoc, setShowLoc] = useState(false);
  const [showScope, setShowScope] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const canManageLocations = permissions.includes("inventory.location.create");
  const canManageScopes = permissions.includes("inventory.fulfillment_scope.manage");

  async function load() {
    setLoading(true);
    try {
      const [wh, locationPage, scopePage, ctx, storeList] = await Promise.all([
        inventoryGet<Warehouse>(`/warehouses/${warehouseId}`),
        inventoryPage<Location>(`/locations?warehouse_id=${warehouseId}`),
        inventoryPage<FulfillmentScope>(`/fulfillment-scopes?warehouse_id=${warehouseId}`),
        api("/me/context"),
        listStores(),
      ]);
      setWarehouse(wh);
      setLocations(locationPage.items);
      setScopes(scopePage.items);
      setPermissions(ctx.permissions);
      setStores(storeList);
      setError("");
    } catch (e) {
      setError(technicalError(e));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [warehouseId]);
  useEffect(() => {
    if (!storeId) {
      setChannels([]);
      setMarkets([]);
      return;
    }
    Promise.all([api(`/stores/${storeId}/channels`), api(`/stores/${storeId}/markets`)])
      .then(([c, m]) => {
        setChannels(c);
        setMarkets(m);
      })
      .catch((e) => setError(technicalError(e)));
  }, [storeId]);

  async function submitLocation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const el = event.currentTarget;
    const form = new FormData(el);
    try {
      await inventoryCreate(`/warehouses/${warehouseId}/locations`, { code: form.get("code"), name: form.get("name"), location_type: form.get("location_type") });
      el.reset();
      setShowLoc(false);
      await load();
    } catch (e) {
      setError(technicalError(e));
    }
  }
  async function submitScope(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const el = event.currentTarget;
    const form = new FormData(el);
    const scopeType = String(form.get("scope_type")) as ScopeType;
    const scopeId = String(form.get("scope_id"));
    try {
      await inventoryCreate("/fulfillment-scopes", {
        warehouse_id: warehouseId,
        scope_type: scopeType,
        store_id: scopeType === "store" ? scopeId : undefined,
        channel_id: scopeType === "channel" ? scopeId : undefined,
        market_id: scopeType === "market" ? scopeId : undefined,
        priority: Number(form.get("priority") || 0),
      });
      el.reset();
      setShowScope(false);
      await load();
    } catch (e) {
      setError(technicalError(e));
    }
  }
  async function archiveScope(item: FulfillmentScope) {
    try {
      await inventoryCommand(`/fulfillment-scopes/${item.id}/archive`, item.version);
      await load();
    } catch (e) {
      setError(technicalError(e));
    }
  }

  const breadcrumbs = [
    { href: "/dashboard", label: "Inicio" },
    { href: "/commerce/warehouses", label: "Bodegas" },
    { href: `/commerce/warehouses/${warehouseId}`, label: warehouse?.name ?? "Bodega" },
  ];

  if (loading && !warehouse) return <AdminShell title="Bodega" breadcrumbs={breadcrumbs}><p className="text-muted">Cargando…</p></AdminShell>;
  if (!warehouse) return <AdminShell title="Bodega" breadcrumbs={breadcrumbs}><p className="text-sm text-red-300" role="alert">{error || "No encontrada"}</p></AdminShell>;

  const locCols: Column<Location>[] = [
    { key: "name", header: "Nombre", render: (l) => <span className="font-medium text-text">{l.name}</span> },
    { key: "code", header: "Código", render: (l) => <span className="text-muted">{l.code}</span> },
    { key: "location_type", header: "Tipo", render: (l) => <span className="text-muted">{l.location_type}</span>, hideOnMobile: true },
    { key: "status", header: "Estado", render: (l) => <StatusBadge status={l.status} /> },
  ];
  const scopeCols: Column<FulfillmentScope>[] = [
    { key: "scope_type", header: "Ámbito", render: (s) => <span className="font-medium text-text">{SCOPE_LABEL[s.scope_type] ?? s.scope_type}</span> },
    { key: "priority", header: "Prioridad", align: "right", render: (s) => s.priority },
    { key: "status", header: "Estado", render: (s) => <StatusBadge status={s.status} /> },
  ];

  return (
    <AdminShell
      title={warehouse.name}
      description={`Código ${warehouse.code}`}
      breadcrumbs={breadcrumbs}
      actions={<LinkButton href="/commerce/warehouses" variant="ghost">← Bodegas</LinkButton>}
    >
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-text">Ubicaciones</h2>
        {canManageLocations && <Button variant="secondary" onClick={() => setShowLoc((v) => !v)}>{showLoc ? "Cerrar" : "Nueva ubicación"}</Button>}
      </div>
      {showLoc && canManageLocations && (
        <form onSubmit={submitLocation} className="mb-4 grid gap-3 rounded-xl border border-line bg-panel p-4 sm:grid-cols-2 lg:grid-cols-4">
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">Código</span><input name="code" required className={inputCls} /></label>
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">Nombre</span><input name="name" required className={inputCls} /></label>
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">Tipo</span><select name="location_type" defaultValue="storage" className={inputCls}>{["storage", "picking", "staging", "returns", "quarantine"].map((t) => <option key={t} value={t}>{t}</option>)}</select></label>
          <div className="flex items-end"><Button variant="primary" type="submit">Crear</Button></div>
        </form>
      )}
      <DataTable columns={locCols} rows={locations} keyField={(l) => l.id} empty={<EmptyState title="Sin ubicaciones" description="Agrega una ubicación para registrar stock en esta bodega." />} />

      <div className="mb-3 mt-8 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-text">Tiendas y canales que sirve</h2>
        {canManageScopes && <Button variant="secondary" onClick={() => setShowScope((v) => !v)}>{showScope ? "Cerrar" : "Asignar"}</Button>}
      </div>
      {showScope && canManageScopes && (
        <form onSubmit={submitScope} className="mb-4 grid gap-3 rounded-xl border border-line bg-panel p-4 sm:grid-cols-2 lg:grid-cols-4">
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">Tienda</span>
            <select name="store_id" value={storeId} onChange={(e) => setStoreId(e.target.value)} className={inputCls}>
              <option value="">Selecciona una tienda</option>
              {stores.filter((s) => s.status !== "archived").map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </label>
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">Tipo</span>
            <select name="scope_type" defaultValue="channel" className={inputCls}><option value="store">Tienda</option><option value="channel">Canal</option><option value="market">Mercado</option></select>
          </label>
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">Ámbito específico</span>
            <select name="scope_id" required className={inputCls}>
              <option value="">Selecciona…</option>
              {storeId && <option value={storeId}>{stores.find((s) => s.id === storeId)?.name} (Tienda)</option>}
              {channels.map((c) => <option key={c.id} value={c.id}>{c.name} (Canal)</option>)}
              {markets.map((m) => <option key={m.id} value={m.id}>{m.name} (Mercado)</option>)}
            </select>
          </label>
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">Prioridad</span><input name="priority" type="number" defaultValue={0} min={0} className={inputCls} /></label>
          <div className="flex items-end"><Button variant="primary" type="submit">Asignar</Button></div>
        </form>
      )}
      <DataTable
        columns={scopeCols}
        rows={scopes}
        keyField={(s) => s.id}
        empty={<EmptyState title="Sin asignaciones" description="Esta bodega no sirve todavía a ninguna tienda, canal o mercado." />}
        rowActions={(s) => canManageScopes && s.status !== "archived" ? <Button size="sm" variant="danger" onClick={() => archiveScope(s)}>Archivar</Button> : null}
      />
      {error && <p className="mt-3 text-sm text-red-300" role="alert">{error}</p>}
    </AdminShell>
  );
}
