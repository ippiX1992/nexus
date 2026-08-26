import type { MetadataRoute } from "next";
import { STORE_KEY } from "@/lib/storefront";

// Rebuild hourly. Lists the storefront's static pages plus every product URL,
// fetched server-side; if the backend is unreachable (e.g. at build time) the
// sitemap degrades to just the static routes.
export const revalidate = 3600;

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const base = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3010";
  const backend = process.env.BACKEND_ORIGIN ?? "http://127.0.0.1:8010";

  const routes: MetadataRoute.Sitemap = [
    { url: `${base}/tienda`, changeFrequency: "daily", priority: 1 },
    { url: `${base}/tienda/rastrear`, changeFrequency: "monthly", priority: 0.3 },
    { url: `${base}/tienda/favoritos`, changeFrequency: "monthly", priority: 0.3 },
  ];

  try {
    const res = await fetch(`${backend}/api/v1/storefront/${STORE_KEY}/products?limit=1000`, { next: { revalidate: 3600 } });
    if (res.ok) {
      const data: { items?: { slug: string }[] } = await res.json();
      for (const product of data.items ?? []) {
        routes.push({ url: `${base}/tienda/${product.slug}`, changeFrequency: "weekly", priority: 0.7 });
      }
    }
  } catch {
    /* backend unavailable — return the static routes only */
  }

  return routes;
}
