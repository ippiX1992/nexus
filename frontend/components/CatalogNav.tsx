import Link from"next/link";
export function CatalogNav(){return <nav className="nav" aria-label="Catalog"><Link href="/catalog/products">Products</Link><Link href="/catalog/product-types">Product Types</Link><Link href="/catalog/brands">Brands</Link><Link href="/catalog/taxonomies">Taxonomies</Link></nav>}
