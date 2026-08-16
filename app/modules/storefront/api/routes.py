"""Public, unauthenticated storefront read API.

The shopper never logs in, so these endpoints take a public store key, resolve
it to a tenant via the registry, set the RLS tenant context, and read the
published catalog with prices and stock. Everything is read-only; RLS still
scopes every row to the resolved tenant, so one storefront can never read
another tenant's data even though there is no auth.
"""
import json
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database import get_session
from app.infrastructure.tenant_context import set_tenant_context
from app.modules.storefront.api.schemas import (
    OrderCreate,
    OrderLine,
    OrderResponse,
    StockStatus,
    StorefrontCategory,
    StorefrontMeta,
    StorefrontProduct,
    StorefrontProductDetail,
    StorefrontProductList,
    TrackingResponse,
    TrackingStage,
)
from app.modules.storefront.registry import Storefront, resolve

router = APIRouter(prefix="/api/v1/storefront", tags=["storefront"])

# Public product image URLs by SKU, harvested from the source PrestaShop catalog
# (clickhome.ec) into a static map so the storefront can show real photos. The
# catalog has no image column of its own; this file is the demo's media source.
_MEDIA_PATH = Path(__file__).resolve().parents[1] / "clickhome_media.json"
try:
    _MEDIA: dict[str, list[str]] = json.loads(_MEDIA_PATH.read_text(encoding="utf-8"))
except FileNotFoundError:
    _MEDIA = {}


def _images_for(sku: str) -> list[str]:
    return _MEDIA.get(sku) or []


def _image_for(sku: str) -> str | None:
    gallery = _MEDIA.get(sku)
    return gallery[0] if gallery else None

_DEFAULT_PRICE_LIST = text(
    "SELECT id FROM pricing_price_lists WHERE is_default AND status = 'active' "
    "ORDER BY created_at LIMIT 1"
)
_BRAND = text(
    "SELECT name FROM catalog_brands WHERE status = 'active' ORDER BY created_at LIMIT 1"
)
# A product matches :category when the category it is tagged with — or any of
# that category's ancestors — has the given slug (subtree match via closure).
_IN_CATEGORY = """
      AND (:category = '' OR EXISTS (
        SELECT 1 FROM catalog_product_categories pc
        JOIN catalog_category_closure cl ON cl.descendant_id = pc.category_id AND cl.tenant_id = pc.tenant_id
        JOIN catalog_categories cat ON cat.id = cl.ancestor_id AND cat.tenant_id = cat.tenant_id
        WHERE pc.product_id = p.id AND pc.tenant_id = p.tenant_id AND cat.slug = :category
      ))
"""

