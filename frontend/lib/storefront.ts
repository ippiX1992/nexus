// Public storefront client. Unlike lib/api.ts (admin, authenticated) these
// endpoints need no token/CSRF — a shopper is anonymous. Calls go to the same
// origin (relative /api/v1) and Next rewrites them to the backend.
const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export const STORE_KEY = "clickhome";
// Continental shipping is free at/above this subtotal — mirrors the backend
// (_FREE_SHIPPING_MIN). Drives the cart's free-shipping progress bar.
export const FREE_SHIPPING_MIN = 99;

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
export type StoreProductDetail = StoreProduct & { long_description?: string | null; images?: string[]; videos?: string[]; specs?: SpecItem[]; category_slug?: string | null };

// Turn a video URL into something playable: YouTube/Vimeo become embed iframes;
// anything else (a direct .mp4/.webm or an uploaded /media file) plays inline.
export function videoEmbed(url: string): { kind: "iframe" | "file"; src: string } {
  const yt = url.match(/(?:youtube\.com\/(?:watch\?v=|embed\/)|youtu\.be\/)([\w-]{11})/);
  if (yt) return { kind: "iframe", src: `https://www.youtube.com/embed/${yt[1]}` };
  const vimeo = url.match(/vimeo\.com\/(?:video\/)?(\d+)/);
  if (vimeo) return { kind: "iframe", src: `https://player.vimeo.com/video/${vimeo[1]}` };
  return { kind: "file", src: url };
}
export type StoreMeta = { key: string; name: string; currency: string; locale: string; brand?: string | null; product_count: number };
export type StoreProductList = { items: StoreProduct[]; total: number };
export type StoreCategory = { slug: string; name: string; product_count: number; children?: StoreCategory[] };

// The catalog stores each product photo as the small PrestaShop "home_default"
// thumbnail (~236px). The same host also serves larger, white-background
// renders of the exact same photo (medium ~452px, thickbox ~1100px). Swap the
// size token so images render crisp on the white product surfaces. Returns the
// URL unchanged when it isn't a recognizable size-tagged clickhome URL.
const IMAGE_SIZE_RE = /-(?:small|home|medium|large|thickbox|cart)_default\//;
export function imageAt(url: string | null | undefined, size: "medium" | "large" | "thickbox"): string | null {
  if (!url) return null;
  return IMAGE_SIZE_RE.test(url) ? url.replace(IMAGE_SIZE_RE, `-${size}_default/`) : url;
}

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
export type Suggestion = { slug: string; name: string; image?: string | null };
export function suggest(query: string) {
  return storeFetch<Suggestion[]>(`/${STORE_KEY}/suggest?q=${encodeURIComponent(query)}`);
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
  shipping_province?: string | null;
  shipping_city?: string | null;
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
  shipping_province?: string;
  shipping_city?: string;
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
export function createOrder(payload: OrderInput, idempotencyKey?: string) {
  // Sending a stable key per checkout makes a double-clicked / retried submit
  // create one order and reserve stock once (the backend replays the first).
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (idempotencyKey) headers["Idempotency-Key"] = idempotencyKey;
  return storeFetch<StoreOrder>(`/${STORE_KEY}/orders`, { method: "POST", headers, body: JSON.stringify(payload) });
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
