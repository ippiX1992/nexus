"use client";

/** Consistent tab strip for detail pages (e.g. product / order sub-views). */
export function Tabs({
  tabs,
  active,
  onChange,
}: {
  tabs: { key: string; label: string; count?: number }[];
  active: string;
  onChange: (key: string) => void;
}) {
  return (
    <div className="mb-5 flex gap-1 border-b border-line">
      {tabs.map((t) => {
        const on = t.key === active;
        return (
          <button
            key={t.key}
            type="button"
            onClick={() => onChange(t.key)}
            className={`-mb-px border-b-2 px-3.5 py-2 text-sm font-medium transition ${
              on ? "border-brand text-text" : "border-transparent text-muted hover:text-text"
            }`}
          >
            {t.label}
            {t.count !== undefined && <span className="ml-1.5 text-xs text-muted">{t.count}</span>}
          </button>
        );
      })}
    </div>
  );
}
