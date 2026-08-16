"""Import the ClickHome (PrestaShop) category tree into the Nexus catalog models
so the storefront's categories/menu are real, persisted data — not a side file.

Writes: catalog_taxonomies (one), catalog_categories (the tree under Home),
catalog_category_closure (self + ancestors per node), and
catalog_product_categories (each demo product mapped to its ClickHome
categories). ClickHome product ids are recovered from the image-URL map, so no
name re-matching is needed for product->category assignment.

Idempotent: it clears any previously imported taxonomy of the same code first.

Usage (PowerShell):
    $env:CLICKHOME_KEY = "<webservice key>"
    python scripts/import_clickhome_categories.py
"""
from __future__ import annotations

import base64
import json
import os
import ssl
import unicodedata
import urllib.request
import uuid
from pathlib import Path

import psycopg

KEY = os.environ.get("CLICKHOME_KEY")
BASE = os.environ.get("CLICKHOME_BASE", "https://clickhome.ec/api")
TENANT = os.environ.get("STOREFRONT_TENANT", "7dacbd20-bde4-46c3-ac45-b890427bf9ba")
DB = os.environ.get("STOREFRONT_DB", "host=127.0.0.1 port=55432 dbname=nexus_e2e user=postgres")
MEDIA = Path(__file__).resolve().parents[1] / "app" / "modules" / "storefront" / "clickhome_media.json"
HOME_ID = "2"  # PrestaShop "Inicio" root category; its descendants are the menu
TAXO_CODE = "inicio"
_ctx = ssl.create_default_context()


def api(path: str):
    request = urllib.request.Request(f"{BASE}{path}")
    request.add_header("Authorization", "Basic " + base64.b64encode(f"{KEY}:".encode()).decode())
    with urllib.request.urlopen(request, timeout=40, context=_ctx) as response:
        return json.load(response)


def first(field):
    return field[0].get("value") if isinstance(field, list) and field else field


def slugify(text: str, limit: int = 58) -> str:
    ascii_text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    slug = "-".join("".join(c if c.isalnum() else " " for c in ascii_text).split())
    return (slug or "cat")[:limit]


