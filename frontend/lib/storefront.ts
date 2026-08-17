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
  image2?: string | null;
  sku: string;
  price: string | null;
  compare_at: string | null;
  currency: string;
  available: number;
  in_stock: boolean;
};
export type SpecItem = { label: string; value: string };
export type StoreProductDetail = StoreProduct & { long_description?: string | null; images?: string[]; specs?: SpecItem[] };
export type StoreMeta = { key: string; name: string; currency: string; locale: string; brand?: string | null; product_count: number };
export type StoreProductList = { items: StoreProduct[]; total: number };
export type StoreCategory = { slug: string; name: string; product_count: number; children?: StoreCategory[] };

async function storeFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const headers = options?.body ? { "Content-Type": "application/json" } : undefined;
  const res = await fetch(`${API}/storefront${path}`, { credentials: "omit", headers, ...options });
  if (!res.ok) {
    let detail = "";
    try {
      detail = (await res.json()).detail ?? "";
    } catch {
      /* non-JSON error */
    }
    throw new Error(detail || `No se pudo completar la solicitud (HTTP ${res.status})`);
  }
  return res.json();
}

export function storeMeta() {
  return storeFetch<StoreMeta>(`/${STORE_KEY}`);
}
export function storeProducts(
  search = "",
  category = "",
  limit?: number,
  offset?: number,
  sort?: string,
  minPrice?: number,
  maxPrice?: number,
) {
  const params = new URLSearchParams();
  if (search) params.set("search", search);
  if (category) params.set("category", category);
  if (limit) params.set("limit", String(limit));
  if (offset) params.set("offset", String(offset));
  if (sort && sort !== "name") params.set("sort", sort);
  if (minPrice) params.set("min_price", String(minPrice));
  if (maxPrice) params.set("max_price", String(maxPrice));
  const query = params.toString();
  return storeFetch<StoreProductList>(`/${STORE_KEY}/products${query ? `?${query}` : ""}`);
}
export function storeCategories() {
  return storeFetch<StoreCategory[]>(`/${STORE_KEY}/categories`);
}
export function storeProduct(slug: string) {
  return storeFetch<StoreProductDetail>(`/${STORE_KEY}/products/${encodeURIComponent(slug)}`);
}

export type OrderLine = { sku: string; name: string; unit_amount: string | null; quantity: number; line_total: string };
export type StoreOrder = {
  order_number: string;
  tracking_number: string;
  status: string;
  currency: string;
  subtotal: string;
  shipping_method?: string;
  shipping_amount?: string;
  coupon_code?: string | null;
  discount_amount?: string;
  total?: string;
  item_count: number;
  customer_name: string;
  placed_at: string;
  items: OrderLine[];
};
export type TrackingStage = { status: string; label: string; at: string; done: boolean };
export type Tracking = { order_number: string; tracking_number: string; status: string; estimated_delivery: string; stages: TrackingStage[] };
export type OrderInput = {
  customer_name: string;
  customer_email?: string;
  customer_phone?: string;
  shipping_address?: string;
  shipping_method?: string;
  coupon_code?: string;
  items: { slug: string; quantity: number }[];
};
export type CouponInfo = { code: string; valid: boolean; label?: string | null; discount_type?: string | null; value?: number | null };
export type Review = { author: string; rating: number; comment?: string | null; created_at: string };
export type ReviewSummary = { average: number; count: number; items: Review[] };

export function validateCoupon(code: string) {
  return storeFetch<CouponInfo>(`/${STORE_KEY}/coupons/${encodeURIComponent(code)}`);
}
export function getReviews(slug: string) {
  return storeFetch<ReviewSummary>(`/${STORE_KEY}/products/${encodeURIComponent(slug)}/reviews`);
}
export function createReview(slug: string, payload: { author: string; rating: number; comment?: string }) {
  return storeFetch<ReviewSummary>(`/${STORE_KEY}/products/${encodeURIComponent(slug)}/reviews`, { method: "POST", body: JSON.stringify(payload) });
}

export function productStock(slug: string) {
  return storeFetch<{ slug: string; available: number; in_stock: boolean }>(`/${STORE_KEY}/products/${encodeURIComponent(slug)}/stock`);
}
export function createOrder(payload: OrderInput) {
  return storeFetch<StoreOrder>(`/${STORE_KEY}/orders`, { method: "POST", body: JSON.stringify(payload) });
}
export function getOrder(orderNumber: string) {
  return storeFetch<StoreOrder>(`/${STORE_KEY}/orders/${encodeURIComponent(orderNumber)}`);
}
export function getTracking(orderNumber: string) {
  return storeFetch<Tracking>(`/${STORE_KEY}/orders/${encodeURIComponent(orderNumber)}/tracking`);
}

export function formatPrice(value: string | number | null | undefined, currency = "USD") {
  if (value === null || value === undefined || value === "") return "Consultar";
  const amount = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(amount)) return "Consultar";
  // Ecuador uses USD with a period decimal ("$51.84"); en-US gives exactly that.
  return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(amount);
}
