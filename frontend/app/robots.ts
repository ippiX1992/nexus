import type { MetadataRoute } from "next";

// Search engines: index the public storefront, keep the admin panel out.
export default function robots(): MetadataRoute.Robots {
  const base = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3010";
  return {
    rules: {
      userAgent: "*",
      allow: "/tienda",
      disallow: ["/dashboard", "/catalog", "/commerce", "/platform", "/members", "/roles", "/security", "/sessions", "/profile", "/select-tenant"],
    },
    sitemap: `${base}/sitemap.xml`,
  };
}