_CATEGORIES = text(
    """
    SELECT cat.slug AS slug, cat.name AS name, parent.slug AS parent_slug,
           count(DISTINCT pc.product_id) AS product_count
    FROM catalog_categories cat
    LEFT JOIN catalog_categories parent ON parent.id = cat.parent_id AND parent.tenant_id = cat.tenant_id
    JOIN catalog_category_closure cl ON cl.ancestor_id = cat.id AND cl.tenant_id = cat.tenant_id
    JOIN catalog_product_categories pc ON pc.category_id = cl.descendant_id AND pc.tenant_id = cat.tenant_id
    JOIN catalog_products p ON p.id = pc.product_id AND p.tenant_id = cat.tenant_id
      AND p.status = 'active' AND p.archived_at IS NULL
    WHERE cat.status = 'active'
    GROUP BY cat.slug, cat.name, parent.slug
    HAVING count(DISTINCT pc.product_id) > 0
    """
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
    + _IN_CATEGORY
)
_LIST_SELECT = (
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
    """
    + _IN_CATEGORY
)

# Whitelisted ORDER BY fragments — the `sort` query value only ever indexes this
# map, never interpolates into SQL, so there is no injection surface.
_ORDER = {
    "price_asc": "ORDER BY e.unit_amount ASC NULLS LAST, t.name",
    "price_desc": "ORDER BY e.unit_amount DESC NULLS LAST, t.name",
    "name": "ORDER BY t.name NULLS LAST",
}
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


_STOCK = text(
    """
    SELECT COALESCE(s.available, 0) AS available
    FROM catalog_products p
    JOIN catalog_product_variants v ON v.product_id = p.id AND v.is_default AND v.archived_at IS NULL
    LEFT JOIN catalog_product_translations t ON t.product_id = p.id AND t.locale = :locale
    LEFT JOIN (
      SELECT variant_id, SUM(on_hand - reserved) AS available FROM inventory_stock_levels GROUP BY variant_id
    ) s ON s.variant_id = v.id
    WHERE p.status = 'active' AND p.archived_at IS NULL AND COALESCE(t.slug, v.sku) = :slug
    LIMIT 1
    """
)
_ORDER_LINE = text(
    """
    SELECT v.id AS variant_id, COALESCE(t.name, v.sku) AS name, v.sku AS sku,
           e.unit_amount AS price, COALESCE(s.available, 0) AS available
    FROM catalog_products p
    JOIN catalog_product_variants v ON v.product_id = p.id AND v.is_default AND v.archived_at IS NULL
    LEFT JOIN catalog_product_translations t ON t.product_id = p.id AND t.locale = :locale
    LEFT JOIN pricing_price_list_entries e ON e.variant_id = v.id AND e.price_list_id = :price_list_id
    LEFT JOIN (
      SELECT variant_id, SUM(on_hand - reserved) AS available FROM inventory_stock_levels GROUP BY variant_id
    ) s ON s.variant_id = v.id
    WHERE p.status = 'active' AND p.archived_at IS NULL AND COALESCE(t.slug, v.sku) = :slug
    LIMIT 1
    """
)
# Reserve stock on the location that can cover the quantity (available drops).
_RESERVE = text(
    """
    UPDATE inventory_stock_levels SET reserved = reserved + :qty, version = version + 1, updated_at = now()
    WHERE id = (
      SELECT id FROM inventory_stock_levels
      WHERE variant_id = :variant_id AND (on_hand - reserved) >= :qty
      ORDER BY (on_hand - reserved) DESC LIMIT 1
    )
    """
)
_INSERT_ORDER = text(
    """
    INSERT INTO storefront_orders
      (id, tenant_id, order_number, tracking_number, store_key, status, customer_name,
       customer_email, customer_phone, shipping_address, currency, subtotal, item_count, placed_at)
    VALUES
      (:id, :tenant, :number, :tracking, :store_key, 'placed', :name, :email, :phone, :address,
       :currency, :subtotal, :item_count, now())
    """
)
_INSERT_ITEM = text(
    """
    INSERT INTO storefront_order_items (id, tenant_id, order_id, variant_id, sku, name, unit_amount, quantity, line_total)
    VALUES (:id, :tenant, :order_id, :variant_id, :sku, :name, :unit_amount, :quantity, :line_total)
    """
)
_INSERT_EVENT = text(
    """
    INSERT INTO storefront_order_events (id, tenant_id, order_id, status, note)
    VALUES (:id, :tenant, :order_id, :status, :note)
    """
)
_GET_ORDER = text(
    """
    SELECT id, order_number, tracking_number, status, currency, subtotal, item_count, customer_name, placed_at
    FROM storefront_orders WHERE order_number = :number LIMIT 1
    """
)
_GET_ITEMS = text(
    "SELECT sku, name, unit_amount, quantity, line_total FROM storefront_order_items WHERE order_id = :order_id ORDER BY name"
)

# Delivery pipeline. Only "placed" is recorded at checkout; the rest are derived
# from the elapsed time since placed_at so tracking visibly advances (estimated).
_STAGES: tuple[tuple[str, str, timedelta], ...] = (
    ("placed", "Pedido recibido", timedelta(0)),
    ("confirmed", "Pago confirmado", timedelta(hours=2)),
    ("preparing", "En preparación", timedelta(days=1)),
    ("shipped", "Enviado", timedelta(days=2)),
    ("delivered", "Entregado", timedelta(days=4)),
)


def _timeline(placed_at: datetime) -> tuple[str, list[TrackingStage]]:
    now = datetime.now(timezone.utc)
    current = "placed"
    stages: list[TrackingStage] = []
    for status, label, offset in _STAGES:
        at = placed_at + offset
        done = at <= now
        if done:
            current = status
        stages.append(TrackingStage(status=status, label=label, at=at, done=done))
    return current, stages


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
    count = (await session.execute(_COUNT, {"locale": store.locale, "search": "", "category": ""})).scalar() or 0
    brand = (await session.execute(_BRAND)).scalar()
    return StorefrontMeta(
        key=store.key,
        name=store.name,
        currency=store.currency,
        locale=store.locale,
        brand=brand,
        product_count=int(count),
    )


@router.get("/{key}/categories", response_model=list[StorefrontCategory])
async def categories(key: str, session: Annotated[AsyncSession, Depends(get_session)]) -> list[StorefrontCategory]:
    await _bind(session, key)
    rows = (await session.execute(_CATEGORIES)).all()
    nodes = {row.slug: StorefrontCategory(slug=row.slug, name=row.name, product_count=int(row.product_count), children=[]) for row in rows}
    roots: list[StorefrontCategory] = []
    for row in rows:
        parent = nodes.get(row.parent_slug) if row.parent_slug else None
        (parent.children if parent else roots).append(nodes[row.slug])
    by_size = lambda category: (-category.product_count, category.name)
    roots.sort(key=by_size)
    for node in nodes.values():
        node.children.sort(key=by_size)
    return roots


@router.get("/{key}/products", response_model=StorefrontProductList)
async def products(
    key: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    search: str = Query("", max_length=120),
    category: str = Query("", max_length=120),
    sort: str = Query("name"),
    limit: int = Query(60, ge=1, le=120),
    offset: int = Query(0, ge=0),
) -> StorefrontProductList:
    store = await _bind(session, key)
    price_list_id = await _price_list_id(session)
    filters = {"locale": store.locale, "search": search.strip(), "category": category.strip()}
    query = text(_LIST_SELECT + _ORDER.get(sort, _ORDER["name"]) + " LIMIT :limit OFFSET :offset")
    rows = (await session.execute(query, {**filters, "price_list_id": price_list_id, "limit": limit, "offset": offset})).all()
    total = (await session.execute(_COUNT, filters)).scalar() or 0
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
        images=_images_for(row.sku),
        sku=row.sku,
        price=row.price,
        compare_at=row.compare_at,
        currency=store.currency,
        available=available,
        in_stock=available > 0,
    )


@router.get("/{key}/products/{slug}/stock", response_model=StockStatus)
async def product_stock(key: str, slug: str, session: Annotated[AsyncSession, Depends(get_session)]) -> StockStatus:
    store = await _bind(session, key)
    row = (await session.execute(_STOCK, {"locale": store.locale, "slug": slug})).first()
    available = int(row.available) if row else 0
    return StockStatus(slug=slug, available=available, in_stock=available > 0)


@router.post("/{key}/orders", response_model=OrderResponse, status_code=201)
async def create_order(
    key: str, payload: OrderCreate, session: Annotated[AsyncSession, Depends(get_session)]
) -> OrderResponse:
    store = await _bind(session, key)
    price_list_id = await _price_list_id(session)

    lines: list[dict] = []
    subtotal = Decimal("0")
    for item in payload.items:
        row = (
            await session.execute(_ORDER_LINE, {"locale": store.locale, "price_list_id": price_list_id, "slug": item.slug})
        ).first()
        if row is None:
            continue
        available = int(row.available or 0)
        quantity = min(item.quantity, available)
        if quantity <= 0:
            continue  # out of stock — skip silently, validated below
        unit = row.price if row.price is not None else Decimal("0")
        line_total = Decimal(unit) * quantity
        subtotal += line_total
        lines.append(
            {"variant_id": row.variant_id, "sku": row.sku, "name": row.name, "unit_amount": row.price, "quantity": quantity, "line_total": line_total}
        )
        await session.execute(_RESERVE, {"variant_id": row.variant_id, "qty": quantity})

    if not lines:
        raise HTTPException(status_code=400, detail="Ningún producto del pedido tiene stock disponible")

    order_id = uuid4()
    number = f"CH-{datetime.now(timezone.utc):%Y%m%d}-{secrets.token_hex(3).upper()}"
    tracking = f"TRK{secrets.token_hex(5).upper()}"
    item_count = sum(line["quantity"] for line in lines)
    await session.execute(
        _INSERT_ORDER,
        {
            "id": order_id, "tenant": store.tenant_id, "number": number, "tracking": tracking, "store_key": store.key,
            "name": payload.customer_name, "email": payload.customer_email, "phone": payload.customer_phone,
            "address": payload.shipping_address, "currency": store.currency, "subtotal": subtotal, "item_count": item_count,
        },
    )
    for line in lines:
        await session.execute(_INSERT_ITEM, {"id": uuid4(), "tenant": store.tenant_id, "order_id": order_id, **line})
    await session.execute(
        _INSERT_EVENT,
        {"id": uuid4(), "tenant": store.tenant_id, "order_id": order_id, "status": "placed", "note": "Pedido recibido"},
    )
    await session.commit()

    return OrderResponse(
        order_number=number, tracking_number=tracking, status="placed", currency=store.currency,
        subtotal=subtotal, item_count=item_count, customer_name=payload.customer_name, placed_at=datetime.now(timezone.utc),
        items=[OrderLine(sku=line["sku"], name=line["name"], unit_amount=line["unit_amount"], quantity=line["quantity"], line_total=line["line_total"]) for line in lines],
    )


async def _load_order(session: AsyncSession, number: str):
    order = (await session.execute(_GET_ORDER, {"number": number})).first()
    if order is None:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    return order


@router.get("/{key}/orders/{number}", response_model=OrderResponse)
async def get_order(key: str, number: str, session: Annotated[AsyncSession, Depends(get_session)]) -> OrderResponse:
    store = await _bind(session, key)
    order = await _load_order(session, number)
    items = (await session.execute(_GET_ITEMS, {"order_id": order.id})).all()
    current, _ = _timeline(order.placed_at)
    return OrderResponse(
        order_number=order.order_number, tracking_number=order.tracking_number, status=current, currency=order.currency,
        subtotal=order.subtotal, item_count=order.item_count, customer_name=order.customer_name, placed_at=order.placed_at,
        items=[OrderLine(sku=i.sku, name=i.name, unit_amount=i.unit_amount, quantity=i.quantity, line_total=i.line_total) for i in items],
    )


@router.get("/{key}/orders/{number}/tracking", response_model=TrackingResponse)
async def get_tracking(key: str, number: str, session: Annotated[AsyncSession, Depends(get_session)]) -> TrackingResponse:
    await _bind(session, key)
    order = await _load_order(session, number)
    current, stages = _timeline(order.placed_at)
    return TrackingResponse(
        order_number=order.order_number, tracking_number=order.tracking_number, status=current,
        estimated_delivery=order.placed_at + timedelta(days=4), stages=stages,
    )
