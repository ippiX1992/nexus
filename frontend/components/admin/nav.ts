export type NavItem = { href: string; label: string };
export type NavGroup = { label: string; items: NavItem[]; comingSoon?: boolean };

export const NAV_GROUPS: NavGroup[] = [
  {
    label: "Catalog",
    items: [
      { href: "/catalog/products", label: "Products" },
      { href: "/catalog/product-types", label: "Product Types" },
      { href: "/catalog/brands", label: "Brands" },
      { href: "/catalog/taxonomies", label: "Taxonomies" },
      { href: "/catalog/options", label: "Options" },
      { href: "/catalog/attributes", label: "Attributes" },
      { href: "/catalog/attribute-groups", label: "Attribute Groups" },
    ],
  },
  { label: "Commerce", items: [], comingSoon: true },
  { label: "Content", items: [], comingSoon: true },
  {
    label: "Platform",
    items: [
      { href: "/platform/stores", label: "Stores" },
      { href: "/platform/sites", label: "Sites" },
      { href: "/platform/channels", label: "Channels" },
      { href: "/platform/environments", label: "Environments" },
      { href: "/platform/markets", label: "Markets" },
      { href: "/platform/operations", label: "Operations" },
      { href: "/platform/usage", label: "Uso y cuotas" },
    ],
  },
  {
    label: "Settings",
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
