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

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_context
from app.application.authorization import TenantContext
from app.infrastructure.database import get_session
from app.infrastructure.tenant_context import set_tenant_context
from app.modules.inventory.application.services import InventoryActor, InventoryService
from app.modules.inventory.domain.policies import InsufficientStock
from app.modules.inventory.infrastructure.repositories import SqlAlchemyInventoryRepository
from app.modules.storefront.api.schemas import (
    CouponInfo,
    OrderCreate,
    OrderLine,
    OrderResponse,
    Review,
    ReviewInput,
    ReviewSummary,
    SpecItem,
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


def _image2_for(sku: str) -> str | None:
    gallery = _MEDIA.get(sku) or []
    return gallery[1] if len(gallery) > 1 else None


# Real product specs (dimensions/weight/EAN) harvested from ClickHome. Warranty
# is a store-wide policy (not per-product data), shown as such.
_SPECS_PATH = Path(__file__).resolve().parents[1] / "clickhome_specs.json"
try:
    _SPECS: dict[str, dict] = json.loads(_SPECS_PATH.read_text(encoding="utf-8"))
except FileNotFoundError:
    _SPECS = {}


def _specs_for(sku: str, available: int) -> list[SpecItem]:
    spec = _SPECS.get(sku, {})
    items = [SpecItem(label="SKU", value=sku)]
    if spec.get("ean"):
        items.append(SpecItem(label="Código EAN", value=spec["ean"]))
    if spec.get("dimensions"):
        items.append(SpecItem(label="Dimensiones", value=spec["dimensions"]))
    if spec.get("weight"):
        items.append(SpecItem(label="Peso", value=spec["weight"]))
    items.append(SpecItem(label="Disponibilidad", value=f"{available} en stock" if available > 0 else "Agotado"))
    items.append(SpecItem(label="Garantía", value="12 meses del fabricante"))
    return items

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

# Optional price band; a bound <= 0 means "no limit" so the same query serves the
# unfiltered case too.
_PRICE_FILTER = """
      AND (:min_price <= 0 OR e.unit_amount >= :min_price)
      AND (:max_price <= 0 OR e.unit_amount <= :max_price)
"""

_COUNT = text(
    """
    SELECT count(*)
    FROM catalog_products p
    JOIN catalog_product_variants v
      ON v.product_id = p.id AND v.is_default AND v.archived_at IS NULL
    LEFT JOIN catalog_product_translations t
      ON t.product_id = p.id AND t.locale = :locale
    LEFT JOIN pricing_price_list_entries e
      ON e.variant_id = v.id AND e.price_list_id = :price_list_id
    WHERE p.status = 'active' AND p.archived_at IS NULL
      AND (:search = '' OR t.name ILIKE '%' || :search || '%')
    """
    + _IN_CATEGORY
    + _PRICE_FILTER
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
    + _PRICE_FILTER
)

# Whitelisted ORDER BY fragments — the `sort` query value only ever indexes this
# map, never interpolates into SQL, so there is no injection surface.
_ORDER = {
    "price_asc": "ORDER BY e.unit_amount ASC NULLS LAST, t.name",
    "price_desc": "ORDER BY e.unit_amount DESC NULLS LAST, t.name",
    "name": "ORDER BY t.name NULLS LAST",
    "newest": "ORDER BY p.created_at DESC NULLS LAST, t.name",
    "random": "ORDER BY random()",
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
# Stock is never touched with raw SQL from here: reservations, commits, releases
# and restocks all go through InventoryService so the ledger, events and the
# reserved/on_hand columns stay consistent. `_ORDER_REF` tags each reservation
# to its order so we can commit/release the exact holds later.
_ORDER_REF = "storefront_order"


def _inventory(session: AsyncSession, tenant_id) -> InventoryService:
    # System actor: a public checkout (or the admin advancing an order) has no
    # inventory-authenticated user; created_by / audit / events accept a null user.
    actor = InventoryActor(user_id=None, session_id=None, tenant_id=tenant_id, correlation_id=uuid4())
    return InventoryService(SqlAlchemyInventoryRepository(session), actor, session)


# Flete: $5 (IVA 15% incluido) para todo el Ecuador continental; Galápagos tiene
# una tarifa distinta. El monto lo decide el servidor según la provincia elegida.
_IVA_RATE = Decimal("0.15")
_SHIPPING_CONTINENTAL = Decimal("5")
_SHIPPING_GALAPAGOS = Decimal("12")


def _shipping_for(province: str | None) -> tuple[str, Decimal]:
    if (province or "").strip().lower() in {"galápagos", "galapagos"}:
        return "galapagos", _SHIPPING_GALAPAGOS
    return "continental", _SHIPPING_CONTINENTAL

# Promo codes applied to the subtotal (demo config).
_COUPONS = {
    "CLICKHOME10": {"type": "percent", "value": 10, "label": "10% de descuento"},
    "BLACK20": {"type": "percent", "value": 20, "label": "20% de descuento"},
    "BIENVENIDO5": {"type": "fixed", "value": 5, "label": "$5 de descuento"},
}


def _coupon_discount(code: str | None, subtotal: Decimal) -> tuple[str | None, Decimal]:
    coupon = _COUPONS.get((code or "").strip().upper())
    if not coupon:
        return None, Decimal("0")
    if coupon["type"] == "percent":
        discount = (subtotal * Decimal(coupon["value"]) / Decimal(100)).quantize(Decimal("0.0001"))
    else:
        discount = Decimal(coupon["value"])
    return (code or "").strip().upper(), min(discount, subtotal)


_INSERT_ORDER = text(
    """
    INSERT INTO storefront_orders
      (id, tenant_id, order_number, tracking_number, store_key, status, customer_name,
       customer_email, customer_phone, shipping_address, shipping_province, shipping_city,
       shipping_method, shipping_amount, coupon_code, discount_amount, currency, subtotal,
       item_count, idempotency_key, placed_at)
    VALUES
      (:id, :tenant, :number, :tracking, :store_key, 'placed', :name, :email, :phone, :address,
       :province, :city, :shipping_method, :shipping_amount, :coupon_code, :discount_amount,
       :currency, :subtotal, :item_count, :idempotency_key, now())
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
    SELECT id, order_number, tracking_number, status, currency, subtotal, shipping_method,
           shipping_amount, shipping_province, shipping_city, coupon_code, discount_amount,
           item_count, customer_name, placed_at
    FROM storefront_orders WHERE order_number = :number LIMIT 1
    """
)
_GET_ITEMS = text(
    "SELECT sku, name, unit_amount, quantity, line_total FROM storefront_order_items WHERE order_id = :order_id ORDER BY name"
)
_GET_ORDER_BY_IDEM = text(
    """
    SELECT id, order_number, tracking_number, status, currency, subtotal, shipping_method,
           shipping_amount, shipping_province, shipping_city, coupon_code, discount_amount,
           item_count, customer_name, placed_at
    FROM storefront_orders WHERE idempotency_key = :key LIMIT 1
    """
)
_REVIEWS = text(
    "SELECT author, rating, comment, created_at FROM storefront_reviews WHERE product_slug = :slug ORDER BY created_at DESC LIMIT 50"
)
_REVIEW_STATS = text("SELECT COALESCE(AVG(rating), 0) AS avg, COUNT(*) AS n FROM storefront_reviews WHERE product_slug = :slug")
_REVIEW_INSERT = text(
    "INSERT INTO storefront_reviews (id, tenant_id, product_slug, author, rating, comment) "
    "VALUES (:id, :tenant, :slug, :author, :rating, :comment)"
)


def _review_summary(stats, rows) -> ReviewSummary:
    return ReviewSummary(
        average=round(float(stats.avg), 1),
        count=int(stats.n),
        items=[Review(author=r.author, rating=r.rating, comment=r.comment, created_at=r.created_at) for r in rows],
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


_STATUS_ORDER = [status for status, _label, _offset in _STAGES]
_GET_EVENTS = text("SELECT status, occurred_at FROM storefront_order_events WHERE order_id = :order_id")


def _timeline(placed_at: datetime, stored_status: str = "placed", event_times: dict | None = None) -> tuple[str, list[TrackingStage]]:
    # A stage is reached when its estimated time has passed OR an admin has pushed
    # the stored status to (or past) it — the later of the two wins.
    now = datetime.now(timezone.utc)
    event_times = event_times or {}
    time_index = 0
    for index, (_status, _label, offset) in enumerate(_STAGES):
        if placed_at + offset <= now:
            time_index = index
    stored_index = _STATUS_ORDER.index(stored_status) if stored_status in _STATUS_ORDER else 0
    current_index = max(time_index, stored_index)
    stages = [
        TrackingStage(status=status, label=label, at=event_times.get(status) or (placed_at + offset), done=index <= current_index)
        for index, (status, label, offset) in enumerate(_STAGES)
    ]
    return _STATUS_ORDER[current_index], stages


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
        image2=_image2_for(row.sku),
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
    price_list_id = await _price_list_id(session)
    count = (
        await session.execute(
            _COUNT,
            {"locale": store.locale, "search": "", "category": "", "price_list_id": price_list_id, "min_price": 0, "max_price": 0},
        )
    ).scalar() or 0
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
    min_price: float = Query(0, ge=0),
    max_price: float = Query(0, ge=0),
    limit: int = Query(60, ge=1, le=120),
    offset: int = Query(0, ge=0),
) -> StorefrontProductList:
    store = await _bind(session, key)
    price_list_id = await _price_list_id(session)
    filters = {
        "locale": store.locale, "search": search.strip(), "category": category.strip(),
        "price_list_id": price_list_id, "min_price": min_price, "max_price": max_price,
    }
    query = text(_LIST_SELECT + _ORDER.get(sort, _ORDER["name"]) + " LIMIT :limit OFFSET :offset")
    rows = (await session.execute(query, {**filters, "limit": limit, "offset": offset})).all()
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
        specs=_specs_for(row.sku, available),
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


@router.get("/{key}/coupons/{code}", response_model=CouponInfo)
async def validate_coupon(key: str, code: str, session: Annotated[AsyncSession, Depends(get_session)]) -> CouponInfo:
    await _bind(session, key)
    coupon = _COUPONS.get(code.strip().upper())
    if not coupon:
        return CouponInfo(code=code.strip().upper(), valid=False)
    return CouponInfo(code=code.strip().upper(), valid=True, label=coupon["label"], discount_type=coupon["type"], value=coupon["value"])


_SUGGEST = text(
    """
    SELECT COALESCE(t.slug, v.sku) AS slug, COALESCE(t.name, v.sku) AS name, v.sku AS sku
    FROM catalog_products p
    JOIN catalog_product_variants v ON v.product_id = p.id AND v.is_default AND v.archived_at IS NULL
    LEFT JOIN catalog_product_translations t ON t.product_id = p.id AND t.locale = :locale
    WHERE p.status = 'active' AND p.archived_at IS NULL AND t.name ILIKE '%' || :q || '%'
    ORDER BY t.name LIMIT 8
    """
)


@router.get("/{key}/suggest")
async def suggest(
    key: str, session: Annotated[AsyncSession, Depends(get_session)], q: str = Query("", max_length=120)
) -> list[dict]:
    store = await _bind(session, key)
    term = q.strip()
    if len(term) < 2:
        return []
    rows = (await session.execute(_SUGGEST, {"locale": store.locale, "q": term})).all()
    return [{"slug": row.slug, "name": row.name, "image": _image_for(row.sku)} for row in rows]


@router.get("/{key}/products/{slug}/reviews", response_model=ReviewSummary)
async def product_reviews(key: str, slug: str, session: Annotated[AsyncSession, Depends(get_session)]) -> ReviewSummary:
    await _bind(session, key)
    stats = (await session.execute(_REVIEW_STATS, {"slug": slug})).first()
    rows = (await session.execute(_REVIEWS, {"slug": slug})).all()
    return _review_summary(stats, rows)


@router.post("/{key}/products/{slug}/reviews", response_model=ReviewSummary, status_code=201)
async def create_review(
    key: str, slug: str, payload: ReviewInput, session: Annotated[AsyncSession, Depends(get_session)]
) -> ReviewSummary:
    store = await _bind(session, key)
    await session.execute(
        _REVIEW_INSERT,
        {"id": uuid4(), "tenant": store.tenant_id, "slug": slug, "author": payload.author, "rating": payload.rating, "comment": payload.comment},
    )
    stats = (await session.execute(_REVIEW_STATS, {"slug": slug})).first()
    rows = (await session.execute(_REVIEWS, {"slug": slug})).all()
    await session.commit()
    return _review_summary(stats, rows)


def _order_response(order, items, events: dict | None = None) -> OrderResponse:
    current, _ = _timeline(order.placed_at, order.status, events)
    return OrderResponse(
        order_number=order.order_number, tracking_number=order.tracking_number, status=current, currency=order.currency,
        subtotal=order.subtotal, shipping_method=order.shipping_method, shipping_amount=order.shipping_amount,
        shipping_province=order.shipping_province, shipping_city=order.shipping_city,
        coupon_code=order.coupon_code, discount_amount=order.discount_amount,
        total=order.subtotal + order.shipping_amount - order.discount_amount, item_count=order.item_count,
        customer_name=order.customer_name, placed_at=order.placed_at,
        items=[OrderLine(sku=i.sku, name=i.name, unit_amount=i.unit_amount, quantity=i.quantity, line_total=i.line_total) for i in items],
    )


@router.post("/{key}/orders", response_model=OrderResponse, status_code=201)
async def create_order(
    key: str,
    payload: OrderCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> OrderResponse:
    store = await _bind(session, key)

    # Idempotent replay: a retried / double-clicked checkout with the same key
    # returns the first order and reserves stock exactly once.
    idem = (idempotency_key or "").strip() or None
    if idem:
        existing = (await session.execute(_GET_ORDER_BY_IDEM, {"key": idem})).first()
        if existing is not None:
            items = (await session.execute(_GET_ITEMS, {"order_id": existing.id})).all()
            return _order_response(existing, items)

    price_list_id = await _price_list_id(session)
    order_id = uuid4()
    inventory = _inventory(session, store.tenant_id)

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
        try:
            # The single source of stock writes: reserves via InventoryService,
            # which locks the level (no overselling), writes the reservation +
            # ledger + event, and tags the hold to this order for later
            # commit/release.
            await inventory.reserve_available(
                row.variant_id, quantity, reference_type=_ORDER_REF, reference_id=order_id
            )
        except InsufficientStock:
            # Lost the race for the last units between the read and the lock —
            # treat this line as out of stock rather than oversell.
            continue
        unit = row.price if row.price is not None else Decimal("0")
        line_total = Decimal(unit) * quantity
        subtotal += line_total
        lines.append(
            {"variant_id": row.variant_id, "sku": row.sku, "name": row.name, "unit_amount": row.price, "quantity": quantity, "line_total": line_total}
        )

    if not lines:
        raise HTTPException(status_code=400, detail="Ningún producto del pedido tiene stock disponible")

    number = f"CH-{datetime.now(timezone.utc):%Y%m%d}-{secrets.token_hex(3).upper()}"
    tracking = f"TRK{secrets.token_hex(5).upper()}"
    item_count = sum(line["quantity"] for line in lines)
    method, shipping_amount = _shipping_for(payload.shipping_province)
    coupon_code, discount = _coupon_discount(payload.coupon_code, subtotal)
    await session.execute(
        _INSERT_ORDER,
        {
            "id": order_id, "tenant": store.tenant_id, "number": number, "tracking": tracking, "store_key": store.key,
            "name": payload.customer_name, "email": payload.customer_email, "phone": payload.customer_phone,
            "address": payload.shipping_address, "province": payload.shipping_province, "city": payload.shipping_city,
            "shipping_method": method, "shipping_amount": shipping_amount,
            "coupon_code": coupon_code, "discount_amount": discount,
            "currency": store.currency, "subtotal": subtotal, "item_count": item_count,
            "idempotency_key": idem,
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
        subtotal=subtotal, shipping_method=method, shipping_amount=shipping_amount,
        shipping_province=payload.shipping_province, shipping_city=payload.shipping_city,
        coupon_code=coupon_code, discount_amount=discount, total=subtotal + shipping_amount - discount,
        item_count=item_count, customer_name=payload.customer_name, placed_at=datetime.now(timezone.utc),
        items=[OrderLine(sku=line["sku"], name=line["name"], unit_amount=line["unit_amount"], quantity=line["quantity"], line_total=line["line_total"]) for line in lines],
    )


async def _load_order(session: AsyncSession, number: str):
    order = (await session.execute(_GET_ORDER, {"number": number})).first()
    if order is None:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    return order


@router.get("/{key}/orders/{number}", response_model=OrderResponse)
async def get_order(key: str, number: str, session: Annotated[AsyncSession, Depends(get_session)]) -> OrderResponse:
    await _bind(session, key)
    order = await _load_order(session, number)
    items = (await session.execute(_GET_ITEMS, {"order_id": order.id})).all()
    events = {row.status: row.occurred_at for row in (await session.execute(_GET_EVENTS, {"order_id": order.id})).all()}
    return _order_response(order, items, events)


@router.get("/{key}/orders/{number}/tracking", response_model=TrackingResponse)
async def get_tracking(key: str, number: str, session: Annotated[AsyncSession, Depends(get_session)]) -> TrackingResponse:
    await _bind(session, key)
    order = await _load_order(session, number)
    events = {row.status: row.occurred_at for row in (await session.execute(_GET_EVENTS, {"order_id": order.id})).all()}
    current, stages = _timeline(order.placed_at, order.status, events)
    return TrackingResponse(
        order_number=order.order_number, tracking_number=order.tracking_number, status=current,
        estimated_delivery=order.placed_at + timedelta(days=4), stages=stages,
    )


# ── Authenticated admin (tenant from the access token, RLS set by the
# dependency). Any active member of the tenant can review and advance orders.
admin_router = APIRouter(prefix="/api/v1/admin/storefront", tags=["storefront-admin"])

_ADMIN_LIST = text(
    """
    SELECT order_number, tracking_number, status, currency, subtotal, item_count,
           customer_name, customer_email, placed_at
    FROM storefront_orders
    WHERE (:status = '' OR status = :status)
      AND (:q = '' OR customer_name ILIKE '%' || :q || '%' OR order_number ILIKE '%' || :q || '%')
    ORDER BY placed_at DESC LIMIT :limit OFFSET :offset
    """
)
_ADMIN_GET = text("SELECT id, status FROM storefront_orders WHERE order_number = :number LIMIT 1")
_ADMIN_ORDER = text(
    """
    SELECT id, order_number, tracking_number, status, currency, subtotal, item_count,
           customer_name, customer_email, customer_phone, shipping_address, placed_at
    FROM storefront_orders WHERE order_number = :number LIMIT 1
    """
)
_ADMIN_ADVANCE = text(
    "UPDATE storefront_orders SET status = :status, version = version + 1, updated_at = now() WHERE id = :id"
)


@admin_router.get("/orders")
async def admin_orders(
    context: Annotated[TenantContext, Depends(get_current_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
    status: str = Query("", max_length=24),
    q: str = Query("", max_length=120),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[dict]:
    rows = (
        await session.execute(_ADMIN_LIST, {"status": status.strip(), "q": q.strip(), "limit": limit, "offset": offset})
    ).all()
    return [
        {
            "order_number": r.order_number, "tracking_number": r.tracking_number, "status": r.status,
            "currency": r.currency, "subtotal": str(r.subtotal), "item_count": r.item_count,
            "customer_name": r.customer_name, "customer_email": r.customer_email, "placed_at": r.placed_at.isoformat(),
        }
        for r in rows
    ]


@admin_router.post("/orders/{number}/advance")
async def admin_advance_order(
    number: str,
    context: Annotated[TenantContext, Depends(get_current_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    order = (await session.execute(_ADMIN_GET, {"number": number})).first()
    if order is None:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    if order.status == "cancelled":
        raise HTTPException(status_code=400, detail="El pedido está cancelado")
    index = _STATUS_ORDER.index(order.status) if order.status in _STATUS_ORDER else 0
    if index >= len(_STATUS_ORDER) - 1:
        raise HTTPException(status_code=400, detail="El pedido ya está entregado")
    nxt = _STATUS_ORDER[index + 1]
    await session.execute(_ADMIN_ADVANCE, {"status": nxt, "id": order.id})
    if nxt == "shipped":
        # Dispatch consumes the held stock through the engine: reserved -= qty,
        # on_hand -= qty, reservation → committed, ledger + event. Idempotent —
        # only still-held reservations are consumed.
        await _inventory(session, context.tenant_id).commit_reservations_for(_ORDER_REF, order.id)
    await session.execute(
        _INSERT_EVENT,
        {"id": uuid4(), "tenant": context.tenant_id, "order_id": order.id, "status": nxt, "note": f"Estado actualizado a {nxt}"},
    )
    await session.commit()
    return {"order_number": number, "status": nxt}


@admin_router.post("/orders/{number}/cancel")
async def admin_cancel_order(
    number: str,
    context: Annotated[TenantContext, Depends(get_current_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    order = (await session.execute(_ADMIN_GET, {"number": number})).first()
    if order is None:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    if order.status == "cancelled":
        return {"order_number": number, "status": "cancelled", "released": 0, "restocked": 0}
    inventory = _inventory(session, context.tenant_id)
    # Not yet dispatched → give the held units back. Already dispatched → the
    # stock left on_hand, so restock it as an explicit adjustment movement.
    released = await inventory.release_reservations_for(_ORDER_REF, order.id, reason="order cancelled")
    restocked = await inventory.restock_committed_for(_ORDER_REF, order.id, reason="order cancelled after dispatch")
    await session.execute(_ADMIN_ADVANCE, {"status": "cancelled", "id": order.id})
    await session.execute(
        _INSERT_EVENT,
        {"id": uuid4(), "tenant": context.tenant_id, "order_id": order.id, "status": "cancelled", "note": "Pedido cancelado"},
    )
    await session.commit()
    return {"order_number": number, "status": "cancelled", "released": released, "restocked": restocked}


@admin_router.get("/orders/{number}")
async def admin_order_detail(
    number: str,
    context: Annotated[TenantContext, Depends(get_current_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    order = (await session.execute(_ADMIN_ORDER, {"number": number})).first()
    if order is None:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    items = (await session.execute(_GET_ITEMS, {"order_id": order.id})).all()
    events = {row.status: row.occurred_at for row in (await session.execute(_GET_EVENTS, {"order_id": order.id})).all()}
    current, stages = _timeline(order.placed_at, order.status, events)
    return {
        "order_number": order.order_number, "tracking_number": order.tracking_number, "status": current,
        "currency": order.currency, "subtotal": str(order.subtotal), "item_count": order.item_count,
        "customer_name": order.customer_name, "customer_email": order.customer_email,
        "customer_phone": order.customer_phone, "shipping_address": order.shipping_address,
        "placed_at": order.placed_at.isoformat(),
        "items": [
            {"sku": i.sku, "name": i.name, "image": _image_for(i.sku), "quantity": i.quantity,
             "unit_amount": str(i.unit_amount) if i.unit_amount is not None else None, "line_total": str(i.line_total)}
            for i in items
        ],
        "stages": [{"status": s.status, "label": s.label, "at": s.at.isoformat(), "done": s.done} for s in stages],
    }


@admin_router.get("/metrics")
async def admin_metrics(
    context: Annotated[TenantContext, Depends(get_current_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    summary = (
        await session.execute(
            text("SELECT count(*) AS orders, COALESCE(SUM(subtotal + shipping_amount - discount_amount), 0) AS revenue FROM storefront_orders")
        )
    ).first()
    # "Hoy" en hora de Ecuador (America/Guayaquil), no en UTC, para que el corte
    # de día coincida con lo que ve el administrador.
    today = (
        await session.execute(
            text(
                "SELECT count(*) AS orders, COALESCE(SUM(subtotal + shipping_amount - discount_amount), 0) AS revenue "
                "FROM storefront_orders "
                "WHERE (created_at AT TIME ZONE 'America/Guayaquil')::date "
                "    = (now() AT TIME ZONE 'America/Guayaquil')::date"
            )
        )
    ).first()
    by_status = {
        row.status: row.n
        for row in (await session.execute(text("SELECT status, count(*) AS n FROM storefront_orders GROUP BY status"))).all()
    }
    top = (
        await session.execute(
            text(
                "SELECT name, SUM(quantity) AS qty, SUM(line_total) AS revenue "
                "FROM storefront_order_items GROUP BY name ORDER BY qty DESC LIMIT 5"
            )
        )
    ).all()
    recent = (
        await session.execute(
            text(
                "SELECT order_number, customer_name, status, "
                "(subtotal + shipping_amount - discount_amount) AS total, created_at "
                "FROM storefront_orders ORDER BY created_at DESC LIMIT 6"
            )
        )
    ).all()
    # Resumen de inventario agregado por variante (una variante puede vivir en
    # varias ubicaciones): disponible = on_hand - reservado.
    inv_sum = (
        await session.execute(
            text(
                """
                WITH v AS (
                    SELECT variant_id,
                           SUM(available) AS avail,
                           SUM(reserved)  AS reserved,
                           SUM(incoming)  AS incoming
                    FROM inventory_stock_levels GROUP BY variant_id
                )
                SELECT COALESCE(SUM(avail), 0)                        AS available,
                       COALESCE(SUM(reserved), 0)                     AS reserved,
                       COALESCE(SUM(incoming), 0)                     AS incoming,
                       COUNT(*) FILTER (WHERE avail <= 0)             AS out_of_stock,
                       COUNT(*) FILTER (WHERE avail > 0 AND avail <= 5) AS low_stock
                FROM v
                """
            )
        )
    ).first()
    low_stock_items = (
        await session.execute(
            text(
                """
                WITH v AS (
                    SELECT variant_id,
                           SUM(available) AS avail,
                           SUM(reserved)  AS reserved,
                           SUM(incoming)  AS incoming
                    FROM inventory_stock_levels GROUP BY variant_id
                )
                SELECT COALESCE(t.name, p.code, cv.sku) AS name, cv.sku AS sku,
                       v.avail AS available, v.reserved AS reserved, v.incoming AS incoming
                FROM v
                JOIN catalog_product_variants cv ON cv.id = v.variant_id
                JOIN catalog_products p ON p.id = cv.product_id AND p.tenant_id = cv.tenant_id
                LEFT JOIN catalog_product_translations t
                  ON t.product_id = p.id AND t.tenant_id = p.tenant_id AND t.locale = 'es-EC'
                WHERE v.avail <= 5
                ORDER BY v.avail ASC, name
                LIMIT 8
                """
            )
        )
    ).all()
    inv_value = (
        await session.execute(
            text(
                """
                SELECT COALESCE(SUM(s.on_hand * e.unit_amount), 0) AS value, COALESCE(SUM(s.on_hand), 0) AS units
                FROM inventory_stock_levels s
                JOIN pricing_price_list_entries e ON e.variant_id = s.variant_id
                  AND e.price_list_id = (SELECT id FROM pricing_price_lists WHERE is_default AND status = 'active' LIMIT 1)
                """
            )
        )
    ).first()
    transfers_in_transit = (
        await session.execute(text("SELECT count(*) FROM inventory_transfers WHERE status = 'in_transit'"))
    ).scalar() or 0
    products = (await session.execute(text("SELECT count(*) FROM catalog_products WHERE status = 'active'"))).scalar() or 0
    return {
        "orders": int(summary.orders or 0),
        "revenue": str(summary.revenue or 0),
        "today": {"orders": int(today.orders or 0), "revenue": str(today.revenue or 0)},
        "by_status": {k: int(v) for k, v in by_status.items()},
        "top_products": [{"name": r.name, "qty": int(r.qty), "revenue": str(r.revenue)} for r in top],
        "recent_orders": [
            {
                "order_number": r.order_number,
                "customer_name": r.customer_name,
                "status": r.status,
                "total": str(r.total),
                "created_at": r.created_at.isoformat(),
            }
            for r in recent
        ],
        "inventory": {
            "available": int(inv_sum.available or 0),
            "reserved": int(inv_sum.reserved or 0),
            "incoming": int(inv_sum.incoming or 0),
            "out_of_stock": int(inv_sum.out_of_stock or 0),
            "low_stock": int(inv_sum.low_stock or 0),
        },
        "low_stock_items": [
            {
                "name": r.name,
                "sku": r.sku,
                "available": int(r.available or 0),
                "reserved": int(r.reserved or 0),
                "incoming": int(r.incoming or 0),
            }
            for r in low_stock_items
        ],
        "transfers_in_transit": int(transfers_in_transit),
        "inventory_value": str(inv_value.value or 0),
        "inventory_units": int(inv_value.units or 0),
        "products": int(products),
    }
