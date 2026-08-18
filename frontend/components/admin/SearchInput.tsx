"use client";
import type { FormEvent } from "react";

export function SearchInput({
  value,
  onChange,
  onSubmit,
  placeholder = "Buscar…",
  className = "",
}: {
  value: string;
  onChange: (value: string) => void;
  onSubmit?: () => void;
  placeholder?: string;
  className?: string;
}) {
  function submit(e: FormEvent) {
    e.preventDefault();
    onSubmit?.();
  }
  return (
    <form onSubmit={submit} className={`relative ${className}`}>
      <svg viewBox="0 0 24 24" fill="none" className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted">
        <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="2" />
        <path d="m20 20-3-3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      </svg>
      <input
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        aria-label={placeholder}
        className="w-full rounded-lg border border-line bg-bg py-2 pl-9 pr-3 text-sm text-text placeholder:text-muted/60 focus:border-brand focus:outline-none"
      />
    </form>
  );
}
