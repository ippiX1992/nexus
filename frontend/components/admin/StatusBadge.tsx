import type { ReactNode } from "react";

type Tone = "neutral" | "info" | "success" | "warning" | "danger" | "brand";

const TONE: Record<Tone, string> = {
  neutral: "bg-white/8 text-muted ring-1 ring-inset ring-white/10",
  info: "bg-sky-500/15 text-sky-300 ring-1 ring-inset ring-sky-500/25",
  success: "bg-emerald-500/15 text-emerald-300 ring-1 ring-inset ring-emerald-500/25",
  warning: "bg-amber-500/15 text-amber-300 ring-1 ring-inset ring-amber-500/25",
  danger: "bg-red-500/15 text-red-300 ring-1 ring-inset ring-red-500/25",
  brand: "bg-brand/15 text-brand ring-1 ring-inset ring-brand/30",
};

// One source of truth for every status label + color in the panel, so an order,
// a product and a stock level all speak the same visual language.
const MAP: Record<string, { label: string; tone: Tone }> = {
  // storefront order lifecycle
  placed: { label: "Recibido", tone: "warning" },
  confirmed: { label: "Confirmado", tone: "info" },
  preparing: { label: "En preparación", tone: "info" },
  shipped: { label: "Enviado", tone: "brand" },
  delivered: { label: "Entregado", tone: "success" },
  cancelled: { label: "Cancelado", tone: "danger" },
  // generic resource lifecycle
  active: { label: "Activo", tone: "success" },
  archived: { label: "Archivado", tone: "neutral" },
  draft: { label: "Borrador", tone: "neutral" },
  // inventory / transfers / reservations
  in_transit: { label: "En tránsito", tone: "info" },
  completed: { label: "Completada", tone: "success" },
  held: { label: "Reservado", tone: "warning" },
  released: { label: "Liberada", tone: "neutral" },
  committed: { label: "Consumida", tone: "success" },
  expired: { label: "Expirada", tone: "danger" },
  out_of_stock: { label: "Sin stock", tone: "danger" },
  low_stock: { label: "Stock bajo", tone: "warning" },
  in_stock: { label: "En stock", tone: "success" },
  error: { label: "Error", tone: "danger" },
};

export function StatusBadge({
  status,
  label,
  tone,
  icon,
}: {
  status?: string;
  label?: string;
  tone?: Tone;
  icon?: ReactNode;
}) {
  const known = status ? MAP[status] : undefined;
  const text = label ?? known?.label ?? status ?? "—";
  const resolved: Tone = tone ?? known?.tone ?? "neutral";
  return (
    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium ${TONE[resolved]}`}>
      {icon}
      {text}
    </span>
  );
}
