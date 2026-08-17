"""Harvest product specs (dimensions, weight, EAN) from ClickHome into
app/modules/storefront/clickhome_specs.json, keyed by the same SKU rule the
catalog import uses. Warranty is a store policy, not per-product data, so it is
NOT harvested here (the API renders it as a fixed store guarantee).

Usage (PowerShell):
    $env:CLICKHOME_KEY = "<webservice key>"
    python scripts/enrich_storefront_specs.py
"""
from __future__ import annotations

import base64
import json
import os
import ssl
import urllib.request
from pathlib import Path

KEY = os.environ.get("CLICKHOME_KEY")
BASE = os.environ.get("CLICKHOME_BASE", "https://clickhome.ec/api")
OUT = Path(__file__).resolve().parents[1] / "app" / "modules" / "storefront" / "clickhome_specs.json"
_ctx = ssl.create_default_context()


def api(path: str):
    request = urllib.request.Request(f"{BASE}{path}")
    request.add_header("Authorization", "Basic " + base64.b64encode(f"{KEY}:".encode()).decode())
    with urllib.request.urlopen(request, timeout=90, context=_ctx) as response:
        return json.load(response)


def num(value) -> float | None:
    try:
        result = float(value)
        return result if result > 0 else None
    except (TypeError, ValueError):
        return None


def main() -> None:
    if not KEY:
        raise SystemExit("Set CLICKHOME_KEY in the environment first.")
    products, offset, page = [], 0, 200
    while True:
        batch = api(f"/products?output_format=JSON&filter[active]=1&display=[id,reference,ean13,weight,width,height,depth]&limit={offset},{page}").get("products", [])
        products.extend(batch)
        if len(batch) < page:
            break
        offset += page

    used: set[str] = set()
    specs: dict[str, dict] = {}
    for product in products:
        chid = str(product["id"])
        reference = (product.get("reference") or "").strip()
        code = reference or f"ch-{chid}"
        if code in used:
            code = f"{code}-{chid}"
        used.add(code)
        sku = code.upper()

        entry: dict[str, str] = {}
        ean = (product.get("ean13") or "").strip()
        if ean:
            entry["ean"] = ean
        w, h, d = num(product.get("width")), num(product.get("height")), num(product.get("depth"))
        if w and h and d:
            entry["dimensions"] = f"{w:g} x {h:g} x {d:g} cm"
        weight = num(product.get("weight"))
        if weight:
            entry["weight"] = f"{weight:g} kg"
        if entry:
            specs[sku] = entry

    OUT.write_text(json.dumps(specs, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"specs: {len(specs)} products -> {OUT}")


if __name__ == "__main__":
    main()
