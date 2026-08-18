"use client";
import { type FormEvent, useEffect, useState } from "react";
import { AdminShell } from "@/components/admin/AdminShell";
import { Button } from "@/components/admin/Button";
import { DataTable, type Column } from "@/components/admin/DataTable";
import { EmptyState } from "@/components/admin/EmptyState";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { api } from "@/lib/api";
import { activeStore, listStores, type Store } from "@/lib/platform";
import { type Override, type ScopeType, pricingCommand, pricingCreate, pricingPage, technicalError } from "@/lib/pricing";

type ScopeOption = { id: string; name: string };
const inputCls = "rounded-lg border border-line bg-bg px-3 py-2 text-sm text-text focus:border-brand focus:outline-none";
const SCOPE_LABEL: Record<string, string> = { store: "Tienda", channel: "Canal", market: "Mercado" };

export default function Page() {
  const [items, setItems] = useState<Override[]>([]);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [stores, setStores] = useState<Store[]>([]);
  const [storeId, setStoreId] = useState(activeStore() ?? "");
  const [channels, setChannels] = useState<ScopeOption[]>([]);
  const [markets, setMarkets] = useState<ScopeOption[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const canManage = permissions.includes("pricing.variant_override.manage");

  async function load() {
    setLoading(true);
    try {
      const [page, ctx, storeList] = await Promise.all([pricingPage<Override>("/variant-overrides"), api("/me/context"), listStores()]);
      setItems(page.items);
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
  }, []);
  useEffect(() => {
    if (!storeId) {
      setChannels([]);
      setMarkets([]);
      return;
    }
    Promise.all([api(`/stores/${storeId}/channels`), api(`/stores/${storeId}/markets`)])
      .then(([channelList, marketList]) => {
        setChannels(channelList);
        setMarkets(marketList);
      })
      .catch((e) => setError(technicalError(e)));
  }, [storeId]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const el = event.currentTarget;
    const form = new FormData(el);
    const scopeType = String(form.get("scope_type")) as ScopeType;
    const scopeId = String(form.get("scope_id"));
    try {
      await pricingCreate("/variant-overrides", {
        variant_id: form.get("variant_id"),
        scope_type: scopeType,
        store_id: scopeType === "store" ? scopeId : undefined,
        channel_id: scopeType === "channel" ? scopeId : undefined,
        market_id: scopeType === "market" ? scopeId : undefined,
        unit_amount: form.get("unit_amount"),
        compare_at_amount: form.get("compare_at_amount") || undefined,
        currency_code: form.get("currency_code"),
        priority: Number(form.get("priority") || 0),
        effective_from: form.get("effective_from") || undefined,
        effective_until: form.get("effective_until") || undefined,
        reason: form.get("reason") || undefined,
      });
      el.reset();
      setShowForm(false);
      await load();
    } catch (e) {
      setError(technicalError(e));
    }
  }
  async function archive(item: Override) {
    try {
      await pricingCommand(`/variant-overrides/${item.id}/archive`, item.version);
      await load();
    } catch (e) {
      setError(technicalError(e));
    }
  }

  const columns: Column<Override>[] = [
    { key: "unit_amount", header: "Precio", align: "right", render: (o) => <span className="font-medium text-text">{o.unit_amount} {o.currency_code}</span> },
    { key: "scope_type", header: "Ámbito", render: (o) => <span className="text-muted">{SCOPE_LABEL[o.scope_type] ?? o.scope_type}</span> },
    { key: "priority", header: "Prioridad", align: "right", render: (o) => o.priority },
    { key: "status", header: "Estado", render: (o) => <StatusBadge status={o.status} /> },
  ];

  return (
    <AdminShell
      title="Reglas de precio"
      description="Reemplazan el precio de un producto para una tienda, canal o mercado específico, sin importar qué diga su lista de precios."
      actions={canManage && <Button variant="primary" onClick={() => setShowForm((v) => !v)}>{showForm ? "Cerrar" : "Nueva regla"}</Button>}
    >
      {showForm && canManage && (
        <form onSubmit={submit} className="mb-5 grid gap-3 rounded-xl border border-line bg-panel p-4 sm:grid-cols-2 lg:grid-cols-3">
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">ID del producto (variant)</span><input name="variant_id" placeholder="uuid del variant" required className={inputCls} /></label>
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">Tienda</span>
            <select name="store_id" value={storeId} onChange={(e) => setStoreId(e.target.value)} className={inputCls}>
              <option value="">Selecciona una tienda</option>
              {stores.filter((s) => s.status !== "archived").map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </label>
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">Tipo de ámbito</span>
            <select name="scope_type" defaultValue="store" className={inputCls}>
              <option value="store">Tienda</option>
              <option value="channel">Canal</option>
              <option value="market">Mercado</option>
            </select>
          </label>
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">Ámbito específico</span>
            <select name="scope_id" required className={inputCls}>
              <option value="">Selecciona…</option>
              {storeId && <option value={storeId}>{stores.find((s) => s.id === storeId)?.name} (Tienda)</option>}
              {channels.map((c) => <option key={c.id} value={c.id}>{c.name} (Canal)</option>)}
              {markets.map((m) => <option key={m.id} value={m.id}>{m.name} (Mercado)</option>)}
            </select>
          </label>
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">Precio</span><input name="unit_amount" type="number" step="0.0001" min="0" required className={inputCls} /></label>
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">Precio de comparación</span><input name="compare_at_amount" type="number" step="0.0001" min="0" className={inputCls} /></label>
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">Moneda (ISO 4217)</span><input name="currency_code" defaultValue="USD" maxLength={3} required className={inputCls} /></label>
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">Prioridad (mayor gana)</span><input name="priority" type="number" defaultValue={0} min={0} className={inputCls} /></label>
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">Vigente desde</span><input name="effective_from" type="datetime-local" className={inputCls} /></label>
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">Vigente hasta</span><input name="effective_until" type="datetime-local" className={inputCls} /></label>
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">Motivo</span><input name="reason" maxLength={500} className={inputCls} /></label>
          <div className="flex items-end"><Button variant="primary" type="submit">Crear regla</Button></div>
        </form>
      )}
      <DataTable
        columns={columns}
        rows={items}
        keyField={(o) => o.id}
        loading={loading}
        empty={<EmptyState title="Sin reglas todavía" description="Las reglas reemplazan cualquier lista de precios para un producto en un ámbito puntual." action={canManage ? <Button variant="primary" onClick={() => setShowForm(true)}>Nueva regla</Button> : undefined} />}
        rowActions={(o) => canManage && o.status !== "archived" ? <Button size="sm" variant="danger" onClick={() => archive(o)}>Archivar</Button> : null}
      />
      {error && <p className="mt-3 text-sm text-red-300" role="alert">{error}</p>}
    </AdminShell>
  );
}
