// Public storefront client. Unlike lib/api.ts (admin, authenticated) these
// endpoints need no token/CSRF — a shopper is anonymous. Calls go to the same
// origin (relative /api/v1) and Next rewrites them to the backend.
const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export const STORE_KEY = "clickhome";

export type StoreProduct = {
  slug: string;
  name: string;
  short_description?: string | null;
  brand?: string | null;
  image?: string | null;
  sku: string;
  price: string | null;
  compare_at: string | null;
  currency: string;
  available: number;
  in_stock: boolean;
};
export type StoreProductDetail = StoreProduct & { long_description?: string | null };
export type StoreMeta = { key: string; name: string; currency: string; locale: string; brand?: string | null; product_count: number };
export type StoreProductList = { items: StoreProduct[]; total: number };
export type StoreCategory = { slug: string; name: string; product_count: number };

async function storeFetch<T>(path: string): Promise<T> {
  const res = await fetch(`${API}/storefront${path}`, { credentials: "omit" });
  if (!res.ok) throw new Error(`No se pudo cargar la tienda (HTTP ${res.status})`);
  return res.json();
}

export function storeMeta() {
  return storeFetch<StoreMeta>(`/${STORE_KEY}`);
}
export function storeProducts(search = "", category = "") {
  const params = new URLSearchParams();
  if (search) params.set("search", search);
  if (category) params.set("category", category);
  const query = params.toString();
  return storeFetch<StoreProductList>(`/${STORE_KEY}/products${query ? `?${query}` : ""}`);
}
export function storeCategories() {
  return storeFetch<StoreCategory[]>(`/${STORE_KEY}/categories`);
}
export function storeProduct(slug: string) {
  return storeFetch<StoreProductDetail>(`/${STORE_KEY}/products/${encodeURIComponent(slug)}`);
}

export function formatPrice(value: string | number | null | undefined, currency = "USD") {
  if (value === null || value === undefined || value === "") return "Consultar";
  const amount = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(amount)) return "Consultar";
  // Ecuador uses USD with a period decimal ("$51.84"); en-US gives exactly that.
  return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(amount);
}
