"""Harvest public product image URLs from the ClickHome PrestaShop webservice
and write app/modules/storefront/clickhome_media.json (a {sku: image_url} map
the storefront serves as product photos).

The catalog imported into Nexus has no image column, and ClickHome product
references don't match our SKUs, so we match by normalized product name. Image
URLs use PrestaShop's public friendly-URL pattern and need no key at read time.

Usage (PowerShell):
    $env:CLICKHOME_KEY = "<webservice key>"
    python scripts/enrich_storefront_media.py

The key is read from the environment and is NEVER written to the output file
or committed. Only public image URLs are stored.
"""
from __future__ import annotations

import base64
import json
import os
import ssl
import unicodedata
import urllib.request
from pathlib import Path

import psycopg

KEY = os.environ.get("CLICKHOME_KEY")
BASE = os.environ.get("CLICKHOME_BASE", "https://clickhome.ec/api")
TENANT = os.environ.get("STOREFRONT_TENANT", "7dacbd20-bde4-46c3-ac45-b890427bf9ba")
DB = os.environ.get("STOREFRONT_DB", "host=127.0.0.1 port=55432 dbname=nexus_e2e user=postgres")
OUT = Path(__file__).resolve().parents[1] / "app" / "modules" / "storefront" / "clickhome_media.json"


def norm(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode().lower()
    return " ".join("".join(c if c.isalnum() or c == " " else " " for c in text).split())


def api(path: str):
    request = urllib.request.Request(f"{BASE}{path}")
    request.add_header("Authorization", "Basic " + base64.b64encode(f"{KEY}:".encode()).decode())
    with urllib.request.urlopen(request, timeout=40, context=ssl.create_default_context()) as response:
        return json.load(response)


def first_value(field):
    return field[0].get("value") if isinstance(field, list) and field else field


def main() -> None:
    if not KEY:
        raise SystemExit("Set CLICKHOME_KEY in the environment first.")
    products = api("/products?output_format=JSON&display=%5Bid,name,link_rewrite,id_default_image%5D&limit=5000").get("products", [])
    by_name: dict[str, dict] = {}
    for product in products:
        by_name[norm(first_value(product.get("name")))] = {
            "id": product["id"],
            "lr": first_value(product.get("link_rewrite")),
            "img": product.get("id_default_image"),
        }
    print(f"clickhome products: {len(products)}")

    cursor = psycopg.connect(DB, autocommit=True).cursor()
    cursor.execute(
        """
        SELECT v.sku, t.name FROM catalog_products p
        JOIN catalog_product_variants v ON v.product_id = p.id AND v.tenant_id = p.tenant_id AND v.is_default
        JOIN catalog_product_translations t ON t.product_id = p.id AND t.tenant_id = p.tenant_id AND t.locale = 'es-EC'
        WHERE p.tenant_id = %s
        """,
        (TENANT,),
    )
    ours = cursor.fetchall()

    media: dict[str, str] = {}
    unmatched: list[str] = []
    for sku, name in ours:
        match = by_name.get(norm(name))
        if match and str(match.get("img")).isdigit() and int(match["img"]) > 0:
            media[sku] = f"https://clickhome.ec/{match['id']}-home_default/{match['lr']}.jpg"
        else:
            unmatched.append(name)

    OUT.write_text(json.dumps(media, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"matched {len(media)}/{len(ours)} -> {OUT}")
    if unmatched:
        print("unmatched:", unmatched)


if __name__ == "__main__":
    main()
