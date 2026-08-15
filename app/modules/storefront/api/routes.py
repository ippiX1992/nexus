"""Public, unauthenticated storefront read API.

The shopper never logs in, so these endpoints take a public store key, resolve
it to a tenant via the registry, set the RLS tenant context, and read the
published catalog with prices and stock. Everything is read-only; RLS still
scopes every row to the resolved tenant, so one storefront can never read
another tenant's data even though there is no auth.
"""
import json
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database import get_session
from app.infrastructure.tenant_context import set_tenant_context
from app.modules.storefront.api.schemas import (
    StorefrontMeta,
    StorefrontProduct,
    StorefrontProductDetail,
    StorefrontProductList,
)
from app.modules.storefront.registry import Storefront, resolve

router = APIRouter(prefix="/api/v1/storefront", tags=["storefront"])

# Public product image URLs by SKU, harvested from the source PrestaShop catalog
# (clickhome.ec) into a static map so the storefront can show real photos. The
# catalog has no image column of its own; this file is the demo's media source.
_MEDIA_PATH = Path(__file__).resolve().parents[1] / "clickhome_media.json"
try:
    _MEDIA: dict[str, str] = json.loads(_MEDIA_PATH.read_text(encoding="utf-8"))
except FileNotFoundError:
    _MEDIA = {}


def _image_for(sku: str) -> str | None:
    return _MEDIA.get(sku)

_DEFAULT_PRICE_LIST = text(
    "SELECT id FROM pricing_price_lists WHERE is_default AND status = 'active' "
    "ORDER BY created_at LIMIT 1"
)
_BRAND = text(
    "SELECT name FROM catalog_brands WHERE status = 'active' ORDER BY created_at LIMIT 1"
)
_COUNT = text(
    """
    SELECT count(*)
    FROM catalog_products p
    JOIN catalog_product_variants v
      ON v.product_id = p.id AND v.is_default AND v.archived_at IS NULL
    LEFT JOIN catalog_product_translations t
      ON t.product_id = p.id AND t.locale = :locale
    WHERE p.status = 'active' AND p.archived_at IS NULL
      AND (:search = '' OR t.name ILIKE '%' || :search || '%')
    """
)
_LIST = text(
    """
    SELECT COALESCE(t.slug, v.sku) AS slug,
           COALESCE(t.name, v.sku) AS name,
           t.short_description AS short_description,
           b.name AS brand,
           v.sku AS sku,
           e.unit_amount AS price,
           e.compare_at_amount AS compare_at,
           COALESCE(s.available, 0) AS available
    FROM catalog_products p
    JOIN catalog_product_variants v
      ON v.product_id = p.id AND v.is_default AND v.archived_at IS NULL
    LEFT JOIN catalog_product_translations t
      ON t.product_id = p.id AND t.locale = :locale
    LEFT JOIN catalog_brands b ON b.id = p.brand_id
    LEFT JOIN pricing_price_list_entries e
      ON e.variant_id = v.id AND e.price_list_id = :price_list_id
    LEFT JOIN (
      SELECT variant_id, SUM(on_hand - reserved) AS available
      FROM inventory_stock_levels GROUP BY variant_id
    ) s ON s.variant_id = v.id
    WHERE p.status = 'active' AND p.archived_at IS NULL
      AND (:search = '' OR t.name ILIKE '%' || :search || '%')
    ORDER BY t.name NULLS LAST
    LIMIT :limit OFFSET :offset
    """
)
_DETAIL = text(
    """
    SELECT COALESCE(t.slug, v.sku) AS slug,
           COALESCE(t.name, v.sku) AS name,
           t.short_description AS short_description,
           t.long_description AS long_description,
           b.name AS brand,
           v.sku AS sku,
           e.unit_amount AS price,
           e.compare_at_amount AS compare_at,
           COALESCE(s.available, 0) AS available
    FROM catalog_products p
    JOIN catalog_product_variants v
      ON v.product_id = p.id AND v.is_default AND v.archived_at IS NULL
    LEFT JOIN catalog_product_translations t
      ON t.product_id = p.id AND t.locale = :locale
    LEFT JOIN catalog_brands b ON b.id = p.brand_id
    LEFT JOIN pricing_price_list_entries e
      ON e.variant_id = v.id AND e.price_list_id = :price_list_id
    LEFT JOIN (
      SELECT variant_id, SUM(on_hand - reserved) AS available
      FROM inventory_stock_levels GROUP BY variant_id
    ) s ON s.variant_id = v.id
    WHERE p.status = 'active' AND p.archived_at IS NULL
      AND COALESCE(t.slug, v.sku) = :slug
    LIMIT 1
    """
)


async def _bind(session: AsyncSession, key: str) -> Storefront:
    store = resolve(key)
    if store is None:
        raise HTTPException(status_code=404, detail="Tienda no encontrada")
    await set_tenant_context(session, store.tenant_id)
    return store


async def _price_list_id(session: AsyncSession):
    return (await session.execute(_DEFAULT_PRICE_LIST)).scalar()


def _to_product(row) -> StorefrontProduct:
    available = int(row.available or 0)
    return StorefrontProduct(
        slug=row.slug,
        name=row.name,
        short_description=row.short_description,
        brand=row.brand,
        image=_image_for(row.sku),
        sku=row.sku,
        price=row.price,
        compare_at=row.compare_at,
        currency="",  # filled by caller from the storefront config
        available=available,
        in_stock=available > 0,
    )


@router.get("/{key}", response_model=StorefrontMeta)
async def meta(key: str, session: Annotated[AsyncSession, Depends(get_session)]) -> StorefrontMeta:
    store = await _bind(session, key)
    count = (await session.execute(_COUNT, {"locale": store.locale, "search": ""})).scalar() or 0
    brand = (await session.execute(_BRAND)).scalar()
    return StorefrontMeta(
        key=store.key,
        name=store.name,
        currency=store.currency,
        locale=store.locale,
        brand=brand,
        product_count=int(count),
    )


@router.get("/{key}/products", response_model=StorefrontProductList)
async def products(
    key: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    search: str = Query("", max_length=120),
    limit: int = Query(60, ge=1, le=120),
    offset: int = Query(0, ge=0),
) -> StorefrontProductList:
    store = await _bind(session, key)
    price_list_id = await _price_list_id(session)
    params = {"locale": store.locale, "search": search.strip(), "price_list_id": price_list_id, "limit": limit, "offset": offset}
    rows = (await session.execute(_LIST, params)).all()
    total = (await session.execute(_COUNT, {"locale": store.locale, "search": search.strip()})).scalar() or 0
    items = []
    for row in rows:
        product = _to_product(row)
        product.currency = store.currency
        items.append(product)
    return StorefrontProductList(items=items, total=int(total))


@router.get("/{key}/products/{slug}", response_model=StorefrontProductDetail)
async def product_detail(
    key: str, slug: str, session: Annotated[AsyncSession, Depends(get_session)]
) -> StorefrontProductDetail:
    store = await _bind(session, key)
    price_list_id = await _price_list_id(session)
    row = (
        await session.execute(_DETAIL, {"locale": store.locale, "slug": slug, "price_list_id": price_list_id})
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    available = int(row.available or 0)
    return StorefrontProductDetail(
        slug=row.slug,
        name=row.name,
        short_description=row.short_description,
        long_description=row.long_description,
        brand=row.brand,
        image=_image_for(row.sku),
        sku=row.sku,
        price=row.price,
        compare_at=row.compare_at,
        currency=store.currency,
        available=available,
        in_stock=available > 0,
    )
