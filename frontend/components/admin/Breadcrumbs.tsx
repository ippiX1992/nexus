import Link from "next/link";
import type { NavItem } from "./nav";

export function Breadcrumbs({ items }: { items: NavItem[] }) {
  return (
    <nav aria-label="Breadcrumb" className="mb-3 flex items-center gap-1.5 text-xs text-muted">
      {items.map((item, index) => {
        const last = index === items.length - 1;
        return (
          <span key={`${item.href}-${index}`} className="flex items-center gap-1.5">
            {index > 0 && <span aria-hidden="true">/</span>}
            {last ? (
              <span className="font-medium text-text">{item.label}</span>
            ) : (
              <Link href={item.href} className="hover:text-text">
                {item.label}
              </Link>
            )}
          </span>
        );
      })}
    </nav>
  );
}
