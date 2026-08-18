import type { ReactNode } from "react";

/** A consistent toolbar row above a table: search on the left, filters/actions
 *  on the right. Wraps gracefully on laptop/tablet widths. */
export function FilterBar({ children }: { children: ReactNode }) {
  return <div className="mb-4 flex flex-wrap items-center gap-2">{children}</div>;
}

export function Spacer() {
  return <div className="ml-auto" />;
}

/** Shared select styling so every filter dropdown matches. */
export function Select({
  value,
  onChange,
  children,
  label,
}: {
  value: string;
  onChange: (value: string) => void;
  children: ReactNode;
  label: string;
}) {
  return (
    <select
      aria-label={label}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-auto rounded-lg border border-line bg-bg px-3 py-2 text-sm text-text focus:border-brand focus:outline-none"
    >
      {children}
    </select>
  );
}