def main() -> None:
    if not KEY:
        raise SystemExit("Set CLICKHOME_KEY in the environment first.")

    cats = api("/categories?output_format=JSON&display=%5Bid,id_parent,active,name%5D&limit=500").get("categories", [])
    node = {str(c["id"]): {"parent": str(c.get("id_parent")), "name": first(c.get("name")), "active": str(c.get("active"))} for c in cats}

    # Keep active descendants of Home (exclude Root=1 and Home=2 themselves).
    keep: set[str] = set()
    for cid, info in node.items():
        if cid in ("1", HOME_ID) or info["active"] != "1":
            continue
        cursor, ok = cid, False
        for _ in range(20):
            parent = node.get(cursor, {}).get("parent")
            if parent == HOME_ID:
                ok = True
                break
            if parent in (None, "0", "1"):
                break
            cursor = parent
        if ok:
            keep.add(cid)

    conn = psycopg.connect(DB, autocommit=True)
    cur = conn.cursor()

    # Reset any prior import of this taxonomy (idempotent re-runs).
    cur.execute("SELECT id FROM catalog_taxonomies WHERE tenant_id=%s AND code=%s", (TENANT, TAXO_CODE))
    for (old,) in cur.fetchall():
        cur.execute("DELETE FROM catalog_product_categories WHERE tenant_id=%s AND taxonomy_id=%s", (TENANT, old))
        cur.execute("DELETE FROM catalog_category_closure WHERE tenant_id=%s AND taxonomy_id=%s", (TENANT, old))
        cur.execute("DELETE FROM catalog_categories WHERE tenant_id=%s AND taxonomy_id=%s", (TENANT, old))
        cur.execute("DELETE FROM catalog_taxonomies WHERE tenant_id=%s AND id=%s", (TENANT, old))

    taxo_id = str(uuid.uuid4())
    cur.execute(
        "INSERT INTO catalog_taxonomies (id, tenant_id, code, name, status) VALUES (%s,%s,%s,%s,'active')",
        (taxo_id, TENANT, TAXO_CODE, "Inicio"),
    )

    # Insert categories parent-before-child so parent_id + closure resolve.
    ch_to_uuid: dict[str, str] = {cid: str(uuid.uuid4()) for cid in keep}
    used_slugs: set[str] = set()

    def depth_of(cid: str) -> int:
        d, cursor = 0, cid
        while node.get(cursor, {}).get("parent") != HOME_ID and d < 20:
            cursor = node[cursor]["parent"]
            d += 1
        return d

    for cid in sorted(keep, key=depth_of):
        info = node[cid]
        parent_ch = info["parent"]
        parent_uuid = None if parent_ch == HOME_ID else ch_to_uuid.get(parent_ch)
        name = (info["name"] or "Categoría").strip()[:158]
        base = slugify(name)
        slug, n = base, 2
        while slug in used_slugs:
            slug = f"{base}-{n}"[:60]
            n += 1
        used_slugs.add(slug)
        cur.execute(
            """INSERT INTO catalog_categories (id, tenant_id, taxonomy_id, parent_id, code, name, slug, position, status)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'active')""",
            (ch_to_uuid[cid], TENANT, taxo_id, parent_uuid, slug, name, slug, 0),
        )
        # Closure: self (depth 0) + every ancestor within the taxonomy.
        cur.execute(
            "INSERT INTO catalog_category_closure (tenant_id, taxonomy_id, ancestor_id, descendant_id, depth) VALUES (%s,%s,%s,%s,0)",
            (TENANT, taxo_id, ch_to_uuid[cid], ch_to_uuid[cid]),
        )
        depth, walker = 1, parent_ch
        while walker != HOME_ID and walker in ch_to_uuid:
            cur.execute(
                "INSERT INTO catalog_category_closure (tenant_id, taxonomy_id, ancestor_id, descendant_id, depth) VALUES (%s,%s,%s,%s,%s)",
                (TENANT, taxo_id, ch_to_uuid[walker], ch_to_uuid[cid], depth),
            )
            walker = node[walker]["parent"]
            depth += 1
    print(f"taxonomy inicio + {len(keep)} categories inserted")

    # Product -> categories, using the ClickHome product id embedded in image URLs.
    media = json.loads(MEDIA.read_text(encoding="utf-8"))
    cur.execute(
        """SELECT v.sku, p.id::text FROM catalog_products p
           JOIN catalog_product_variants v ON v.product_id=p.id AND v.tenant_id=p.tenant_id AND v.is_default
           WHERE p.tenant_id=%s""",
        (TENANT,),
    )
    product_by_sku = dict(cur.fetchall())

    assigned = 0
    for sku, url in media.items():
        pid = product_by_sku.get(sku)
        if not pid:
            continue
        ch_pid = url.rsplit("/", 2)[1].split("-", 1)[0]  # ".../{id}-home_default/..."
        try:
            detail = api(f"/products/{ch_pid}?output_format=JSON")
        except Exception:
            continue
        ch_cats = detail.get("product", {}).get("associations", {}).get("categories", [])
        mapped = [ch_to_uuid[str(c["id"])] for c in ch_cats if str(c["id"]) in ch_to_uuid]
        for position, cat_uuid in enumerate(dict.fromkeys(mapped)):
            cur.execute(
                """INSERT INTO catalog_product_categories (tenant_id, product_id, category_id, taxonomy_id, is_primary, position)
                   VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                (TENANT, pid, cat_uuid, taxo_id, position == 0, position),
            )
        if mapped:
            assigned += 1
    print(f"assigned categories to {assigned} products")


if __name__ == "__main__":
    main()
