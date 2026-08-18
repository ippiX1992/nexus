"use client";
import { useParams } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";
import { AdminShell } from "@/components/admin/AdminShell";
import { Button, LinkButton } from "@/components/admin/Button";
import { DataTable, type Column } from "@/components/admin/DataTable";
import { EmptyState } from "@/components/admin/EmptyState";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { api } from "@/lib/api";
import { variantLabels } from "@/lib/catalog";
import { activeStore, listStores, type Store } from "@/lib/platform";
import { type Assignment, type PriceList, type PriceListEntry, type ScopeType, pricingCommand, pricingCreate, pricingGet, pricingPage, pricingPut, technicalError } from "@/lib/pricing";

type ScopeOption = { id: string; name: string };
const inputCls = "rounded-lg border border-line bg-bg px-3 py-2 text-sm text-text focus:border-brand focus:outline-none";
const SCOPE_LABEL: Record<string, string> = { store: "Tienda", channel: "Canal", market: "Mercado" };

export default function Page() {
  const params = useParams();
  const priceListId = String(params.id);
  const [priceList, setPriceList] = useState<PriceList | null>(null);
  const [entries, setEntries] = useState<PriceListEntry[]>([]);
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [stores, setStores] = useState<Store[]>([]);
  const [storeId, setStoreId] = useState(activeStore() ?? "");
  const [channels, setChannels] = useState<ScopeOption[]>([]);
  const [markets, setMarkets] = useState<ScopeOption[]>([]);
  const [names, setNames] = useState<Map<string, string>>(new Map());
  const [showEntry, setShowEntry] = useState(false);
  const [showAssign, setShowAssign] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const canManageEntries = permissions.includes("pricing.price_list_entry.manage");
  const canManageAssignments = permissions.includes("pricing.assignment.manage");

  async function load() {
    setLoading(true);
    try {
      const [list, entryPage, assignmentPage, ctx, storeList, labels] = await Promise.all([
        pricingGet<PriceList>(`/price-lists/${priceListId}`),
        pricingPage<PriceListEntry>(`/price-lists/${priceListId}/entries`),
        pricingPage<Assignment>(`/assignments?price_list_id=${priceListId}`),
        api("/me/context"),
        listStores(),
        variantLabels().catch(() => new Map<string, string>()),
      ]);
      setPriceList(list);
      setEntries(entryPage.items);
      setAssignments(assignmentPage.items);
      setPermissions(ctx.permissions);
      setStores(storeList);
      setNames(labels);
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
  }, [priceListId]);
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

  const variantName = (id: string) => (names.get(id) ?? "").split(" · ")[0] || id;

  async function submitEntry(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const el = event.currentTarget;
    const form = new FormData(el);
    const variantId = String(form.get("variant_id"));
    try {
      await pricingPut(`/price-lists/${priceListId}/entries/${variantId}`, {
        unit_amount: form.get("unit_amount"),
        compare_at_amount: form.get("compare_at_amount") || null,
        msrp_amount: form.get("msrp_amount") || null,
        cost_amount: form.get("cost_amount") || null,
      });
      el.reset();
      setShowEntry(false);
      await load();
    } catch (e) {
      setError(technicalError(e));
    }
  }
  async function submitAssignment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const el = event.currentTarget;
    const form = new FormData(el);
    const scopeType = String(form.get("scope_type")) as ScopeType;
    const scopeId = String(form.get("scope_id"));
    try {
      await pricingCreate("/assignments", {
        price_list_id: priceListId,
        scope_type: scopeType,
        store_id: scopeType === "store" ? scopeId : undefined,
        channel_id: scopeType === "channel" ? scopeId : undefined,
        market_id: scopeType === "market" ? scopeId : undefined,
        priority: Number(form.get("priority") || 0),
        effective_from: form.get("effective_from") || undefined,
        effective_until: form.get("effective_until") || undefined,
      });
      el.reset();
      setShowAssign(false);
      await load();
    } catch (e) {
      setError(technicalError(e));
    }
  }
  async function archiveAssignment(item: Assignment) {
    try {
      await pricingCommand(`/assignments/${item.id}/archive`, item.version);
      await load();
    } catch (e) {
      setError(technicalError(e));
    }
  }

  const breadcrumbs = [
    { href: "/dashboard", label: "Inicio" },
    { href: "/commerce/price-lists", label: "Listas de precios" },
    { href: `/commerce/price-lists/${priceListId}`, label: priceList?.name ?? "Lista" },
  ];
  if (loading && !priceList) return <AdminShell title="Lista de precios" breadcrumbs={breadcrumbs}><p className="text-muted">Cargando…</p></AdminShell>;
  if (!priceList) return <AdminShell title="Lista de precios" breadcrumbs={breadcrumbs}><p className="text-sm text-red-300" role="alert">{error || "No encontrada"}</p></AdminShell>;

  const entryCols: Column<PriceListEntry>[] = [
    { key: "variant", header: "Producto", render: (e) => <span className="font-medium text-text">{variantName(e.variant_id)}</span> },
    { key: "unit_amount", header: "Base", align: "right", render: (e) => e.unit_amount },
    { key: "compare_at_amount", header: "Comparación", align: "right", render: (e) => e.compare_at_amount ?? "—", hideOnMobile: true },
    { key: "msrp_amount", header: "MSRP", align: "right", render: (e) => e.msrp_amount ?? "—", hideOnMobile: true },
    { key: "cost_amount", header: "Costo", align: "right", render: (e) => e.cost_amount ?? "—", hideOnMobile: true },
  ];
  const assignCols: Column<Assignment>[] = [
    { key: "scope_type", header: "Ámbito", render: (a) => <span className="font-medium text-text">{SCOPE_LABEL[a.scope_type] ?? a.scope_type}</span> },
    { key: "priority", header: "Prioridad", align: "right", render: (a) => a.priority },
    { key: "vigencia", header: "Vigencia", render: (a) => <span className="text-muted">{a.effective_from ? new Date(a.effective_from).toLocaleDateString("es-EC") : "—"} → {a.effective_until ? new Date(a.effective_until).toLocaleDateString("es-EC") : "—"}</span>, hideOnMobile: true },
    { key: "status", header: "Estado", render: (a) => <StatusBadge status={a.status} /> },
  ];

  return (
    <AdminShell
      title={priceList.name}
      description={`${priceList.code} · ${priceList.currency_code}${priceList.is_default ? " · por defecto" : ""}`}
      breadcrumbs={breadcrumbs}
      actions={<LinkButton href="/commerce/price-lists" variant="ghost">← Listas de precios</LinkButton>}
    >
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-text">Precios por producto</h2>
        {canManageEntries && <Button variant="secondary" onClick={() => setShowEntry((v) => !v)}>{showEntry ? "Cerrar" : "Definir precio"}</Button>}
      </div>
      {showEntry && canManageEntries && (
        <form onSubmit={submitEntry} className="mb-4 grid gap-3 rounded-xl border border-line bg-panel p-4 sm:grid-cols-2 lg:grid-cols-5">
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">ID del producto (variant)</span><input name="variant_id" placeholder="uuid del variant" required className={inputCls} /></label>
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">Precio base</span><input name="unit_amount" type="number" step="0.0001" min="0" required className={inputCls} /></label>
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">Comparación</span><input name="compare_at_amount" type="number" step="0.0001" min="0" className={inputCls} /></label>
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">MSRP</span><input name="msrp_amount" type="number" step="0.0001" min="0" className={inputCls} /></label>
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">Costo</span><input name="cost_amount" type="number" step="0.0001" min="0" className={inputCls} /></label>
          <div className="flex items-end"><Button variant="primary" type="submit">Guardar precio</Button></div>
        </form>
      )}
      <DataTable columns={entryCols} rows={entries} keyField={(e) => e.id} empty={<EmptyState title="Sin precios todavía" description="Agrega el primer producto para empezar esta lista." />} />

      <div className="mb-3 mt-8 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-text">Dónde se aplica</h2>
        {canManageAssignments && <Button variant="secondary" onClick={() => setShowAssign((v) => !v)}>{showAssign ? "Cerrar" : "Asignar"}</Button>}
      </div>
      {showAssign && canManageAssignments && (
        <form onSubmit={submitAssignment} className="mb-4 grid gap-3 rounded-xl border border-line bg-panel p-4 sm:grid-cols-2 lg:grid-cols-3">
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
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">Vigente desde</span><input name="effective_from" type="datetime-local" className={inputCls} /></label>
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">Vigente hasta</span><input name="effective_until" type="datetime-local" className={inputCls} /></label>
          <div className="flex items-end"><Button variant="primary" type="submit">Crear asignación</Button></div>
        </form>
      )}
      <DataTable
        columns={assignCols}
        rows={assignments}
        keyField={(a) => a.id}
        empty={<EmptyState title="Sin asignaciones" description="Esta lista no se aplica a ninguna tienda, canal o mercado todavía." />}
        rowActions={(a) => canManageAssignments && a.status !== "archived" ? <Button size="sm" variant="danger" onClick={() => archiveAssignment(a)}>Archivar</Button> : null}
      />
      {error && <p className="mt-3 text-sm text-red-300" role="alert">{error}</p>}
    </AdminShell>
  );
}
