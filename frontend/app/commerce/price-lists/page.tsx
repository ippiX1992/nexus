"use client";
import { inputCls } from "@/components/admin/forms";
import { type FormEvent, useEffect, useState } from "react";
import { AdminShell } from "@/components/admin/AdminShell";
import { Button, LinkButton } from "@/components/admin/Button";
import { DataTable, type Column } from "@/components/admin/DataTable";
import { EmptyState } from "@/components/admin/EmptyState";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { api } from "@/lib/api";
import { type PriceList, pricingCommand, pricingCreate, pricingPage, technicalError } from "@/lib/pricing";


export default function Page() {
  const [items, setItems] = useState<PriceList[]>([]);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const canManage = permissions.includes("pricing.price_list.create");
  const canArchive = permissions.includes("pricing.price_list.archive");

  async function load() {
    setLoading(true);
    try {
      const [page, ctx] = await Promise.all([pricingPage<PriceList>("/price-lists"), api("/me/context")]);
      setItems(page.items);
      setPermissions(ctx.permissions);
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

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const el = event.currentTarget;
    const form = new FormData(el);
    try {
      await pricingCreate("/price-lists", { code: form.get("code"), name: form.get("name"), currency_code: form.get("currency_code"), is_default: form.get("is_default") === "on" });
      el.reset();
      setShowForm(false);
      await load();
    } catch (e) {
      setError(technicalError(e));
    }
  }
  async function archive(item: PriceList) {
    try {
      await pricingCommand(`/price-lists/${item.id}/archive`, item.version);
      await load();
    } catch (e) {
      setError(technicalError(e));
    }
  }

  const columns: Column<PriceList>[] = [
    {
      key: "name",
      header: "Nombre",
      render: (p) => (
        <span className="flex items-center gap-2">
          <span className="font-medium text-text">{p.name}</span>
          {p.is_default && <StatusBadge label="Por defecto" tone="brand" />}
        </span>
      ),
    },
    { key: "code", header: "Código", render: (p) => <span className="text-muted">{p.code}</span>, hideOnMobile: true },
    { key: "currency_code", header: "Moneda", render: (p) => p.currency_code },
    { key: "status", header: "Estado", render: (p) => <StatusBadge status={p.status} /> },
  ];

  return (
    <AdminShell
      title="Listas de precios"
      description="Listas de precios por moneda. Se asignan a una tienda, canal o mercado con prioridad y vigencia."
      actions={canManage && <Button variant="primary" onClick={() => setShowForm((v) => !v)}>{showForm ? "Cerrar" : "Nueva lista"}</Button>}
    >
      {showForm && canManage && (
        <form onSubmit={submit} className="mb-5 grid gap-3 rounded-xl border border-line bg-panel p-4 sm:grid-cols-2 lg:grid-cols-3">
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">Código</span><input name="code" required className={inputCls} /></label>
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">Nombre</span><input name="name" required className={inputCls} /></label>
          <label className="grid gap-1.5 text-sm"><span className="font-medium text-text">Moneda (ISO 4217)</span><input name="currency_code" defaultValue="USD" maxLength={3} required className={inputCls} /></label>
          <label className="flex items-center gap-2 self-end text-sm text-text"><input type="checkbox" name="is_default" className="h-4 w-4 !w-4" /> Lista por defecto</label>
          <div className="flex items-end"><Button variant="primary" type="submit">Crear lista</Button></div>
        </form>
      )}
      <DataTable
        columns={columns}
        rows={items}
        keyField={(p) => p.id}
        loading={loading}
        onRowClick={(p) => { window.location.href = `/commerce/price-lists/${p.id}`; }}
        empty={<EmptyState title="Sin listas de precios" description="Crea la primera para fijar los precios de tu catálogo." action={canManage ? <Button variant="primary" onClick={() => setShowForm(true)}>Nueva lista</Button> : undefined} />}
        rowActions={(p) => (
          <>
            <LinkButton href={`/commerce/price-lists/${p.id}`} size="sm" variant="ghost">Ver precios</LinkButton>
            {canArchive && p.status !== "archived" && <Button size="sm" variant="danger" onClick={() => archive(p)}>Archivar</Button>}
          </>
        )}
      />
      {error && <p className="mt-3 text-sm text-red-300" role="alert">{error}</p>}
    </AdminShell>
  );
}
