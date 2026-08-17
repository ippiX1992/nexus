import Link from "next/link";

type Tone = "default" | "brand" | "good" | "warn" | "bad";

// Semantic left accent so a KPI can signal "todo bien" vs "requiere atención".
const TONE: Record<Tone, string> = {
  default: "",
  brand: "border-l-4 border-l-brand",
  good: "border-l-4 border-l-emerald-500",
  warn: "border-l-4 border-l-amber-500",
  bad: "border-l-4 border-l-red-500",
};

export function StatCard({
  label,
  value,
  hint,
  icon,
  tone = "default",
  href,
}: {
  label: string;
  value: string | number;
  hint?: string;
  icon?: string;
  tone?: Tone;
  href?: string;
}) {
  const body = (
    <>
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs font-medium uppercase tracking-wide text-muted">{label}</p>
        {icon && (
          <span aria-hidden className="text-lg leading-none">
            {icon}
          </span>
        )}
      </div>
      <p className="mt-2 text-2xl font-semibold text-text">{value}</p>
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
    </>
  );
  const base = `block rounded-xl border border-line bg-panel-2 p-4 ${TONE[tone]}`;
  if (href) {
    return (
      <Link href={href} className={`${base} transition hover:border-brand/60 hover:bg-white/5`}>
        {body}
      </Link>
    );
  }
  return <div className={base}>{body}</div>;
}
