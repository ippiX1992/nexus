export type NavItem = { href: string; label: string };
export type NavGroup = { label: string; items: NavItem[]; comingSoon?: boolean };

export const NAV_GROUPS: NavGroup[] = [
  {
    label: "Catálogo",
    items: [
      { href: "/catalog/products", label: "Productos" },
      { href: "/catalog/product-types", label: "Tipos de producto" },
      { href: "/catalog/brands", label: "Marcas" },
      { href: "/catalog/taxonomies", label: "Categorías" },
      { href: "/catalog/options", label: "Opciones" },
      { href: "/catalog/attributes", label: "Atributos" },
      { href: "/catalog/attribute-groups", label: "Grupos de atributos" },
    ],
  },
  {
    label: "Comercio",
    items: [
      { href: "/commerce/price-lists", label: "Listas de precios" },
      { href: "/commerce/pricing-rules", label: "Reglas de precio" },
      { href: "/commerce/price-history", label: "Historial de precios" },
      { href: "/commerce/warehouses", label: "Bodegas" },
      { href: "/commerce/inventory", label: "Inventario" },
      { href: "/commerce/transfers", label: "Transferencias" },
      { href: "/commerce/orders", label: "Pedidos" },
    ],
  },
  { label: "Contenido", items: [], comingSoon: true },
  {
    label: "Plataforma",
    items: [
      { href: "/platform/stores", label: "Tiendas" },
      { href: "/platform/sites", label: "Sitios" },
      { href: "/platform/channels", label: "Canales" },
      { href: "/platform/environments", label: "Ambientes" },
      { href: "/platform/markets", label: "Mercados" },
      { href: "/platform/operations", label: "Operaciones" },
      { href: "/platform/usage", label: "Uso y cuotas" },
    ],
  },
  {
    label: "Ajustes",
    items: [
      { href: "/profile", label: "Perfil" },
      { href: "/security", label: "Seguridad" },
      { href: "/sessions", label: "Sesiones" },
      { href: "/members", label: "Miembros" },
      { href: "/roles", label: "Roles" },
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
