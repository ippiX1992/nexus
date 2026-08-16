"""Full catalog re-seed from ClickHome (PrestaShop) into the Nexus models.

Imports every ACTIVE ClickHome product into the demo tenant: product + default
variant + es-EC translation (name, slug, short/long description) + retail price
entry + stock level + category links (to the tree imported by
import_clickhome_categories.py) + a {sku: image_url} entry in
clickhome_media.json.

It first WIPES the tenant's existing products (and their dependent rows) so the
catalog is a clean mirror — everything here originally came from ClickHome
anyway. Categories/taxonomy, brand, product type, price list and warehouse
location are reused, not recreated.

Usage (PowerShell):
    $env:CLICKHOME_KEY = "<webservice key>"
    python scripts/import_clickhome_catalog.py

The key is read from CLICKHOME_KEY and never written to any file.
"""
from __future__ import annotations

import base64
import html
import json
import os
import re
import ssl
import unicodedata
import urllib.request
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path

import psycopg

KEY = os.environ.get("CLICKHOME_KEY")
BASE = os.environ.get("CLICKHOME_BASE", "https://clickhome.ec/api")
TENANT = os.environ.get("STOREFRONT_TENANT", "7dacbd20-bde4-46c3-ac45-b890427bf9ba")
DB = os.environ.get("STOREFRONT_DB", "host=127.0.0.1 port=55432 dbname=nexus_e2e user=postgres")
MEDIA = Path(__file__).resolve().parents[1] / "app" / "modules" / "storefront" / "clickhome_media.json"
LOCALE = "es-EC"
_ctx = ssl.create_default_context()

# Reusable ids for the demo tenant (see probe output); override via env if needed.
PRODUCT_TYPE = os.environ.get("STOREFRONT_PRODUCT_TYPE", "5d2e6ea6-959d-44e2-9708-7e40779f6759")
BRAND = os.environ.get("STOREFRONT_BRAND", "bba72a31-e013-426a-949e-705d5a60a0ba")
PRICE_LIST = os.environ.get("STOREFRONT_PRICE_LIST", "f5ac4cb9-b7fe-448f-8dbd-9f05a3f600b8")
LOCATION = os.environ.get("STOREFRONT_LOCATION", "9ec6386e-d9a5-4b35-a87b-3171e4692f3f")

WIPE_ORDER = [
    "catalog_product_categories", "catalog_product_identifiers",
    "catalog_product_attribute_value_options", "catalog_product_attribute_values",
    "catalog_variant_option_values", "catalog_product_options",
    "catalog_product_seo", "catalog_product_stores",
    "pricing_price_history", "pricing_variant_price_overrides", "pricing_price_list_entries",
    "inventory_reservations", "inventory_ledger_entries", "inventory_transfers", "inventory_stock_levels",
    "catalog_product_translations", "catalog_product_variants", "catalog_products",
]


def api(path: str):
    request = urllib.request.Request(f"{BASE}{path}")
    request.add_header("Authorization", "Basic " + base64.b64encode(f"{KEY}:".encode()).decode())
    with urllib.request.urlopen(request, timeout=60, context=_ctx) as response:
        return json.load(response)


def first(field):
    return field[0].get("value") if isinstance(field, list) and field else (field or "")


def slugify(text: str, limit: int = 58) -> str:
    ascii_text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    slug = "-".join("".join(c if c.isalnum() else " " for c in ascii_text).split())
    return (slug or "item")[:limit]


def clean_html(raw: str, limit: int = 1400) -> str | None:
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw or ""))
    text = " ".join(text.split())
    return text[:limit] or None


def to_decimal(value) -> Decimal | None:
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.0001"))
        return amount if amount > 0 else None
    except (InvalidOperation, TypeError):
        return None


def fetch_active_products() -> list[dict]:
    products, offset, page = [], 0, 200
    while True:
        batch = api(f"/products?output_format=JSON&filter[active]=1&display=full&limit={offset},{page}").get("products", [])
        products.extend(batch)
        if len(batch) < page:
            break
        offset += page
    return products


