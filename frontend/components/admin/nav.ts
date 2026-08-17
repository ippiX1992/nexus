export type NavItem = { href: string; label: string };
export type NavGroup = { label: string; items: NavItem[]; comingSoon?: boolean };

// Menú orientado al trabajo (no al modelo técnico): grupos por lo que el
// usuario quiere hacer. Lo poco usado vive en "Configuración avanzada".
export const NAV_GROUPS: NavGroup[] = [
  {
    label: "Ventas",
    items: [{ href: "/commerce/orders", label: "Pedidos" }],
  },
  {
    label: "Catálogo",
    items: [
      { href: "/catalog/products", label: "Productos" },
      { href: "/catalog/taxonomies", label: "Categorías" },
      { href: "/catalog/brands", label: "Marcas" },
    ],
  },
  {
    label: "Inventario",
    items: [
      { href: "/commerce/inventory", label: "Stock" },
      { href: "/commerce/warehouses", label: "Bodegas" },
      { href: "/commerce/transfers", label: "Transferencias" },
    ],
  },
  {
    label: "Precios",
    items: [
      { href: "/commerce/price-lists", label: "Listas de precios" },
      { href: "/commerce/pricing-rules", label: "Reglas de precio" },
      { href: "/commerce/price-history", label: "Historial" },
    ],
  },
  {
    label: "Canales",
    items: [
      { href: "/platform/stores", label: "Tiendas" },
      { href: "/platform/markets", label: "Mercados" },
    ],
  },
  {
    label: "Administración",
    items: [
      { href: "/members", label: "Miembros" },
      { href: "/roles", label: "Roles" },
      { href: "/security", label: "Seguridad" },
      { href: "/sessions", label: "Sesiones" },
      { href: "/profile", label: "Perfil" },
      { href: "/platform/operations", label: "Operaciones" },
      { href: "/platform/usage", label: "Uso y cuotas" },
    ],
  },
  {
    label: "Configuración avanzada",
    items: [
      { href: "/catalog/product-types", label: "Tipos de producto" },
      { href: "/catalog/options", label: "Opciones" },
      { href: "/catalog/attributes", label: "Atributos" },
      { href: "/catalog/attribute-groups", label: "Grupos de atributos" },
      { href: "/platform/sites", label: "Sitios" },
      { href: "/platform/channels", label: "Canales de venta" },
      { href: "/platform/environments", label: "Ambientes" },
    ],
  },
];

export function groupForPath(pathname: string): string | null {
  for (const group of NAV_GROUPS) {
    if (group.items.some((item) => pathname.startsWith(item.href))) return group.label;
  }
  return null;
}

export function breadcrumbsForPath(pathname: string, currentTitle: string): NavItem[] {
  const group = NAV_GROUPS.find((g) => g.items.some((item) => pathname.startsWith(item.href)));
  const crumbs: NavItem[] = [{ href: "/dashboard", label: "Inicio" }];
  if (group) {
    const landing = group.items[0];
    crumbs.push({ href: landing.href, label: group.label });
  }
  crumbs.push({ href: pathname, label: currentTitle });
  return crumbs;
}