def main() -> None:
    if not KEY:
        raise SystemExit("Set CLICKHOME_KEY in the environment first.")

    print("fetching active products…")
    products = fetch_active_products()
    print(f"  {len(products)} products")
    stock = {str(s["id_product"]): int(s.get("quantity") or 0) for s in api("/stock_availables?output_format=JSON&display=[id_product,quantity]&limit=5000").get("stock_availables", [])}
    ch_cats = api("/categories?output_format=JSON&display=[id,name]&limit=500").get("categories", [])
    ch_slug = {str(c["id"]): slugify(first(c.get("name"))) for c in ch_cats}

    conn = psycopg.connect(DB, autocommit=True)
    cur = conn.cursor()
    cur.execute("SELECT slug, id::text FROM catalog_categories WHERE tenant_id=%s", (TENANT,))
    cat_by_slug = dict(cur.fetchall())
    cur.execute("SELECT taxonomy_id::text FROM catalog_categories WHERE tenant_id=%s LIMIT 1", (TENANT,))
    taxonomy = cur.fetchone()[0]

    print("wiping existing tenant products…")
    for table in WIPE_ORDER:
        cur.execute(f"DELETE FROM {table} WHERE tenant_id=%s", (TENANT,))

    used_codes: set[str] = set()
    used_slugs: set[str] = set()
    media: dict[str, str] = {}
    prod_rows, var_rows, tr_rows, price_rows, stock_rows, pc_rows = [], [], [], [], [], []

    for product in products:
        chid = str(product["id"])
        name = (first(product.get("name")) or f"Producto {chid}").strip()[:255]
        reference = (product.get("reference") or "").strip()
        code = reference or f"ch-{chid}"
        if code in used_codes:
            code = f"{code}-{chid}"
        used_codes.add(code)
        sku = code.upper()
        # ClickHome id is unique, so suffixing it guarantees a unique slug/sku
        # even when two product names truncate to the same base.
        slug = f"{slugify(name, 50)}-{chid}"

        pid, vid = str(uuid.uuid4()), str(uuid.uuid4())
        prod_rows.append((pid, TENANT, PRODUCT_TYPE, BRAND, code, "active"))
        var_rows.append((vid, TENANT, pid, sku, sku, True, "active"))
        tr_rows.append((str(uuid.uuid4()), TENANT, pid, LOCALE, name, slug,
                        clean_html(first(product.get("description_short")), 400),
                        clean_html(first(product.get("description")))))

        price = to_decimal(product.get("price"))
        if price is not None:
            price_rows.append((str(uuid.uuid4()), TENANT, PRICE_LIST, vid, price, "active"))
        stock_rows.append((str(uuid.uuid4()), TENANT, LOCATION, vid, max(0, stock.get(chid, 0))))

        link = first(product.get("link_rewrite"))
        img = product.get("id_default_image")
        # PrestaShop friendly image URLs key on the IMAGE id (id_default_image),
        # NOT the product id. Store the whole gallery (default first) per SKU.
        ordered: list[str] = []
        if str(img).isdigit() and int(img) > 0:
            ordered.append(str(img))
        for image in product.get("associations", {}).get("images", []):
            image_id = str(image.get("id"))
            if image_id.isdigit() and image_id not in ordered:
                ordered.append(image_id)
        if ordered and link:
            media[sku] = [f"https://clickhome.ec/{image_id}-home_default/{link}.jpg" for image_id in ordered]

        seen_cats: set[str] = set()
        for position, assoc in enumerate(product.get("associations", {}).get("categories", [])):
            cat_uuid = cat_by_slug.get(ch_slug.get(str(assoc["id"]), ""))
            if cat_uuid and cat_uuid not in seen_cats:
                pc_rows.append((TENANT, pid, cat_uuid, taxonomy, len(seen_cats) == 0, len(seen_cats)))
                seen_cats.add(cat_uuid)

    print("inserting…")
    cur.executemany("INSERT INTO catalog_products (id,tenant_id,product_type_id,brand_id,code,status) VALUES (%s,%s,%s,%s,%s,%s)", prod_rows)
    cur.executemany("INSERT INTO catalog_product_variants (id,tenant_id,product_id,sku,sku_normalized,is_default,status) VALUES (%s,%s,%s,%s,%s,%s,%s)", var_rows)
    cur.executemany("INSERT INTO catalog_product_translations (id,tenant_id,product_id,locale,name,slug,short_description,long_description) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", tr_rows)
    cur.executemany("INSERT INTO pricing_price_list_entries (id,tenant_id,price_list_id,variant_id,unit_amount,status) VALUES (%s,%s,%s,%s,%s,%s)", price_rows)
    cur.executemany("INSERT INTO inventory_stock_levels (id,tenant_id,location_id,variant_id,on_hand) VALUES (%s,%s,%s,%s,%s)", stock_rows)
    cur.executemany("INSERT INTO catalog_product_categories (tenant_id,product_id,category_id,taxonomy_id,is_primary,position) VALUES (%s,%s,%s,%s,%s,%s)", pc_rows)

    MEDIA.write_text(json.dumps(media, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"done: {len(prod_rows)} products, {len(price_rows)} priced, {len(pc_rows)} category links, {len(media)} images")


if __name__ == "__main__":
    main()
